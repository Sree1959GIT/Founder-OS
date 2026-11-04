"""Agent runtime: the tool-calling loop, the Planner, the Advisor and rule-based fallbacks.

Every LLM call goes through the `LLMRouter` (privacy routing and fallback). When the local LLM is down, the agents
fall back to rules (PRD R3): keyword intent, a direct metric routine or vault search, and a template answer built
only from tool results.
"""

from __future__ import annotations

import asyncio
import calendar
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from app.agents.events import Artifact, Citation, EventBus
from app.agents.registry import PROMPTS_DIR, REGISTRY, AgentType, spawnable_types
from app.agents.tools import TOOLS, DecisionImpact, ToolContext, ToolOutcome, run_tool, specs_for
from app.agents.verifier import (
    PATH_RE,
    ClaimIssue,
    Fact,
    extract_figures,
    named_paths,
    number_supported,
    repair_claims,
    verify,
)
from app.decision.base import DecisionError, DecisionService
from app.engine.hybrid_rag import bm25_tokens
from app.engine.lineage import Lineage
from app.llm.base import Completion, LLMError, Message, StreamChunk, ToolCall, Usage
from app.llm.router import LLMRouter
from app.vault.decisions import DecisionRecord

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
    r"past decisions?)\b",
    re.I,
)
_ASKS_TO_DECIDE = re.compile(r"\b(should|shall) (we|i)\b", re.I)
_ASKS_WHAT_WAS_DECIDED = re.compile(r"\b(what (did|have) (we|i) (decide|decided)|past decisions?)\b", re.I)
_SAYS_NOTHING_FOUND = re.compile(
    r"\b(nothing|no (relevant|information|notes?|mention|details?|sources?)|not (found|mentioned|covered)|"
    r"(do|does|did) not (say|mention|cover|contain))\b",
    re.I,
)
_CHITCHAT = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b[\s!.?]*$", re.I)

KILL_CRITERIA_OVERLAP = 0.6

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


class Plan(BaseModel):
    intent: Intent
    decision_type: str | None = None
    reversibility: Literal["one_way", "two_way"] | None = None
    team: list[AgentInstance] = Field(default_factory=list)
    planner: str = Field(description="How the plan was made: rules, decision model or LLM")
    intent_decision_id: str | None = None


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
    facts: list[Fact] = Field(default_factory=list, exclude=True)
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


def _instance(agent_type: str, brief: str, router: LLMRouter, index: int = 1) -> AgentInstance:
    spec = REGISTRY[agent_type]
    provider = router.primary(spec.privacy, needs_tools=bool(spec.tools))
    suffix = f" #{index}" if index > 1 else ""
    return AgentInstance(
        type=agent_type,
        name=f"{spec.title}{suffix}",
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
        return Plan(intent=intent, team=team, planner=how, intent_decision_id=decision_id)
    if intent == "knowledge":
        team = _team([("librarian", message)], router)
        return Plan(intent=intent, team=team, planner=how, intent_decision_id=decision_id)
    return await _plan_decision(message, router, how, decision_id)


def _default_decision_plan(message: str, router: LLMRouter, how: str, decision_id: str | None) -> Plan:
    tasks = [
        ("financial_analyst", f"Numbers that matter for this decision: {message}"),
        ("librarian", f"What the notes and past decisions say about: {message}"),
    ]
    return Plan(intent="decision", team=_team(tasks, router), planner=how, intent_decision_id=decision_id)


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
                "maxItems": 4,
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
            for t in data.get("tasks", [])[:4]
            if isinstance(t, dict) and t.get("agent_type") in types
        ]
        if not tasks:
            raise LLMError("the plan had no valid tasks")
        if not any(agent_type == "librarian" for agent_type, _ in tasks):
            # A decision is never analysed without checking what was already decided, whatever the plan says.
            tasks = [*tasks[:3], ("librarian", f"What the founder already decided on this topic: {message}")]
        reversibility = data.get("reversibility") if data.get("reversibility") in ("one_way", "two_way") else None
        return Plan(
            intent="decision",
            decision_type=str(data.get("decision_type") or "") or None,
            reversibility=reversibility,
            team=_team(tasks, router),
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

    def _emit(self, type_: Any, agent_id: str, **data: Any) -> None:
        self.bus.emit(type_, self.run_id, agent_id, **data)

    async def run(self, inst: AgentInstance, user_message: str) -> AgentResult:
        spec = REGISTRY[inst.type]
        started = time.perf_counter()
        result = AgentResult(agent_id=inst.id, type=inst.type, name=inst.name, brief=inst.brief)
        self._emit("agent.status", inst.id, status="thinking")
        await self._look_up_past_decisions(spec, inst, user_message, result)
        messages = [
            Message.system(spec.prompt() + await self._data_context(spec) + _decisions_context(result)),
            Message.user(f"Brief: {inst.brief}\nFounder's message: {user_message}"),
        ]
        await self._search_first(spec, inst, user_message, messages, result)
        await self._scenario_first(spec, inst, user_message, messages, result)
        try:
            await self._loop(spec, inst, messages, result)
        except LLMError as exc:
            logger.warning("Agent {} LLM unavailable, using rules: {}", inst.name, exc)
            result.fallback_from = result.provider or inst.provider
            await self._rules(spec, inst, user_message, result)
        _surface_decisions(result)
        self._verify(spec, inst, user_message, result)
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
        _keep_used_sources(result)
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
            est_cost_usd=0.0 if not inst.is_cloud else None,
        )
        return result

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
        if spec.name != "financial_analyst" or hires is None:
            return
        call = ToolCall(name="run_scenario", arguments={"new_hires": hires})
        outcome = await self._call_tool(spec, inst, call, result)
        messages.append(Message.assistant("", [call]))
        messages.append(Message.tool(call, outcome.for_model()))

    async def _data_context(self, spec: AgentType) -> str:
        """Tell the Financial Analyst which months exist, so it does not invent a `month` argument."""
        if spec.name != "financial_analyst":
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
            result.facts,
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
        outcome = await run_tool(call.name, self.ctx_factory(inst.id), call.arguments, spec.tools)
        result.tool_calls.append({"tool": call.name, "arguments": call.arguments, "error": outcome.error})
        result.facts.extend(outcome.facts)
        # The first scenario is the founder's: later ones are the model exploring.
        if result.decision_impact is None and not outcome.error and isinstance(outcome.content.get("impact"), dict):
            result.decision_impact = DecisionImpact(**outcome.content["impact"])
        for citation in outcome.citations:
            if citation not in result.retrieved:
                result.retrieved.append(citation)
        self._emit("agent.tool_call", inst.id, tool=call.name, arguments=call.arguments, error=outcome.error)
        for artifact in outcome.artifacts:
            result.artifacts.append(artifact)
            self._emit("agent.artifact", inst.id, artifact=artifact.model_dump(mode="json"))
        return outcome

    async def _loop(self, spec: AgentType, inst: AgentInstance, messages: list[Message], result: AgentResult) -> None:
        tools = specs_for(spec.tools) or None
        for step in range(self.max_steps + 1):
            final = step == self.max_steps
            self._emit("agent.status", inst.id, status="waiting_cloud" if inst.is_cloud else "thinking")
            completion = await self.router.complete(spec.privacy, messages, tools=None if final else tools)
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
        if completion.fallback_from:
            result.fallback_from = completion.fallback_from

    async def _rules(self, spec: AgentType, inst: AgentInstance, user_message: str, result: AgentResult) -> None:
        """No LLM: run the obvious tool and answer with a template built only from its result."""
        result.provider, result.model = "rules", ""
        if spec.name == "financial_analyst" and result.decision_impact is not None:
            result.text = result.decision_impact.sentence()
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
                    f"{c['label']}: {_fmt(c['value'], c['unit'])} as of {c['as_of']}."
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
    result.text, _ = repair_claims(result.text, result.facts, user_message, _written_by_code(result.decision_impact))


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


def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "months":
        return f"{value} months"
    if unit in ("ratio",):
        return f"{value}"
    if unit == "percent":
        return f"{value} %"
    if unit == "count":
        return f"{value}"
    if re.fullmatch(r"[A-Z]{3}", unit):
        return f"{value:,.2f} {unit}" if isinstance(value, int | float) else f"{value} {unit}"
    return f"{value} {unit}"


def _plain(snippet: str) -> str:
    """A search snippet as one line of prose (no Markdown heading marks, no line breaks)."""
    return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*#+\s*", "", snippet)).strip()


def _args_preview(arguments: dict[str, Any]) -> str:
    text = ", ".join(f"{k}={json.dumps(v, default=str)}" for k, v in arguments.items())
    return text if len(text) <= 80 else text[:77] + "..."


def findings_for_advisor(results: list[AgentResult]) -> str:
    blocks: list[str] = []
    impact = team_impact(results)
    for r in results:
        # A wrong-meaning sentence is already replaced, so naming its figure again would only bring it back.
        kept = [i for i in r.issues if not i.startswith("wrong meaning")]
        replaced = ["a sentence was replaced by one written in code"] if len(kept) < len(r.issues) else []
        flag = "" if r.verified else f" [UNVERIFIED: {'; '.join(kept + replaced)}]"
        if r.status != "done":
            blocks.append(f"- {r.name}: failed ({r.error}).")
            continue
        blocks.append(f"- {r.name}{flag}: {r.text}")
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


class _SentenceGate:
    """Checks the Advisor's reply one sentence at a time, before the founder sees it (the reply streams)."""

    def __init__(self, facts: list[Fact], message: str, impact: DecisionImpact | None, issues: list[str]) -> None:
        self.facts, self.message, self.impact, self.issues = facts, message, impact, issues
        self.pending = ""
        self.written: set[str] = set()

    def _checked(self, text: str) -> str:
        fixed, failed = repair_claims(text, self.facts, self.message, _written_by_code(self.impact), self.written)
        self.issues.extend(f"advisor: wrong meaning: {i.message}" for i in failed)
        if not failed:
            return text
        trailing = text[len(text.rstrip()) :]
        return fixed + trailing

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


def advisor_impact_note(answer: str, plan_: Plan, results: list[AgentResult]) -> str:
    impact = team_impact(results) if plan_.intent == "decision" else None
    if impact is None:
        return ""
    if not impact_stated(answer, impact):
        return f" {impact.sentence()}"
    # Seen live: "Hiring a designer costs $11,423.62". That is the company's average, not a quote for this role.
    if impact.cost_per_hire_monthly and impact.cost_is_company_average and "average" not in answer.lower():
        each = f"{impact.cost_per_hire_monthly:,.2f} {impact.currency}"
        return f" The {each} is the company's average loaded monthly cost per person, not a quote for this role."
    return ""


async def advise(
    router: LLMRouter,
    user_message: str,
    plan_: Plan,
    results: list[AgentResult],
    issues: list[str] | None = None,
) -> AsyncIterator[StreamChunk]:
    """The Advisor streams its reply, sentence by sentence, each one checked before it goes out.

    A sentence that attaches a figure to the wrong quantity or unit is replaced by one written in code and added to
    `issues`. Without an LLM it yields a template answer built from the findings.
    """
    spec = REGISTRY["advisor"]
    findings = findings_for_advisor(results)
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
    messages = [Message.system(system), Message.user(context)]
    sent: list[str] = []
    facts = [fact for r in results for fact in r.facts]
    gate = _SentenceGate(facts, user_message, team_impact(results), issues if issues is not None else [])
    try:
        async for chunk in router.stream(spec.privacy, messages):
            ready = gate.feed(chunk.delta) if chunk.delta else ""
            if ready:
                sent.append(ready)
                yield StreamChunk(delta=ready)
            if chunk.done and chunk.completion is not None:
                ready = gate.flush()
                if ready:
                    sent.append(ready)
                    yield StreamChunk(delta=ready)
                note = advisor_decision_note("".join(sent), results)
                note += advisor_impact_note("".join(sent) + note, plan_, results)
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
        if any(sent):
            # The founder already saw part of the reply: end it honestly instead of appending a second answer.
            logger.warning("Advisor stream broke after {} chunks: {}", len(sent), exc)
            note = " (The reply was cut off; see the findings.)" + advisor_decision_note("".join(sent), results)
            yield StreamChunk(delta=note)
            text = "".join(sent) + note
            yield StreamChunk(done=True, completion=Completion(text=text, provider=provider.name, model=provider.model))
            return
        logger.warning("Advisor LLM unavailable, using the template answer: {}", exc)
        text = template_answer(results)
        text += advisor_impact_note(text, plan_, results)
        yield StreamChunk(delta=text)
        yield StreamChunk(
            done=True, completion=Completion(text=text, provider="rules", model="", fallback_from=provider.name)
        )


def template_answer(results: list[AgentResult]) -> str:
    done = [r for r in results if r.status == "done" and r.text]
    if not done:
        return "The language model is unavailable and there are no findings yet. Check that Ollama is running."
    return " ".join(r.text for r in done) + " (Answer assembled without the language model.)"


AwaitableFactory = Callable[[], Awaitable[Any]]
