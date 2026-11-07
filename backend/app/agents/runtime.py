"""Agent runtime: the tool-calling loop, the Planner, the Advisor and rule-based fallbacks.

Every LLM call goes through the `LLMRouter` (privacy routing and fallback). When the local LLM is down, the agents
fall back to rules (PRD R3): keyword intent, a direct metric routine or vault search, and a template answer built
only from tool results.
"""

from __future__ import annotations

import asyncio
import calendar
import dataclasses
import datetime as dt
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from app.agents.decision_frame import ASSUMPTION_LABEL, DecisionFrame, OptionCost, build_frame, names_goal
from app.agents.events import Artifact, Citation, EventBus
from app.agents.guards import guarded, in_role, role_problems
from app.agents.registry import PROMPTS_DIR, REGISTRY, AgentType, spawnable_types
from app.agents.sources import (
    REMOVED_NOTE,
    Evidence,
    cited_sources,
    figures_removed,
    gather,
    masked,
    vault_checker,
    without_unsupported,
)
from app.agents.specialists import (
    MAX_TEAM,
    REGULATORY_NOTE,
    RULE_TEXT,
    MemoDraft,
    MemoPrediction,
    MemoRef,
    calls_for_team,
    default_brief,
    in_your_words,
    lens_name,
    memo_schema,
    needs_analyst,
    risk_register,
    rule_draft,
    scout_without_web,
    team_for_message,
    with_real_outcomes,
    with_required_fields,
    without_unbacked_figures,
    write_memo,
)
from app.agents.tools import TOOLS, DecisionImpact, ToolContext, ToolOutcome, run_tool, specs_for, web_outcome
from app.agents.verifier import (
    PATH_RE,
    ClaimIssue,
    Fact,
    extract_figures,
    format_money,
    named_paths,
    number_supported,
    repair_claims,
    split_sentences,
    verify,
)
from app.decision.base import DecisionError, DecisionService
from app.engine.hybrid_rag import bm25_tokens
from app.engine.lineage import Lineage
from app.llm.base import Completion, LLMError, Message, StreamChunk, ToolCall, Usage
from app.llm.router import LLMRouter
from app.vault.decisions import DecisionRecord
from app.vault.manager import VaultError

Intent = Literal["finance", "knowledge", "decision", "chitchat"]
INTENT_OPTIONS: list[str] = ["finance", "knowledge", "decision", "chitchat"]
INTENT_QUESTION = (
    "What does the founder's message need? finance = a question about the company's own numbers (runway, burn, "
    "revenue, margins, churn, CAC); knowledge = what their notes, documents or past decisions say; decision = a "
    "business decision to analyse (hiring, pricing, expansion, spending); chitchat = a greeting or small talk."
)

_DECISION_CUES = re.compile(
    r"\b(should (we|i)|shall we|whether|what if|decid\w*|decision|thinking (of|about)|want to|plan to|"
    r"open(ing)? an?|hire|hiring|launch|expand|raise (a|our)? ?(round|money|funds)|cut|invest)\b",
    re.I,
)
_FINANCE_CUES = re.compile(
    r"\b(runway|burn|cash|mrr|arr|revenue|margin|cac|ltv|churn|nrr|payback|growth|headcount cost|arpa|"
    r"profit|spend|metrics?|numbers?|how much|how long)\b",
    re.I,
)
_KNOWLEDGE_CUES = re.compile(r"\b(notes?|vault|journal|documents?|wrote|board update|memo|decided|last time)\b", re.I)
# Naming the notes says where to look, whatever the topic: "What do my notes say about churn?" is not a metric.
_ASKS_THE_NOTES = re.compile(
    r"\b((my|our|the) (notes?|journal|vault|documents?|board update|memo)|what (did|have) (we|i) (decide|decided)|"
    r"past decisions?|company profile)\b",
    re.I,
)
_ASKS_TO_DECIDE = re.compile(r"\b(should|shall) (we|i)\b", re.I)
_ASKS_WHAT_WAS_DECIDED = re.compile(
    r"\b(what (did|have) (we|i) (decide|decided)|did (we|i) (already )?(decide|agree)|have (we|i) (already )?decided|"
    r"past decisions?|review date)\b",
    re.I,
)
_SAYS_NOTHING_FOUND = re.compile(
    r"\b(nothing|no (relevant|information|notes?|mention|details?|sources?)|not (found|mentioned|covered)|"
    r"(do|does|did) not (say|mention|cover|contain))\b",
    re.I,
)
_CHITCHAT = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b(\s+(there|team|all|everyone))?[\s!.?]*$",
    re.I,
)

KILL_CRITERIA_OVERLAP = 0.6

# A single-metric question is answered by code, plus at most one short question from the model (PRD R1).
MAX_LOOKUP_WORDS = 12
MAX_QUESTION_WORDS = 22
METRIC_QUESTION_TIMEOUT_S = 4.0
_ASKS_FOR_A_NUMBER = re.compile(
    # "What about our churn?" is a lookup too: plain "churn" is logo churn, the goal's own metric (founder review 23).
    r"^\s*(?:what(?:'|\u2019)?s|what is|what are|what about|how about|how much|how long|how(?:'|\u2019)s|show(?: me)?|"
    r"tell me|give me|"
    r"our|my|current)\b",
    re.I,
)
_MORE_THAN_A_NUMBER = re.compile(
    r"\b(?:why|compare[ds]?|versus|vs|trend\w*|over time|histor\w+|last|previous|prior|forecast\w*|project\w*|"
    r"next|by|each|if|would|could|should|will|after|before|since|in|between|good|bad|ok|okay|healthy|enough|"
    r"explain\w*|break\w*|channel\w*|segment\w*|customers?|because|and|or|plus|with|without)\b",
    re.I,
)
_SPELLED_NUMBERS = frozenset(
    {
        *("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"),
        *("hundred", "thousand", "million", "billion", "trillion", "half", "double", "twice", "percent"),
    }
)

# Keyword -> metric routine, for the rule-based Financial Analyst (first match wins).
METRIC_KEYWORDS: list[tuple[str, str]] = [
    ("runway", "runway"),
    ("net burn", "net_burn"),
    ("gross burn", "gross_burn"),
    ("burn", "net_burn"),
    ("arr", "arr"),
    ("mrr", "mrr"),
    ("gross margin", "gross_margin"),
    ("margin", "gross_margin"),
    ("ltv:cac", "ltv_cac"),
    ("ltv", "ltv"),
    ("payback", "cac_payback"),
    ("cac", "cac"),
    ("nrr", "nrr"),
    ("retention", "nrr"),
    ("revenue churn", "revenue_churn"),
    ("churn", "logo_churn"),
    ("arpa", "arpa"),
    ("growth", "revenue_growth"),
    ("headcount", "headcount_cost"),
    ("payroll", "headcount_cost"),
]


class AgentInstance(BaseModel):
    id: str = Field(default_factory=lambda: f"agt_{uuid.uuid4().hex[:8]}")
    type: str
    name: str
    brief: str
    provider: str = ""
    model: str = ""
    is_cloud: bool = False
    fast_metric: str | None = Field(default=None, description="A single-metric question: code writes the answer")
    local_only: bool = Field(default=False, description="The founder chose to keep this team on the local model")


class Plan(BaseModel):
    intent: Intent
    decision_type: str | None = None
    reversibility: Literal["one_way", "two_way"] | None = None
    team: list[AgentInstance] = Field(default_factory=list)
    planner: str = Field(description="How the plan was made: rules, decision model or LLM")
    intent_decision_id: str | None = None
    frame: DecisionFrame | None = Field(default=None, description="Type, cost model, options and goal check, by code")


class AgentResult(BaseModel):
    agent_id: str
    type: str
    name: str
    brief: str
    text: str = ""
    status: Literal["done", "failed", "cancelled"] = "done"
    error: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list, description="Only the sources the answer names")
    retrieved: list[Citation] = Field(default_factory=list, description="Everything the agent's tools returned")
    past_decisions: list[DecisionRecord] = Field(default_factory=list, description="On record for this topic")
    decision_impact: DecisionImpact | None = Field(default=None, description="From run_scenario, computed in code")
    memo: MemoRef | None = Field(default=None, description="The memo this agent wrote")
    written_by_code: bool = Field(default=False, description="The fast path: no model wrote this answer")
    removed: list[str] = Field(
        default_factory=list, description="What the source check took out, reworded with no figure or source in it"
    )
    removed_figures: list[float] = Field(default_factory=list, exclude=True)
    passages: dict[str, list[str]] = Field(default_factory=dict, exclude=True, description="Source -> text retrieved")
    facts: list[Fact] = Field(default_factory=list, exclude=True)
    inherited: list[Fact] = Field(default_factory=list, exclude=True, description="From earlier stages of the team")
    record_passages: dict[str, list[str]] = Field(default_factory=dict, exclude=True, description="Proposed memos")
    record_facts: list[Fact] = Field(
        default_factory=list, exclude=True, description="Figures of a proposed memo on record: backed once it is cited"
    )
    inherited_impact: DecisionImpact | None = Field(default=None, exclude=True)
    est_cost_usd: float | None = Field(default=0.0, description="None: a cloud model with no known price")
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    verified: bool | None = None
    issues: list[str] = Field(default_factory=list)
    attempts: int = 1
    provider: str = ""
    model: str = ""
    fallback_from: str | None = None
    usage: Usage = Field(default_factory=Usage)
    elapsed_ms: float = 0.0

    @property
    def numbers(self) -> list[float]:
        return [f.value for f in self.facts]

    @property
    def known_facts(self) -> list[Fact]:
        return [*self.facts, *self.inherited]

    @property
    def lineage(self) -> list[Lineage]:
        return [lin for a in self.artifacts for lin in a.lineage]


Emit = Callable[..., Any]


def rule_intent(message: str) -> Intent | None:
    """Clear-cut cases need no model call (fast, deterministic). Ambiguous ones return None."""
    if _CHITCHAT.match(message):
        return "chitchat"
    if _ASKS_WHAT_WAS_DECIDED.search(message) and not _ASKS_TO_DECIDE.search(message):
        return "knowledge"
    if _DECISION_CUES.search(message):
        return "decision"
    if _ASKS_THE_NOTES.search(message):
        return "knowledge"
    if _FINANCE_CUES.search(message):
        return "finance"
    if _KNOWLEDGE_CUES.search(message):
        return "knowledge"
    return None


def rule_metric(text: str) -> str | None:
    lowered = text.lower()
    for keyword, metric in METRIC_KEYWORDS:
        if re.search(rf"(?<![\w:]){re.escape(keyword)}(?![\w:])", lowered):
            return metric
    return None


_LOOKUP_WORDS = frozenset(
    [
        "a",
        "about",
        "am",
        "are",
        "at",
        "can",
        "cost",
        "costs",
        "current",
        "currently",
        "do",
        "does",
        "give",
        "have",
        "how",
        "i",
        "is",
        "latest",
        "logo",
        "long",
        "many",
        "me",
        "month",
        "monthly",
        "months",
        "much",
        "my",
        "now",
        "of",
        "our",
        "per",
        "please",
        "rate",
        "right",
        "s",
        "show",
        "tell",
        "the",
        "today",
        "us",
        "we",
        "what",
        "whats",
        "you",
    ]
)


def single_metric(message: str) -> str | None:
    """The one metric a plain question asks for, or None if it asks for anything more than that number.

    "What's our runway?" is a lookup. "Why is burn up?", "runway in March" and "burn and churn" need the model.
    """
    if not _ASKS_FOR_A_NUMBER.match(message) or _MORE_THAN_A_NUMBER.search(message) or re.search(r"\d", message):
        return None
    if len(message.split()) > MAX_LOOKUP_WORDS:
        return None
    left = message.lower()
    found: set[str] = set()
    for keyword, metric in METRIC_KEYWORDS:  # longer forms come first, so "net burn" is not read as "burn" as well
        pattern = rf"(?<![\w:]){re.escape(keyword)}(?![\w:])"
        if re.search(pattern, left):
            found.add(metric)
            left = re.sub(pattern, " ", left)
    # Every other word must be one a plain lookup uses: "MRR for January" and "runway we need" are other questions.
    if set(re.findall(r"[a-z]+", left)) - _LOOKUP_WORDS:
        return None
    return found.pop() if len(found) == 1 else None


def _instance(agent_type: str, brief: str, router: LLMRouter, index: int = 1) -> AgentInstance:
    spec = REGISTRY[agent_type]
    provider = router.primary(spec.privacy, needs_tools=bool(spec.tools), agent_type=agent_type)
    suffix = f" #{index}" if index > 1 else ""
    lens = lens_name(brief) if agent_type == "perspective_lens" else None
    return AgentInstance(
        type=agent_type,
        name=f"{spec.title}: {lens}{suffix}" if lens else f"{spec.title}{suffix}",
        brief=brief,
        provider=provider.name,
        model=provider.model,
        is_cloud=provider.is_cloud,
    )


def _team(tasks: list[tuple[str, str]], router: LLMRouter) -> list[AgentInstance]:
    counts: dict[str, int] = {}
    team: list[AgentInstance] = []
    for agent_type, brief in tasks:
        counts[agent_type] = counts.get(agent_type, 0) + 1
        team.append(_instance(agent_type, brief, router, counts[agent_type]))
    return team


async def plan(message: str, router: LLMRouter, decisions: DecisionService) -> Plan:
    """Planner: intent (rules, then the decision model), then the team (templates, or the LLM for decisions)."""
    if calls_for_team(message):
        return await _plan_decision(message, router, "rules (the founder named a specialist's work)", None)
    intent = rule_intent(message)
    how = "rules"
    decision_id = None
    if intent is None:
        try:
            decision = await decisions.choose(INTENT_QUESTION, INTENT_OPTIONS, {"message": message}, kind="intent")
        except DecisionError as exc:
            logger.info("Intent decision failed, using the default team: {}", exc)
            return _default_decision_plan(message, router, "rules (decision model unavailable); default team", None)
        decision_id = decision.id
        if decision.probability < decisions.min_confidence:
            # Unsure what the founder means: the safe choice is to look at both the numbers and the notes.
            how = f"decision model unsure ({decision.choice} p={decision.probability:.2f}); default team"
            return _default_decision_plan(message, router, how, decision_id)
        intent, how = decision.choice, f"decision model ({decision.provider}, p={decision.probability:.2f})"  # type: ignore[assignment]
    assert intent is not None
    if intent == "chitchat":
        return Plan(intent=intent, planner=how, intent_decision_id=decision_id)
    if intent == "finance":
        team = _team([("financial_analyst", message)], router)
        team[0].fast_metric = single_metric(message)
        return Plan(intent=intent, team=team, planner=how, intent_decision_id=decision_id)
    if intent == "knowledge":
        team = _team([("librarian", message)], router)
        return Plan(intent=intent, team=team, planner=how, intent_decision_id=decision_id)
    return await _plan_decision(message, router, how, decision_id)


def _with_required_types(tasks: list[tuple[str, str]], message: str) -> list[tuple[str, str]]:
    """The specialists the founder's words call for, and the Analyst whose numbers they argue from.

    The founder asked for them, so they stay even if the team is full: others make room, last planned first.
    """
    required = [t for t in team_for_message(message) if t not in {agent_type for agent_type, _ in tasks}]
    combined = [*tasks, *((t, default_brief(t, message)) for t in required)]
    if needs_analyst([agent_type for agent_type, _ in combined]):
        combined.insert(0, ("financial_analyst", f"Numbers that matter for this decision: {message}"))
    keep = {"librarian", "financial_analyst", *required}
    while len(combined) > MAX_TEAM:
        drop = next((i for i in range(len(combined) - 1, -1, -1) if combined[i][0] not in keep), len(combined) - 1)
        combined.pop(drop)
    return combined


def _default_decision_plan(message: str, router: LLMRouter, how: str, decision_id: str | None) -> Plan:
    tasks = [
        ("financial_analyst", f"Numbers that matter for this decision: {message}"),
        ("librarian", f"What the notes and past decisions say about: {message}"),
    ]
    team = _team(_with_required_types(tasks, message), router)
    return Plan(intent="decision", team=team, planner=how, intent_decision_id=decision_id)


async def _plan_decision(message: str, router: LLMRouter, how: str, decision_id: str | None) -> Plan:
    types = spawnable_types()
    schema = {
        "type": "object",
        "properties": {
            "decision_type": {"type": "string"},
            "reversibility": {"type": "string", "enum": ["one_way", "two_way"]},
            "tasks": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {"agent_type": {"type": "string", "enum": types}, "brief": {"type": "string"}},
                    "required": ["agent_type", "brief"],
                },
            },
        },
        "required": ["decision_type", "reversibility", "tasks"],
    }
    messages = [Message.system(REGISTRY["planner"].prompt()), Message.user(message)]
    try:
        data = (await router.complete(REGISTRY["planner"].privacy, messages, json_schema=schema)).json()
        if not isinstance(data, dict):
            raise LLMError(f"the plan was not a JSON object: {str(data)[:100]}")
        tasks = [
            (str(t["agent_type"]), str(t["brief"]).strip() or message)
            for t in data.get("tasks", [])[:6]
            if isinstance(t, dict) and t.get("agent_type") in types
        ]
        if not tasks:
            raise LLMError("the plan had no valid tasks")
        if not any(agent_type == "librarian" for agent_type, _ in tasks):
            # A decision is never analysed without checking what was already decided, whatever the plan says.
            tasks = [*tasks[:5], ("librarian", f"What the founder already decided on this topic: {message}")]
        reversibility = data.get("reversibility") if data.get("reversibility") in ("one_way", "two_way") else None
        return Plan(
            intent="decision",
            decision_type=str(data.get("decision_type") or "") or None,
            reversibility=reversibility,
            team=_team(_with_required_types(tasks, message), router),
            planner=f"{how}; team by LLM",
            intent_decision_id=decision_id,
        )
    except (LLMError, KeyError, TypeError, ValueError, AttributeError) as exc:
        logger.info("Planner LLM failed, using the default decision team: {}", exc)
        return _default_decision_plan(message, router, f"{how}; default team", decision_id)


class AgentRunner:
    """Runs one agent instance: LLM tool loop (or rules when the LLM is down), then the Verifier (one retry)."""

    def __init__(
        self,
        router: LLMRouter,
        bus: EventBus,
        run_id: str,
        ctx_factory: Callable[[str], ToolContext],
        max_steps: int = 4,
    ) -> None:
        self.router = router
        self.bus = bus
        self.run_id = run_id
        self.ctx_factory = ctx_factory
        self.max_steps = max_steps
        self.frame: DecisionFrame | None = None

    def _emit(self, type_: Any, agent_id: str, **data: Any) -> None:
        self.bus.emit(type_, self.run_id, agent_id, **data)

    async def run(
        self,
        inst: AgentInstance,
        user_message: str,
        upstream: list[AgentResult] | None = None,
        frame: DecisionFrame | None = None,
    ) -> AgentResult:
        spec = REGISTRY[inst.type]
        if inst.local_only:
            spec = dataclasses.replace(spec, privacy="local")
        started = time.perf_counter()
        upstream = upstream or []
        if frame is None and spec.name == "memo_writer":
            frame = await asyncio.to_thread(build_frame, user_message, self.ctx_factory(inst.id))
        self.frame = frame
        result = AgentResult(
            agent_id=inst.id,
            type=inst.type,
            name=inst.name,
            brief=inst.brief,
            inherited=[*(fact for r in upstream for fact in r.facts), *(frame.facts if frame else [])],
            record_facts=[fact for r in upstream for fact in r.record_facts],
            inherited_impact=team_impact(upstream),
        )
        self._emit("agent.status", inst.id, status="thinking")
        await self._look_up_past_decisions(spec, inst, user_message, result)
        findings = f"\nTeam findings so far:\n{findings_for_advisor(upstream)}" if upstream else ""
        framed = frame.for_agents() if frame is not None else ""
        messages = [
            Message.system(spec.prompt() + await self._data_context(spec) + _decisions_context(result) + framed),
            Message.user(f"Brief: {inst.brief}\nFounder's message: {user_message}{findings}"),
        ]
        if spec.name == "memo_writer":
            if frame is not None:
                messages.append(Message.user(_memo_brief(frame)))
            await self._write_memo(spec, inst, user_message, messages, upstream, result)
            return self._finish(inst, result, started)
        if await self._metric_written_by_code(spec, inst, user_message, result):
            self._verify(spec, inst, user_message, result)
            return self._finish(inst, result, started)
        await self._search_first(spec, inst, user_message, messages, result)
        await self._cost_model_first(spec, inst, messages, result)
        await self._scenario_first(spec, inst, user_message, messages, result)
        try:
            await self._loop(spec, inst, messages, result)
        except LLMError as exc:
            logger.warning("Agent {} LLM unavailable, using rules: {}", inst.name, exc)
            result.fallback_from = result.provider or inst.provider
            await self._rules(spec, inst, user_message, result)
        await self._insist_on_scoring(spec, inst, messages, result)
        await self._surface_named_folder(spec, inst, user_message, result)
        _surface_decisions(result)
        self._verify(spec, inst, user_message, result)
        out_of_role = role_problems(spec.name, result.text, user_message, frame)
        if not result.text.strip():
            out_of_role = ["your answer was empty: answer your brief"]
        if out_of_role:
            result.verified = False
            result.issues = [*result.issues, *out_of_role]
        if not result.verified and result.provider not in ("rules", ""):
            result.attempts = 2
            self._emit("agent.step", inst.id, step="sent back by the Verifier: " + "; ".join(result.issues))
            feedback = (
                "The Verifier rejected your answer: "
                + "; ".join(result.issues)
                + ". Use only numbers from tool results (call a tool if needed) and cite only returned sources. "
                "Answer again."
            )
            messages.append(Message.assistant(result.text))
            messages.append(Message.user(feedback))
            try:
                await self._loop(spec, inst, messages, result)
            except LLMError as exc:
                result.issues.append(f"retry failed: {exc}")
            _surface_decisions(result)
            self._verify(spec, inst, user_message, result)
        _replace_wrong_claims(result, user_message)
        result.text = guarded(
            in_role(spec.name, result.text, user_message, frame), frame, _records_for(result, upstream)
        )
        self._remove_unsupported(inst, user_message, upstream, result)
        if not result.text.replace(REMOVED_NOTE, "").strip() and spec.name in RULE_TEXT:
            # Seen live: a small model can return nothing, twice. Or nothing it said could be backed.
            result.text = RULE_TEXT[spec.name]
        self._finish_specialist(spec, inst, result)
        _keep_used_sources(result)
        return self._finish(inst, result, started)

    async def _metric_written_by_code(
        self, spec: AgentType, inst: AgentInstance, user_message: str, result: AgentResult
    ) -> bool:
        """A single-metric question: the routine's result is the answer. An edited brief goes to the model instead."""
        if inst.fast_metric is None or inst.brief != user_message:
            return False
        call = ToolCall(name="get_metric", arguments={"name": inst.fast_metric})
        outcome = await self._call_tool(spec, inst, call, result)
        if outcome.error:
            return False  # the model explains what is missing
        result.provider, result.model = "rules", ""
        result.text = metric_sentence(
            outcome.content, inst.fast_metric, self.ctx_factory(inst.id).finance.metrics.currency
        )
        result.written_by_code = True
        return True

    def _evidence(self, inst: AgentInstance, user_message: str, results: list[AgentResult]) -> Evidence:
        return gather(user_message, results, self.frame, vault_checker(self.ctx_factory(inst.id)))

    def _remove_unsupported(
        self, inst: AgentInstance, user_message: str, upstream: list[AgentResult], result: AgentResult
    ) -> None:
        """Sent back once and still unsupported: it goes, so no later stage can build on it and no reader sees it."""
        kept, removed = without_unsupported(result.text, self._evidence(inst, user_message, [result, *upstream]))
        if not removed:
            return
        result.text = kept.strip()  # no inline note: the UI shows how many claims went, by the badge
        result.removed = [masked(sentence) for sentence in removed]
        result.removed_figures = figures_removed(removed)
        result.verified = False
        result.issues = [*result.issues, f"removed: unsupported source ({len(removed)})"]
        self._emit("agent.step", inst.id, step=f"removed: unsupported source ({len(removed)})")

    def _finish(self, inst: AgentInstance, result: AgentResult, started: float) -> AgentResult:
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        self._emit(
            "agent.done",
            inst.id,
            status=result.status,
            verified=result.verified,
            issues=result.issues,
            elapsed_ms=result.elapsed_ms,
            provider=result.provider,
            model=result.model,
            tokens=result.usage.model_dump(),
            est_cost_usd=result.est_cost_usd,
        )
        return result

    def _finish_specialist(self, spec: AgentType, inst: AgentInstance, result: AgentResult) -> None:
        """What a specialist's answer always carries, whatever the model wrote."""
        frame = self.frame
        if spec.name == "financial_analyst" and frame is not None and frame.non_hire:
            result.text = _analyst_on_a_cost_model(result.text, frame)
        if spec.name == "devils_advocate" and result.text:
            artifact = risk_register(inst.id, result.text.replace(REMOVED_NOTE, "").strip())
            result.artifacts.append(artifact)
            self._emit("agent.artifact", inst.id, artifact=artifact.model_dump(mode="json"))
        if spec.name == "regulatory_tax" and "not legal" not in result.text.lower():
            result.text = f"{result.text} {REGULATORY_NOTE}".strip()
        web_used = any(c["tool"] == "web_search" and not c.get("error") for c in result.tool_calls)
        if spec.name == "market_scout" and not web_used and not self._can_search_web(spec):
            result.text = scout_without_web(result.text, {c.path for c in result.retrieved})
            result.removed = []  # what to find is in its text now: the model's recollections go nowhere, even reworded
        pages = [c for c in result.retrieved if c.chunk_id == "web" and c.path not in result.text]
        if pages and spec.name in ("market_scout", "regulatory_tax"):
            result.text = f"{result.text} Sources: {', '.join(c.path for c in pages[:5])}."

    def _can_search_web(self, spec: AgentType) -> bool:
        return "web_search" in spec.tools and self.router.can_search_web(spec.privacy, spec.name)

    async def _insist_on_scoring(
        self, spec: AgentType, inst: AgentInstance, messages: list[Message], result: AgentResult
    ) -> None:
        """A ranking must come from the routine. A model that ranked in prose is sent back once to call it."""
        scored = any(c["tool"] == "weighted_scoring" and not c.get("error") for c in result.tool_calls)
        if spec.name != "prioritiser" or scored or result.provider in ("rules", ""):
            return
        messages.append(Message.assistant(result.text))
        messages.append(Message.user("Call weighted_scoring now: a ranking must come from the routine."))
        try:
            await self._loop(spec, inst, messages, result)
        except LLMError as exc:
            logger.info("Prioritiser retry failed: {}", exc)

    async def _surface_named_folder(
        self, spec: AgentType, inst: AgentInstance, user_message: str, result: AgentResult
    ) -> None:
        """Asked what "my journal" says, the answer must use the journal.

        Seen live, 2 full eval runs of 3: the search returned the journal and the model cited only another note. The
        same question run alone passed, so the model's choice varies. Code adds the journal's own passage.
        """
        if spec.name != "librarian" or not _NAMES_THE_JOURNAL.search(user_message):
            return
        if any(path.startswith("journal/") for path in named_paths(result.text, {c.path for c in result.retrieved})):
            return
        call = ToolCall(name="search_vault", arguments={"query": user_message, "folder": "journal", "k": 2})
        outcome = await self._call_tool(spec, inst, call, result)
        hits = [a for a in outcome.artifacts if a.citations and a.citations[0].path.startswith("journal/")]
        if hits:
            hit = hits[0]
            quote = f"From your journal: {_plain(hit.data['snippet'])} [{hit.citations[0].path}]"
            result.text = f"{result.text} {quote}".strip()

    async def _write_memo(
        self,
        spec: AgentType,
        inst: AgentInstance,
        user_message: str,
        messages: list[Message],
        upstream: list[AgentResult],
        result: AgentResult,
    ) -> None:
        """The model drafts as JSON, the Verifier checks the prose (one repair turn), and code writes the file."""
        evidence = self._evidence(inst, user_message, [result, *upstream])
        dropped = [v for r in upstream for v in r.removed_figures]
        draft = await self._draft_memo(spec, messages, user_message, result, evidence=evidence, dropped=dropped)
        report = self._check_memo(draft, user_message, result)
        if not report.ok and result.provider != "rules":
            result.attempts = 2
            self._emit("agent.step", inst.id, step="memo sent back by the Verifier: " + "; ".join(report.issues))
            messages.append(Message.assistant(draft.model_dump_json()))
            messages.append(
                Message.user(
                    f"The Verifier rejected your memo: {'; '.join(report.issues)}. Use only numbers from the findings, "
                    "with their meaning. Return the whole memo again."
                )
            )
            draft = await self._draft_memo(
                spec, messages, user_message, result, fallback=draft, evidence=evidence, dropped=dropped
            )
            report = self._check_memo(draft, user_message, result)
        result.verified, result.issues = report.ok, report.issues
        draft = in_your_words(draft, self.frame, _records_for(result, upstream))
        evidence.quoted.extend(_forecast_fact(p).value for p in draft.predictions)
        draft = without_unbacked_figures(draft, _memo_facts(draft, result), user_message, evidence)
        if any(REMOVED_NOTE in line for line in draft.open_numbers):
            result.verified = False
            result.issues = [*result.issues, "removed: unsupported source"]
        self._emit("agent.status", inst.id, status="searching_vault")
        try:
            memo, artifact = await asyncio.to_thread(
                write_memo,
                self.ctx_factory(inst.id),
                draft,
                upstream,
                verified=report.ok and bool(result.verified),
                agent_id=inst.id,
                frame=self.frame,
                message=user_message,
                evidence=evidence,
            )
        except (ValueError, OSError, VaultError) as exc:
            logger.warning("The memo could not be written: {}", exc)
            result.status, result.error = "failed", str(exc)
            result.verified = False
            return
        result.memo = memo
        result.artifacts.append(artifact)
        self._emit("agent.artifact", inst.id, artifact=artifact.model_dump(mode="json"))
        result.text = (
            f"Memo written to {memo.path} (status {memo.status}, review date {memo.review_date}). "
            f"It proposes: {memo.chosen}. Prediction: {memo.predictions[0]}"
        )

    async def _draft_memo(
        self,
        spec: AgentType,
        messages: list[Message],
        user_message: str,
        result: AgentResult,
        fallback: MemoDraft | None = None,
        evidence: Evidence | None = None,
        dropped: list[float] | None = None,
    ) -> MemoDraft:
        try:
            completion = await self.router.complete(
                spec.privacy, messages, json_schema=memo_schema(self.frame), agent_type=spec.name
            )
            self._account(result, completion)
            draft = MemoDraft.model_validate(completion.json())
            if evidence is not None:
                draft = with_real_outcomes(draft, evidence, dropped or [])
            return with_required_fields(draft, user_message, self.frame)
        except (LLMError, ValueError, TypeError) as exc:
            logger.warning(
                "Memo draft from the model failed, using {}: {}", "the last one" if fallback else "rules", exc
            )
            if fallback is not None:
                return fallback
            result.provider, result.model = "rules", ""
            return with_required_fields(rule_draft(user_message), user_message, self.frame)

    @staticmethod
    def _check_memo(draft: MemoDraft, user_message: str, result: AgentResult) -> Any:
        return verify(draft.prose(), _memo_facts(draft, result), [], needs_citations=False, context=user_message)

    async def _look_up_past_decisions(
        self, spec: AgentType, inst: AgentInstance, user_message: str, result: AgentResult
    ) -> None:
        """Checked by code on the founder's own words: a Planner brief can narrow the topic and a model can skip it."""
        if "past_decisions" not in spec.tools:
            return
        outcome = await self._call_tool(
            spec, inst, ToolCall(name="past_decisions", arguments={"query": user_message}), result
        )
        if not outcome.error:
            result.past_decisions = [DecisionRecord(**row) for row in outcome.content["decisions"]]

    async def _search_first(
        self, spec: AgentType, inst: AgentInstance, user_message: str, messages: list[Message], result: AgentResult
    ) -> None:
        """Search the whole vault for the founder's question before the model's first turn.

        Seen live: left to itself, the model limited its only search to one folder and invented an answer from what
        came back. It can still search further, but it always has the results for the question as asked.
        """
        if spec.name != "librarian":
            return
        call = ToolCall(name="search_vault", arguments={"query": user_message})
        outcome = await self._call_tool(spec, inst, call, result)
        messages.append(Message.assistant("", [call]))
        messages.append(Message.tool(call, outcome.for_model()))

    async def _scenario_first(
        self, spec: AgentType, inst: AgentInstance, user_message: str, messages: list[Message], result: AgentResult
    ) -> None:
        """A hire is a what-if. Run it before the model's first turn.

        Seen live, 4 runs of 4: asked "the cost of hiring a designer", the model fetched `headcount_cost`, the whole
        company's payroll, and never ran a scenario.
        """
        hires = hires_in_message(user_message)
        if spec.name != "financial_analyst" or hires is None or (self.frame is not None and self.frame.non_hire):
            return
        call = ToolCall(name="run_scenario", arguments={"new_hires": hires})
        outcome = await self._call_tool(spec, inst, call, result)
        messages.append(Message.assistant("", [call]))
        messages.append(Message.tool(call, outcome.for_model()))

    async def _cost_model_first(
        self, spec: AgentType, inst: AgentInstance, messages: list[Message], result: AgentResult
    ) -> None:
        """A decision that is not a hire has its own costs. The Analyst states them, and shows them on the canvas.

        Seen live: asked about a Dubai office, the model ran a what-if with `new_hires=1` and called that its cost.
        So the what-if tools are not offered for it: code already ran the low, base and high cases.
        """
        frame = self.frame
        if spec.name != "financial_analyst" or frame is None or not frame.non_hire or frame.cost_model is None:
            return
        result.facts.extend(frame.facts)
        artifact = Artifact(
            id=f"art_{uuid.uuid4().hex[:10]}",
            kind="cost_model",
            title=f"Cost model: {frame.subject}",
            agent_id=inst.id,
            data={**frame.cost_model.model_dump(mode="json"), "options": [o.model_dump() for o in frame.options]},
        )
        result.artifacts.append(artifact)
        self._emit("agent.artifact", inst.id, artifact=artifact.model_dump(mode="json"))
        messages.append(
            Message.user(
                "The what-if is already computed for you. Say what this costs and what it does to runway, calling the "
                f"labelled figures assumptions:\n{frame.cost_model.sentence()}"
            )
        )

    def _hidden_tools(self, spec: AgentType) -> frozenset[str]:
        frame = self.frame
        if spec.name == "financial_analyst" and frame is not None and frame.non_hire and frame.cost_model is not None:
            return frozenset({"run_scenario", "run_monte_carlo"})
        return frozenset()

    async def _data_context(self, spec: AgentType) -> str:
        """Tell the Financial Analyst which months exist, so it does not invent a `month` argument."""
        if not {"get_metric", "request_metric"} & set(spec.tools):
            return ""
        try:
            months = await asyncio.to_thread(self.ctx_factory("").finance.metrics.available_months)
        except Exception as exc:  # no data loaded yet: the tools will say so
            logger.debug("No month range for the analyst: {}", exc)
            return "\n\nNo financial data is loaded yet."
        if not months:
            return ""
        return (
            f"\n\nThe data covers {months[0]} to {months[-1]}; the latest month is {months[-1]}. "
            "Leave `month` out to use the latest month."
        )

    def _verify(self, spec: AgentType, inst: AgentInstance, user_message: str, result: AgentResult) -> None:
        self._emit("agent.status", inst.id, status="verifying")
        searched = any(c["tool"] == "search_vault" and not c.get("error") for c in result.tool_calls)
        # The search always runs and dense search always returns something, so "nothing relevant" must stay allowed:
        # sending it back would push the model to cite a source that did not help.
        honest_blank = not result.past_decisions and _SAYS_NOTHING_FOUND.search(result.text) is not None
        cited = not honest_blank and (bool(result.past_decisions) or (searched and bool(result.retrieved)))
        report = verify(
            result.text,
            [*result.known_facts, *result.record_facts],  # a memo's figure is cited to it later, by the source check
            result.retrieved,
            needs_citations=spec.name == "librarian" and cited,
            # Only the founder's own words may supply numbers: a Planner-written brief is LLM text (PRD R1).
            context=user_message,
        )
        result.verified = report.ok
        result.issues = report.issues

    async def _call_tool(
        self, spec: AgentType, inst: AgentInstance, call: ToolCall, result: AgentResult
    ) -> ToolOutcome:
        tool = TOOLS.get(call.name)
        self._emit("agent.status", inst.id, status=tool.status if tool else "thinking")
        self._emit("agent.step", inst.id, step=f"running {call.name}({_args_preview(call.arguments)})")
        if call.name == "web_search" and "web_search" in spec.tools:
            outcome = await self._search_web(spec, inst, call)
        else:
            outcome = await run_tool(call.name, self.ctx_factory(inst.id), call.arguments, spec.tools)
        result.tool_calls.append({"tool": call.name, "arguments": call.arguments, "error": outcome.error})
        result.facts.extend(outcome.facts)
        # The first scenario is the founder's: later ones are the model exploring.
        is_hire = self.frame is None or not self.frame.non_hire
        has_impact = not outcome.error and isinstance(outcome.content.get("impact"), dict)
        if is_hire and result.decision_impact is None and has_impact:
            result.decision_impact = DecisionImpact(**outcome.content["impact"])
        for citation in outcome.citations:
            if citation not in result.retrieved:
                result.retrieved.append(citation)
        for source, texts in outcome.passages.items():
            result.passages.setdefault(source, []).extend(texts)
        for source, texts in outcome.record_passages.items():
            result.record_passages.setdefault(source, []).extend(texts)
        result.record_facts.extend(outcome.record_facts)
        self._emit("agent.tool_call", inst.id, tool=call.name, arguments=call.arguments, error=outcome.error)
        for artifact in outcome.artifacts:
            result.artifacts.append(artifact)
            self._emit("agent.artifact", inst.id, artifact=artifact.model_dump(mode="json"))
        return outcome

    async def _search_web(self, spec: AgentType, inst: AgentInstance, call: ToolCall) -> ToolOutcome:
        query = str(call.arguments.get("query", "")).strip()
        if not query or not self._can_search_web(spec):
            return ToolOutcome({}, error="web search is not available: use the vault")
        try:
            answer = await self.router.web_search(spec.privacy, query, agent_type=spec.name)
        except LLMError as exc:
            return ToolOutcome({}, error=f"web search failed: {type(exc).__name__}")
        return web_outcome(self.ctx_factory(inst.id), answer)

    async def _loop(self, spec: AgentType, inst: AgentInstance, messages: list[Message], result: AgentResult) -> None:
        hidden = self._hidden_tools(spec)
        tools = [
            t
            for t in specs_for(spec.tools)
            if t.name not in hidden and (t.name != "web_search" or self._can_search_web(spec))
        ] or None
        for step in range(self.max_steps + 1):
            final = step == self.max_steps
            self._emit("agent.status", inst.id, status="waiting_cloud" if inst.is_cloud else "thinking")
            completion = await self.router.complete(
                spec.privacy, messages, tools=None if final else tools, agent_type=spec.name
            )
            self._account(result, completion)
            if not completion.tool_calls or final:
                result.text = completion.text.strip()
                return
            messages.append(Message.assistant(completion.text, completion.tool_calls))
            for call in completion.tool_calls:
                outcome = await self._call_tool(spec, inst, call, result)
                messages.append(Message.tool(call, outcome.for_model()))

    @staticmethod
    def _account(result: AgentResult, completion: Completion) -> None:
        result.provider, result.model = completion.provider, completion.model
        result.usage = result.usage + completion.usage
        if result.est_cost_usd is not None:
            result.est_cost_usd = (
                None if completion.est_cost_usd is None else round(result.est_cost_usd + completion.est_cost_usd, 6)
            )
        if completion.fallback_from:
            result.fallback_from = completion.fallback_from

    async def _rules(self, spec: AgentType, inst: AgentInstance, user_message: str, result: AgentResult) -> None:
        """No LLM: run the obvious tool and answer with a template built only from its result."""
        result.provider, result.model = "rules", ""
        if spec.name == "financial_analyst" and result.decision_impact is not None:
            result.text = result.decision_impact.sentence()
        elif spec.name == "financial_analyst" and self._hidden_tools(spec) and self.frame is not None:
            result.text = self.frame.cost_sentence()
        elif spec.name == "financial_analyst":
            metric = rule_metric(f"{inst.brief} {user_message}")
            if metric is None:
                outcome = await self._call_tool(spec, inst, ToolCall(name="metrics_summary"), result)
                rows = outcome.content.get("metrics", [])
                result.text = "; ".join(f"{r['label']}: {_fmt(r['value'], r['unit'])}" for r in rows[:5])
            else:
                outcome = await self._call_tool(
                    spec, inst, ToolCall(name="get_metric", arguments={"name": metric}), result
                )
                c = outcome.content
                result.text = (
                    f"{c['label']}: {_fmt(c['value'], c['unit'], metric)} as of {c['as_of']}."
                    if not outcome.error
                    else f"Could not compute {metric}: {outcome.error}"
                )
        elif spec.name == "librarian":
            outcome = await self._call_tool(
                spec, inst, ToolCall(name="search_vault", arguments={"query": inst.brief, "k": 3}), result
            )
            hits = [a for a in outcome.artifacts if a.citations][:3]
            result.text = (
                " ".join(f"{_plain(a.data['snippet'])} [{a.citations[0].path}]" for a in hits)
                if hits
                else "Nothing relevant was found in the vault."
            )
        elif spec.name in ("market_scout", "regulatory_tax"):
            outcome = await self._call_tool(
                spec, inst, ToolCall(name="search_vault", arguments={"query": inst.brief, "k": 2}), result
            )
            hits = [a for a in outcome.artifacts if a.citations][:2]
            result.text = (
                " ".join(f"{_plain(a.data['snippet'])} [{a.citations[0].path}]" for a in hits)
                if hits
                else RULE_TEXT[spec.name]
            )
        elif spec.name == "revenue_customer":
            lines = []
            for metric in ("mrr", "logo_churn", "nrr"):
                outcome = await self._call_tool(
                    spec, inst, ToolCall(name="request_metric", arguments={"name": metric}), result
                )
                if not outcome.error:
                    c = outcome.content
                    lines.append(f"{c['label']}: {_fmt(c['value'], c['unit'])}")
            result.text = "; ".join(lines) + ("." if lines else "")
        elif spec.name in RULE_TEXT:
            result.text = RULE_TEXT[spec.name]
        if not result.text:
            result.status, result.error = "failed", "the language model is unavailable and no rule applies"


_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_HIRES_RE = re.compile(
    r"\bhir(?:e|ing)\s+(?:(?:another|more|new|additional)\s+)?"
    # "hire a few", "hiring a good idea" and "hire 20% more" do not say how many people.
    r"(a(?!\s+(?:couple|few|lot|bit|good|bad|great|smart|wise)\b)|an|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|\d{1,3}(?!\s*%))\b"
    r"|\bhir(?:e|ing)\s+(another)\b",
    re.I,
)


def hires_in_message(message: str) -> int | None:
    """How many people the founder is thinking of hiring, when they say. "Should we hire more?" says nothing."""
    match = _HIRES_RE.search(message)
    if match is None:
        return None
    if match.group(2):
        return 1
    word = match.group(1).lower()
    return int(word) if word.isdigit() else _NUMBER_WORDS[word]


_NAMES_THE_JOURNAL = re.compile(r"\b(my|our|the) journal\b", re.I)


def _memo_facts(draft: MemoDraft, result: AgentResult) -> list[Fact]:
    """The team's numbers, plus the memo's own forecasts: a stated belief, not a financial figure."""
    forecasts = [_forecast_fact(p) for p in draft.predictions]
    return [*result.known_facts, *result.record_facts, *forecasts]  # a figure quoted from a memo on record is cited


def _forecast_fact(prediction: MemoPrediction) -> Fact:
    return Fact(round(prediction.probability * 100, 2))


def _written_by_code(impact: DecisionImpact | None) -> Callable[[list[ClaimIssue]], str]:
    """What replaces a sentence whose figure had the wrong meaning: the impact, or the figure with its own label."""

    def write(issues: list[ClaimIssue]) -> str:
        if impact is not None:
            return impact.sentence()
        written = dict.fromkeys(i.fact.sentence() for i in issues if i.fact is not None)
        return " ".join(written) or "A statement here was removed: its figure did not match what it described."

    return write


def _replace_wrong_claims(result: AgentResult, user_message: str) -> None:
    """Sent back once and still wrong: not verified, and the sentence is replaced by one written in code."""
    impact = result.decision_impact or result.inherited_impact
    result.text, _ = repair_claims(result.text, result.known_facts, user_message, _written_by_code(impact))


_RESTATES_THE_MODEL = re.compile(
    r"\b(?:low|base|high)[- ]case\b|\bup-?front\b|\bcost model\b|"
    r"\b(?:office|this|it|that|option|region|launch|change|product|hire)\b[^.!?]*\b(?:costs?|runway)\b",
    re.I,
)


def _analyst_on_a_cost_model(text: str, frame: DecisionFrame) -> str:
    """Code's sentence on the cost, plus anything else the Analyst found.

    Seen live: asked to restate the cases, the model wrote that the office "extends the low-case runway".
    """
    sentence = frame.cost_sentence()
    if not sentence or frame.cost_model is None:
        return f"{text} {sentence}".strip()
    others = "".join(p for p in split_sentences(text) if not _RESTATES_THE_MODEL.search(p)).strip()
    return f"{sentence} {others}".strip()


def _records_for(result: AgentResult, upstream: list[AgentResult]) -> list[DecisionRecord]:
    return [*result.past_decisions, *_team_decisions(upstream)]


def _memo_brief(frame: DecisionFrame) -> str:
    """What the Memo Writer chooses from. Code holds the costs; the model holds the judgement."""
    lines = [f"Today is {dt.date.today().isoformat()}."]
    if frame.options:
        lines.append("Options, costed in code. Choose exactly one for `chosen`, using its exact name:")
        lines.extend(f"- {o.line(frame.currency)}" for o in frame.options)
    sentences = [g.sentence for g in frame.goals if g.status in ("moves_away", "moves_towards", "open_question")]
    if sentences:
        lines.append("Goal check, computed in code; weigh it in your choice: " + " ".join(sentences))
    return "\n".join(lines)


def team_impact(results: list[AgentResult]) -> DecisionImpact | None:
    return next((r.decision_impact for r in results if r.decision_impact is not None), None)


def impact_stated(text: str, impact: DecisionImpact) -> bool:
    """The answer gives the runway change (or the new runway) and the cost, as those figures."""
    figures = extract_figures(text)
    runway = [v for v in (impact.runway_change_months, impact.scenario_runway_months) if v is not None]
    cost = [v for v in (impact.cost_per_hire_monthly, impact.monthly_cost_delta) if v]
    said_runway = not runway or any(number_supported(f, runway) for f in figures)
    said_cost = not cost or any(number_supported(f, cost) for f in figures)
    return said_runway and said_cost


def _decisions_context(result: AgentResult) -> str:
    if not result.past_decisions:
        return ""
    lines = "\n".join(f"- {record.summary()}" for record in result.past_decisions)
    return f"\n\nPast decisions on record for this topic (from the vault, exact):\n{lines}"


def _month_names(iso: str) -> list[str]:
    month = int(iso[5:7]) if iso[5:7].isdigit() else 0
    return [calendar.month_name[month], calendar.month_abbr[month]] if 1 <= month <= 12 else []


def _states_month(iso: str, text: str) -> bool:
    """2026-09-15, 2026-09, September or Sep, capitalised ("you may want" is not May).

    Not inside a longer word: the "2026-09" of a [[2026-09-hire]] link states no date.
    """
    forms = [iso, iso[:7], *_month_names(iso)]
    return any(re.search(rf"(?<![\w-]){re.escape(form)}(?![\w-])", text) for form in forms)


def _states_day(iso: str, text: str) -> bool:
    """2026-12-15, 15 Dec, December 15th. A kill criterion's "by December" does not state a 15 December review."""
    if re.search(rf"(?<![\w-]){re.escape(iso)}(?![\w-])", text):
        return True
    day = iso[8:10].lstrip("0")
    if not day.isdigit():
        return _states_month(iso, text)
    ordinal = rf"{day}(?:st|nd|rd|th)?"
    return any(
        re.search(rf"\b{ordinal}\s+(?:of\s+)?{name}\b|\b{name}\.?\s+{ordinal}\b", text) for name in _month_names(iso)
    )


def _states_prediction(predictions: list[str], text: str) -> bool:
    """The prediction's own words, or its percentage named as a prediction: "gross margin is 70%" does not count."""
    joined = " ".join(predictions)
    words = set(bm25_tokens(joined))
    if words and len(words & set(bm25_tokens(text))) >= KILL_CRITERIA_OVERLAP * len(words):
        return True
    percent = re.search(r"(\d+(?:\.\d+)?)\s?(?:%|percent\b)", joined)
    if percent is None:
        return False
    named = re.search(r"predict|chance|probab|likel|confiden", text) is not None
    return named and re.search(rf"(?<![\d.]){re.escape(percent.group(1))}\s?(?:%|percent\b)", text) is not None


def _states_kill_criteria(criteria: list[str], text: str) -> bool:
    """Most of the criterion's own words: naming "a kill criterion" without its condition gives the founder nothing."""
    words = set(bm25_tokens(" ".join(criteria)))
    return len(words & set(bm25_tokens(text))) >= KILL_CRITERIA_OVERLAP * len(words)


def _missing_facts(text: str, record: DecisionRecord) -> tuple[list[str], bool]:
    """(the facts of this decision that `text` does not state, whether it states any of them)."""
    # The 2026-09 in "decisions/2026-09-hire.md" states no date.
    plain = PATH_RE.sub(" ", text.replace(record.path, " "))
    lowered = plain.lower()
    wanted: list[tuple[str, bool]] = []
    if record.decided:
        wanted.append((f"decided {record.decided}", _states_month(record.decided, plain)))
    if not record.is_decided:
        wanted.append((f"status {record.status}", record.status.lower() in lowered))
    if record.kill_criteria:
        criteria = "; ".join(c.rstrip(".") for c in record.kill_criteria)
        wanted.append((f"kill criteria: {criteria}", _states_kill_criteria(record.kill_criteria, lowered)))
    if record.predictions:
        wanted.append((f"prediction: {'; '.join(record.predictions)}", _states_prediction(record.predictions, lowered)))
    if record.review_date:
        wanted.append((f"review date {record.review_date}", _states_day(record.review_date, plain)))
    if not wanted:  # a note with no fields: all an answer can do is name it
        return ([record.title], False) if record.title.lower() not in lowered else ([], True)
    return [fact for fact, stated in wanted if not stated], any(stated for _, stated in wanted)


def decision_note(text: str, record: DecisionRecord, *, needs_path: bool, lead: str) -> str:
    """What `text` must add for this decision: only the missing facts, or the whole record if it states none."""
    missing, any_stated = _missing_facts(text, record)
    path_missing = needs_path and record.path.lower() not in text.lower()
    if not any_stated:
        return f"{lead} {record.summary()}"
    if not missing and not path_missing:
        return ""
    source = f" [{record.path}]" if path_missing else ""
    return f'On record for "{record.title}"{source}' + (f": {'; '.join(missing)}." if missing else ".")


def decision_covered(text: str, record: DecisionRecord, *, needs_path: bool) -> bool:
    return not decision_note(text, record, needs_path=needs_path, lead="")


def _surface_decisions(result: AgentResult) -> None:
    """A small model can ignore what it was told, so code guarantees that the facts of a past decision are stated."""
    notes = [decision_note(result.text, r, needs_path=True, lead="On record:") for r in result.past_decisions]
    result.text = " ".join([result.text, *(n for n in notes if n)]).strip()


def _keep_used_sources(result: AgentResult) -> None:
    """Citations are the sources the answer names, not everything a search happened to return."""
    used = named_paths(result.text, {c.path for c in result.retrieved})
    result.citations = [c for c in result.retrieved if c.path in used]
    result.artifacts = [a for a in result.artifacts if a.kind != "citation" or any(c.path in used for c in a.citations)]


def _fmt(value: Any, unit: str, metric: str = "") -> str:
    if value is None:
        return "n/a"
    if unit == "months":
        return f"{value} months"
    if unit in ("ratio",):
        # LTV:CAC is a multiple. The other ratios read as a share: "72.13 %", not "0.7213".
        return f"{value}" if metric == "ltv_cac" else f"{float(value) * 100:.2f} %"
    if unit == "percent":
        return f"{value} %"
    if unit == "count":
        return f"{value}"
    if re.fullmatch(r"[A-Z]{3}", unit):
        return f"{value:,.2f} {unit}" if isinstance(value, int | float) else f"{value} {unit}"
    return f"{value} {unit}"


def _month_label(iso: str) -> str:
    """ "2027-09" as "September 2027". Anything else stays as it is."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", iso):
        return iso
    return f"{calendar.month_name[int(iso[5:])]} {iso[:4]}"


def metric_sentence(content: dict[str, Any], metric: str, currency: str = "USD") -> str:
    """The answer to a single-metric question, written by code from the routine's own result."""
    label, value, unit, as_of = content["label"], content["value"], content["unit"], content["as_of"]
    if value is None:
        return (
            f"{label} cannot be computed from the data as of {_month_label(as_of)}. {content.get('note') or ''}".strip()
        )
    written = format_money(float(value), unit) if re.fullmatch(r"[A-Z]{3}", unit) else _fmt(value, unit, metric)
    sentence = f"{label} is {written} as of {_month_label(as_of)}"
    detail = content.get("detail") or {}
    if metric == "runway" and detail.get("closing_cash") is not None and detail.get("net_burn") is not None:
        cash, burn = format_money(detail["closing_cash"], currency), format_money(detail["net_burn"], currency)
        zero = (
            f", so cash reaches zero in {_month_label(detail['zero_cash_month'])}"
            if detail.get("zero_cash_month")
            else ""
        )
        sentence += f": closing cash is {cash}, with a net burn of {burn} per month{zero}"
    return f"{sentence}."


def probing_question(text: str) -> str:
    """One short question with no figure in it, or nothing. Code has already given the number."""
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    words = re.findall(r"[a-z']+", line.lower())
    if not line.endswith("?") or len(split_sentences(line)) != 1 or len(line.split()) > MAX_QUESTION_WORDS:
        return ""
    if re.search(r"[\d$€£₹%]", line) or extract_figures(line) or set(words) & _SPELLED_NUMBERS:
        return ""
    return line


def _plain(snippet: str) -> str:
    """A search snippet as one line of prose (no Markdown heading marks, no line breaks)."""
    return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*#+\s*", "", snippet)).strip()


def _args_preview(arguments: dict[str, Any]) -> str:
    text = ", ".join(f"{k}={json.dumps(v, default=str)}" for k, v in arguments.items())
    return text if len(text) <= 80 else text[:77] + "..."


def findings_for_advisor(results: list[AgentResult], frame: DecisionFrame | None = None) -> str:
    blocks: list[str] = [*frame.findings_block()] if frame is not None else []
    impact = team_impact(results)
    for r in results:
        # What failed is already out of the text, so naming its figure or source here would only bring it back.
        kept = [i for i in r.issues if _names_nothing(i)]
        wrong = any(i.startswith("wrong meaning") for i in r.issues)
        replaced = ["a sentence was replaced by one written in code"] if wrong else []
        flag = "" if r.verified else f" [UNVERIFIED: {'; '.join(kept + replaced)}]"
        if r.status != "done":
            blocks.append(f"- {r.name}: failed ({r.error}).")
            continue
        blocks.append(f"- {r.name}{flag}: {_short(r.text)}")
        # With a computed impact, a raw total such as total payroll only invites being called the decision's cost.
        for art in [] if impact is not None else r.artifacts:
            if art.kind == "metric_card":
                d = art.data
                blocks.append(f"  * {d.get('label')}: {d.get('value')} {d.get('unit')} (as of {d.get('as_of')})")
    if impact is not None:
        blocks.append("Impact of this decision, computed in code (state this; no other total is its cost):")
        blocks.append(f"- {impact.sentence()}")
    records = _team_decisions(results)
    if records:
        blocks.append("Past decisions on this topic, already on record (lead with these):")
        blocks.extend(f"- {record.summary()}" for record in records)
    return "\n".join(blocks) if blocks else "(no findings)"


def _names_nothing(issue: str) -> bool:
    if issue.startswith("removed: unsupported source"):
        return True
    return not extract_figures(issue) and not cited_sources(issue) and not issue.startswith("wrong meaning")


def _short(text: str, limit: int = 900) -> str:
    """A team's findings must fit an 8k context, however many agents ran."""
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _team_decisions(results: list[AgentResult]) -> list[DecisionRecord]:
    return list({record.path: record for r in results for record in r.past_decisions}.values())


def advisor_decision_note(answer: str, results: list[AgentResult]) -> str:
    """What the Advisor's reply must add so that no past decision on the topic goes unmentioned."""
    parts: list[str] = []
    for record in _team_decisions(results):
        lead = "You already decided this:" if record.is_decided else "Already on record:"
        note = decision_note(answer, record, needs_path=False, lead=lead)
        if note:
            ignored = note.startswith(lead)
            parts.append(f" {note} {record.follow_up_question()}" if ignored else f" {note}")
    return "".join(parts)


def decision_lead(frame: DecisionFrame | None, records: list[DecisionRecord], chosen: str = "") -> str:
    """A decision answer opens with the proposed option, then the full model: the same order as the lead card.

    Written by code, so the figures are the table's and the signs are never doubled ("reducing runway by -2.07").
    A proposed memo already on record is a draft to update, so the founder is asked what has changed.
    """
    if frame is None or not frame.options:
        return ""
    wanted = chosen or frame.default_option
    proposed = next((o for o in frame.options if o.name == wanted), None)
    full = next((o for o in frame.options if o.is_full), None)
    model = frame.cost_model
    parts: list[str] = []
    if proposed is not None:
        parts.append(f"Proposed: {_option_words(proposed, frame.currency)}.")
    if model is not None and (proposed is None or not proposed.is_full):
        base = model.case("base")
        name = full.name if full is not None else model.subject
        runway = _runway_words(base.base_runway_months, base.scenario_runway_months, base.runway_change_months)
        away = next((g.goal for g in frame.goals if g.status == "moves_away"), "")
        goal = f', which moves you away from your goal "{away}"' if away else ""
        parts.append(
            f"The full model, {name}, is {model.money(base.one_off)} up front and {model.money(base.monthly)} a month"
            f"{runway}{goal}; all of these are assumptions to confirm ({ASSUMPTION_LABEL})."
        )
    elif parts:
        parts.append(f"These are assumptions to confirm ({ASSUMPTION_LABEL}).")
    drafts = [r for r in records if not r.is_decided]
    if drafts:
        # A proposal never started, so it is not asked about its kill criteria: only what has changed.
        record = drafts[0]
        when = f" from {record.drafted_on()}" if record.drafted_on() else ""
        parts.append(
            f"You already have a {record.status} memo on this{when} [{record.path}]: what has changed since you "
            "drafted it?"
        )
    return " ".join(parts)


def _runway_words(before: float | None, after: float | None, change: float | None) -> str:
    if before is None or after is None or change is None:
        return "; runway does not run out in the model"
    return f", moving projected runway from {before:.2f} to {after:.2f} months ({change:+.2f})"


def _option_words(option: OptionCost, currency: str) -> str:
    if not option.modelled:
        return f"{option.name} (its cost is not modelled)"
    cost = (
        f"{format_money(option.one_off, currency)} up front and {format_money(option.monthly, currency)} a month"
        if option.one_off
        else f"{format_money(option.monthly, currency)} a month"
    )
    effect = (
        "runway does not run out in the model"
        if option.runway_change_months is None
        else f"runway {option.runway_change_months:+.2f} months"
    )
    return f"{option.name}, {cost}, {effect}"


# A decision answer: code's lead, then at most this many of the model's sentences (founder review 18).
DECISION_PROSE_SENTENCES = 2
# A question about whether the drafted memo's target will be met: with a draft on record, the founder is asked what
# has changed since it was drafted instead (founder review, 18).
_TARGET_QUESTION = re.compile(
    r"\b(?:expected to|likely to|realistic\w*|going to)\b[^?]*\b(?:meet|hit|reach|achieve)\b[^?]*\?", re.I
)
_KILL_QUESTION = re.compile(r"\b(?:kill criteri\w*|on track|meet(?:ing)? (?:its|the) (?:targets?|criteria))\b", re.I)


class _SentenceGate:
    """Checks the Advisor's reply one sentence at a time, before the founder sees it (the reply streams)."""

    def __init__(
        self,
        facts: list[Fact],
        message: str,
        impact: DecisionImpact | None,
        issues: list[str],
        frame: DecisionFrame | None = None,
        records: list[DecisionRecord] | None = None,
        chosen: str = "",
        evidence: Evidence | None = None,
    ) -> None:
        self.facts, self.message, self.impact, self.issues = facts, message, impact, issues
        self.frame, self.records, self.chosen = frame, records or [], chosen
        self.evidence = evidence
        self.pending = ""
        self.written: set[str] = set()
        self.noted = False
        self.max_sentences: int | None = None  # a decision answer stays short
        self.said: list[str] = []  # what went out, to drop a sentence said twice
        self.lead_figures: list[float] = []  # code's lead already gave these: a sentence of only these repeats it
        self.draft_on_record = False  # a proposed memo is on record: no question about its kill criteria

    def _budgeted(self, text: str) -> str:
        """No sentence twice, and no more than the budget."""
        kept: list[str] = []
        for piece in split_sentences(text):
            key = re.sub(r"\W+", " ", piece).strip().lower()
            if not key:
                kept.append(piece)
                continue
            if key in self.said or (self.max_sentences is not None and len(self.said) >= self.max_sentences):
                continue
            figures = extract_figures(piece)
            if figures and self.lead_figures and all(number_supported(f, self.lead_figures) for f in figures):
                continue  # the proposal and the full model, said again in the model's words
            if self.draft_on_record and (_KILL_QUESTION.search(piece) or _TARGET_QUESTION.search(piece)):
                continue
            self.said.append(key)
            kept.append(piece)
        out = "".join(kept)
        return out if out.strip() else ""  # nothing left: no stray spaces between what was said

    def _without_unsupported(self, text: str) -> str:
        """A figure with no source never reaches the founder, not even inside a question."""
        if self.evidence is None:
            return text
        kept, removed = without_unsupported(text, self.evidence)
        if not removed:
            return text
        self.issues.append(f"advisor: removed: unsupported source ({len(removed)})")
        self.noted = True
        if not kept.strip():
            return ""
        trailing = text[len(text.rstrip()) :]
        return kept.strip() + (trailing or " ")

    def _checked(self, text: str) -> str:
        text = guarded(text, self.frame, self.records, self.written, self.chosen)
        text = self._without_unsupported(text)
        if not text.strip():
            return ""
        fixed, failed = repair_claims(text, self.facts, self.message, _written_by_code(self.impact), self.written)
        self.issues.extend(f"advisor: wrong meaning: {i.message}" for i in failed)
        if not failed:
            return self._budgeted(text)
        trailing = text[len(text.rstrip()) :]
        return self._budgeted(fixed + trailing)

    def _budgeted_notes(self, note: str) -> str:
        """Code's own notes always go out, but never a sentence the reply has already said."""
        kept: list[str] = []
        for piece in split_sentences(note):
            key = re.sub(r"\W+", " ", piece).strip().lower()
            if key and key in self.said:
                continue
            self.said.append(key)
            kept.append(piece)
        out = "".join(kept)
        return f" {out.strip()}" if out.strip() else ""

    def feed(self, delta: str) -> str:
        """Any sentences `delta` completed, checked. The unfinished one waits."""
        self.pending += delta
        last_end = None
        for match in re.finditer(r"[.!?]\s+", self.pending):
            last_end = match.end()
        if last_end is None:
            return ""
        ready, self.pending = self.pending[:last_end], self.pending[last_end:]
        return self._checked(ready)

    def flush(self) -> str:
        ready, self.pending = self.pending, ""
        return self._checked(ready) if ready else ""


def _chosen_in(results: list[AgentResult]) -> str:
    return next((r.memo.chosen for r in results if r.memo is not None), "")


def advisor_memo_note(answer: str, results: list[AgentResult], frame: DecisionFrame | None = None) -> str:
    """A memo that was written is never a surprise: the reply names it and its review date."""
    memo = next((r.memo for r in results if r.memo is not None), None)
    if memo is None or (memo.path in answer and memo.review_date in answer):
        return ""
    option = next((o for o in frame.options if o.name == memo.chosen), None) if frame is not None else None
    if option is not None and frame is not None and option.modelled:
        # What is proposed may not be what the cost sentence above priced: name its own cost.
        line = option.line(frame.currency)
        proposes = "" if line in answer or f"Proposed: {memo.chosen}" in answer else f" The memo proposes {line}"
    else:
        proposes = f" The memo proposes {memo.chosen}." if memo.chosen and memo.chosen not in answer else ""
    return f"{proposes} It is at {memo.path}, for review on {memo.review_date}."


_SAYS_AWAY = re.compile(r"\b(away|against|further from|short of|hurts?|conflicts?)\b", re.I)


def advisor_frame_note(answer: str, frame: DecisionFrame | None) -> str:
    """The cost of a decision that is not a hire, and what it does to the goals: said plainly by code."""
    if frame is None:
        return ""
    notes: list[str] = []
    model = frame.cost_model
    if frame.non_hire:
        said = model is not None and format_money(model.case("base").monthly, model.currency) in answer
        if not said:
            notes.append(frame.cost_sentence())
        elif model is not None and model.assumption_count and "assum" not in answer.lower():
            notes.append("Those costs are assumptions: confirm them.")
    moving_away = {g.goal for g in frame.goals if g.status == "moves_away"}
    for sentence in frame.goal_sentences():
        goal = sentence[sentence.find('"') + 1 : sentence.rfind('"')]
        # Quoting the goal is not telling the founder this moves away from it. Seen in a rule answer's vault passage.
        told = (
            any(names_goal(goal, s) and _SAYS_AWAY.search(s) for s in split_sentences(answer))
            if goal in moving_away
            else names_goal(goal, answer)
        )
        if goal and not told:
            notes.append(sentence)
    return "".join(f" {note}" for note in notes if note)


def advisor_impact_note(answer: str, plan_: Plan, results: list[AgentResult]) -> str:
    impact = team_impact(results) if plan_.intent == "decision" else None
    if impact is None:
        return ""
    if not impact_stated(answer, impact):
        return f" {impact.sentence()}"
    # Seen live: "Hiring a designer costs $11,423.62". That is the company's average, not a quote for this role.
    if impact.cost_per_hire_monthly and impact.cost_is_company_average and "average" not in answer.lower():
        each = format_money(impact.cost_per_hire_monthly, impact.currency)
        return f" The {each} is the company's average loaded monthly cost per person, not a quote for this role."
    return ""


async def _advise_metric(
    router: LLMRouter, user_message: str, result: AgentResult, issues: list[str], evidence: Evidence
) -> AsyncIterator[StreamChunk]:
    """The number first and at once, then at most one short question from the model, if it comes in time."""
    spec = REGISTRY["advisor"]
    yield StreamChunk(delta=result.text)
    system = (PROMPTS_DIR / "advisor_metric_question.md").read_text(encoding="utf-8")
    messages = [Message.system(system), Message.user(f"The founder asked: {user_message}")]
    usage, used, model, question = Usage(), "rules", "", ""
    try:
        completion = await asyncio.wait_for(
            router.complete(spec.privacy, messages, agent_type=spec.name), timeout=METRIC_QUESTION_TIMEOUT_S
        )
        usage, used, model = completion.usage, completion.provider, completion.model
        question = probing_question(completion.text)
    except (LLMError, TimeoutError) as exc:
        logger.info("No question after a metric answer: {}", repr(exc))
    if question:
        gate = _SentenceGate(result.known_facts, user_message, None, issues, evidence=evidence)
        question = gate._checked(question).strip()
    if question:
        yield StreamChunk(delta=f" {question}")
    text = f"{result.text} {question}".strip()
    yield StreamChunk(done=True, completion=Completion(text=text, provider=used, model=model, usage=usage))


async def advise(
    router: LLMRouter,
    user_message: str,
    plan_: Plan,
    results: list[AgentResult],
    issues: list[str] | None = None,
    exists: Callable[[str], bool] | None = None,
) -> AsyncIterator[StreamChunk]:
    """The Advisor streams its reply, sentence by sentence, each one checked before it goes out.

    A sentence that attaches a figure to the wrong quantity or unit is replaced by one written in code and added to
    `issues`. Without an LLM it yields a template answer built from the findings.
    """
    spec = REGISTRY["advisor"]
    frame = plan_.frame
    if len(results) == 1 and results[0].written_by_code and results[0].verified:
        evidence = gather(user_message, results, frame, exists)
        async for chunk in _advise_metric(router, user_message, results[0], [] if issues is None else issues, evidence):
            yield chunk
        return
    findings = findings_for_advisor(results, frame)
    context = (
        f"Founder's message: {user_message}\nIntent: {plan_.intent}"
        + (
            f"; decision type: {plan_.decision_type}; reversibility: {plan_.reversibility}"
            if plan_.decision_type
            else ""
        )
        + f"\n\nTeam findings:\n{findings}"
    )
    # Only when there is one: told about past decisions in general, the model invented one ("you decided in August").
    decisions_rule = (PROMPTS_DIR / "advisor_past_decisions.md").read_text(encoding="utf-8")
    system = spec.prompt() + (decisions_rule if _team_decisions(results) else "")
    if team_impact(results) is not None:
        system += (PROMPTS_DIR / "advisor_decision_impact.md").read_text(encoding="utf-8")
    if frame is not None and frame.non_hire and frame.cost_model is not None:
        system += (PROMPTS_DIR / "advisor_cost_model.md").read_text(encoding="utf-8")
    records = _team_decisions(results)
    lead = decision_lead(frame, records, _chosen_in(results))
    if lead:
        context += (
            f"\n\nAlready said to the founder, first, by code: {lead}\nDo not repeat it, the goal or the proposal. "
            f"Add at most {DECISION_PROSE_SENTENCES} short sentences: the main trade-off, and one question."
        )
    messages = [Message.system(system), Message.user(context)]
    sent: list[str] = []
    facts = [*(fact for r in results for fact in r.facts), *(frame.facts if frame else [])]
    claims = issues if issues is not None else []
    evidence = gather(user_message, results, frame, exists, quoted_text=findings, code_lines=[lead] if lead else ())
    gate = _SentenceGate(
        facts, user_message, team_impact(results), claims, frame, records, _chosen_in(results), evidence
    )
    if lead:
        gate.max_sentences = DECISION_PROSE_SENTENCES
        gate.said.extend(re.sub(r"\W+", " ", p).strip().lower() for p in split_sentences(lead))
        gate.max_sentences += len(gate.said)
        gate.lead_figures = [f.value for f in extract_figures(lead)]
        gate.draft_on_record = any(not r.is_decided for r in records)
        sent.append(f"{lead} ")
        yield StreamChunk(delta=f"{lead} ")
    try:
        async for chunk in router.stream(spec.privacy, messages, agent_type=spec.name):
            ready = gate.feed(chunk.delta) if chunk.delta else ""
            if ready:
                sent.append(ready)
                yield StreamChunk(delta=ready)
            if chunk.done and chunk.completion is not None:
                ready = gate.flush()
                if ready:
                    sent.append(ready)
                    yield StreamChunk(delta=ready)
                # Everything the model wrote was removed: the team's checked findings are still an answer.
                if gate.noted and not "".join(sent).replace(REMOVED_NOTE, "").strip():
                    findings_text = " ".join(r.text for r in results if r.status == "done" and r.text)
                    if findings_text:
                        sent.append(f" {findings_text}")
                        yield StreamChunk(delta=f" {findings_text}")
                # With code's lead, a proposed memo on record is already named and asked about.
                note = "" if lead else advisor_decision_note("".join(sent), results)
                note += advisor_impact_note("".join(sent) + note, plan_, results)
                note += advisor_frame_note("".join(sent) + note, frame)
                note += advisor_memo_note("".join(sent) + note, results, frame)
                note = gate._budgeted_notes(note) if lead else note
                if note:
                    sent.append(note)
                    yield StreamChunk(delta=note)
                text = "".join(sent)
                yield StreamChunk(done=True, completion=chunk.completion.model_copy(update={"text": text}))
    except LLMError as exc:
        provider = router.primary(spec.privacy)
        ready = gate.flush()
        if ready:
            sent.append(ready)
            yield StreamChunk(delta=ready)
        if any(sent[1:] if lead else sent):
            # The founder already saw part of the reply: end it honestly instead of appending a second answer.
            logger.warning("Advisor stream broke after {} chunks: {}", len(sent), exc)
            note = " (The reply was cut off; see the findings.)" + advisor_decision_note("".join(sent), results)
            yield StreamChunk(delta=note)
            text = "".join(sent) + note
            yield StreamChunk(done=True, completion=Completion(text=text, provider=provider.name, model=provider.model))
            return
        logger.warning("Advisor LLM unavailable, using the template answer: {}", exc)
        text = guarded(template_answer(results), frame, records, chosen=_chosen_in(results))
        shown = lead + " " + text if lead else text
        text += advisor_impact_note(shown, plan_, results)
        text += advisor_frame_note(lead + " " + text if lead else text, frame)
        text += advisor_memo_note(lead + " " + text if lead else text, results, frame)
        if lead:
            gate.max_sentences = None  # the findings are the answer here: only what the lead already said goes
            text = gate._budgeted(text)
        yield StreamChunk(delta=text)
        text = f"{lead} {text}" if lead else text
        yield StreamChunk(
            done=True, completion=Completion(text=text, provider="rules", model="", fallback_from=provider.name)
        )


def template_answer(results: list[AgentResult]) -> str:
    done = [r for r in results if r.status == "done" and r.text]
    if not done:
        return "The language model is unavailable and there are no findings yet. Check that Ollama is running."
    return " ".join(r.text for r in done) + " (Answer assembled without the language model.)"


AwaitableFactory = Callable[[], Awaitable[Any]]
