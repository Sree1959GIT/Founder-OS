"""Agent runtime: the tool-calling loop, the Planner, the Advisor and rule-based fallbacks.

Every LLM call goes through the `LLMRouter` (privacy routing and fallback). When the local LLM is down, the agents
fall back to rules (PRD R3): keyword intent, a direct metric routine or vault search, and a template answer built
only from tool results.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from app.agents.events import Artifact, Citation, EventBus
from app.agents.registry import REGISTRY, AgentType, spawnable_types
from app.agents.tools import TOOLS, ToolContext, ToolOutcome, run_tool, specs_for
from app.agents.verifier import verify
from app.decision.base import DecisionError, DecisionService
from app.engine.lineage import Lineage
from app.llm.base import Completion, LLMError, Message, StreamChunk, ToolCall, Usage
from app.llm.router import LLMRouter

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
_CHITCHAT = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b[\s!.?]*$", re.I)

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
    citations: list[Citation] = Field(default_factory=list)
    numbers: list[float] = Field(default_factory=list, exclude=True)
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
    def lineage(self) -> list[Lineage]:
        return [lin for a in self.artifacts for lin in a.lineage]


Emit = Callable[..., Any]


def rule_intent(message: str) -> Intent | None:
    """Clear-cut cases need no model call (fast, deterministic). Ambiguous ones return None."""
    if _CHITCHAT.match(message):
        return "chitchat"
    if _DECISION_CUES.search(message):
        return "decision"
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
        messages = [
            Message.system(spec.prompt() + await self._data_context(spec)),
            Message.user(f"Brief: {inst.brief}\nFounder's message: {user_message}"),
        ]
        try:
            await self._loop(spec, inst, messages, result)
        except LLMError as exc:
            logger.warning("Agent {} LLM unavailable, using rules: {}", inst.name, exc)
            result.fallback_from = result.provider or inst.provider
            await self._rules(spec, inst, user_message, result)
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
            self._verify(spec, inst, user_message, result)
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
        report = verify(
            result.text,
            result.numbers,
            result.citations,
            needs_citations=spec.name == "librarian" and searched and bool(result.citations),
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
        result.numbers.extend(outcome.numbers)
        for citation in outcome.citations:
            if citation not in result.citations:
                result.citations.append(citation)
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
        if spec.name == "financial_analyst":
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
            hits = outcome.content.get("results", [])
            result.text = (
                " ".join(f"{_plain(h['snippet'])} [{h['path']}]" for h in hits[:3])
                if hits
                else "Nothing relevant was found in the vault."
            )
        if not result.text:
            result.status, result.error = "failed", "the language model is unavailable and no rule applies"


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
    for r in results:
        flag = "" if r.verified else f" [UNVERIFIED: {'; '.join(r.issues)}]"
        if r.status != "done":
            blocks.append(f"- {r.name}: failed ({r.error}).")
            continue
        blocks.append(f"- {r.name}{flag}: {r.text}")
        for art in r.artifacts:
            if art.kind == "metric_card":
                d = art.data
                blocks.append(f"  * {d.get('label')}: {d.get('value')} {d.get('unit')} (as of {d.get('as_of')})")
    return "\n".join(blocks) if blocks else "(no findings)"


async def advise(
    router: LLMRouter, user_message: str, plan_: Plan, results: list[AgentResult]
) -> AsyncIterator[StreamChunk]:
    """The Advisor streams its reply. Without an LLM it yields a template answer built from the findings."""
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
    messages = [Message.system(spec.prompt()), Message.user(context)]
    sent: list[str] = []
    try:
        async for chunk in router.stream(spec.privacy, messages):
            sent.append(chunk.delta)
            yield chunk
    except LLMError as exc:
        provider = router.primary(spec.privacy)
        if any(sent):
            # The founder already saw part of the reply: end it honestly instead of appending a second answer.
            logger.warning("Advisor stream broke after {} chunks: {}", len(sent), exc)
            note = " (The reply was cut off; see the findings.)"
            yield StreamChunk(delta=note)
            text = "".join(sent) + note
            yield StreamChunk(done=True, completion=Completion(text=text, provider=provider.name, model=provider.model))
            return
        logger.warning("Advisor LLM unavailable, using the template answer: {}", exc)
        text = template_answer(results)
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
