"""The agent graph (LangGraph) and the run manager.

    plan ──Send(instance)──▶ agent (N instances, in parallel, capped) ──▶ verify ──▶ advise ──▶ END
      └──(no team: chitchat)──────────────────────────────────────────────▲

- **plan**: the Planner picks the intent and the team; then the team-approval policy applies (`TEAM_APPROVAL`:
  `always` | `cloud_only` (default: only teams with a cloud agent wait for the founder) | `never`).
- **agent**: one node per instance via LangGraph `Send`. Concurrency is capped by two semaphores shared by all
  runs (`MAX_LOCAL_AGENTS`=2, `MAX_CLOUD_AGENTS`=6); extra instances wait as `queued`. Each instance's answer is
  checked by the Verifier and sent back once (inside `AgentRunner`).
- **verify**: joins the fan-out and records the team-level verdict.
- **advise**: the Advisor streams the reply to the chat; its numbers are verified against all tool results.
"""

from __future__ import annotations

import asyncio
import operator
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from loguru import logger
from pydantic import BaseModel, Field

from app.agents.events import Artifact, Citation, EventBus
from app.agents.runtime import AgentInstance, AgentResult, AgentRunner, Plan, advise, plan
from app.agents.tools import ToolContext
from app.agents.verifier import verify_numbers
from app.decision.base import DecisionService
from app.llm.base import Usage
from app.llm.router import LLMRouter


class RunCancelled(Exception):
    pass


class GraphState(TypedDict, total=False):
    run_id: str
    message: str
    plan: Plan
    approved: bool
    results: Annotated[list[AgentResult], operator.add]
    instance: AgentInstance
    answer: str
    advisor: dict[str, Any]


class MetricOut(BaseModel):
    metric: str
    label: str
    value: float | None
    unit: str
    as_of: str
    agent_id: str
    lineage: dict[str, Any]


class ChatResult(BaseModel):
    run_id: str
    message: str
    answer: str
    intent: str
    decision_type: str | None = None
    reversibility: str | None = None
    planner: str
    intent_decision_id: str | None = Field(
        default=None, description="Decision-log id of the intent choice (to record a correction for Laya)"
    )
    team: list[AgentInstance]
    approved: bool
    agents: list[AgentResult]
    metrics: list[MetricOut] = Field(description="Every metric the team computed, with its full lineage")
    artifacts: list[Artifact]
    citations: list[Citation]
    verified: bool
    issues: list[str]
    advisor_provider: str
    advisor_model: str
    usage: Usage
    timings_ms: dict[str, float]
    elapsed_ms: float
    status: str = "done"


@dataclass
class RunContext:
    run_id: str
    message: str
    deltas: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    approval: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool | None = None
    timings: dict[str, float] = field(default_factory=dict)
    task: asyncio.Task[ChatResult] | None = None
    result: ChatResult | None = None
    plan: Plan | None = None


class AgentOrchestrator:
    """Builds the LangGraph graph once and runs it per chat message."""

    def __init__(
        self,
        router: LLMRouter,
        decisions: DecisionService,
        bus: EventBus,
        ctx_factory: Callable[[str], ToolContext],
        *,
        approval_policy: str = "cloud_only",
        approval_timeout_s: float = 300.0,
        max_local: int = 2,
        max_cloud: int = 6,
        max_steps: int = 4,
    ) -> None:
        self.router = router
        self.decisions = decisions
        self.bus = bus
        self.ctx_factory = ctx_factory
        self.approval_policy = approval_policy
        self.approval_timeout_s = approval_timeout_s
        self.max_local, self.max_cloud = max_local, max_cloud
        self.local_slots = asyncio.Semaphore(max_local)
        self.cloud_slots = asyncio.Semaphore(max_cloud)
        self.max_steps = max_steps
        self.runs: dict[str, RunContext] = {}
        self.graph = self._build()

    # ---------------------------------------------------------------- graph
    def _build(self) -> Any:
        g: StateGraph[GraphState] = StateGraph(GraphState)
        g.add_node("plan", self._plan_node)
        g.add_node("agent", self._agent_node)
        g.add_node("verify", self._verify_node)
        g.add_node("advise", self._advise_node)
        g.add_edge(START, "plan")
        g.add_conditional_edges("plan", self._fan_out, ["agent", "advise"])
        g.add_edge("agent", "verify")
        g.add_edge("verify", "advise")
        g.add_edge("advise", END)
        return g.compile()

    def needs_approval(self, team: list[AgentInstance]) -> bool:
        if not team or self.approval_policy == "never":
            return False
        return self.approval_policy == "always" or any(i.is_cloud for i in team)

    async def _plan_node(self, state: GraphState) -> dict[str, Any]:
        run = self.runs[state["run_id"]]
        started = time.perf_counter()
        the_plan = await plan(state["message"], self.router, self.decisions)
        run.plan = the_plan
        run.timings["plan"] = _ms(started)
        team = [i.model_dump() for i in the_plan.team]
        needs = self.needs_approval(the_plan.team)
        self.bus.emit(
            "team.proposed",
            run.run_id,
            intent=the_plan.intent,
            decision_type=the_plan.decision_type,
            reversibility=the_plan.reversibility,
            planner=the_plan.planner,
            team=team,
            needs_approval=needs,
        )
        approved = True
        if needs:
            try:
                await asyncio.wait_for(run.approval.wait(), timeout=self.approval_timeout_s)
                approved = bool(run.approved)
            except TimeoutError:
                approved = False
                run.approved = False
                run.approval.set()  # closed: /api/runs no longer shows it as waiting, and /approve returns 409
            run.timings["approval_wait"] = _ms(started) - run.timings["plan"]
        if not approved:
            self.bus.emit("team.rejected", run.run_id, reason="not approved")
            for inst in the_plan.team:
                self.bus.emit("agent.status", run.run_id, inst.id, status="cancelled")
            return {"plan": the_plan, "approved": False}
        if the_plan.team:
            self.bus.emit("team.approved", run.run_id, auto=not needs)
            for inst in the_plan.team:
                self.bus.emit("agent.spawned", run.run_id, inst.id, **inst.model_dump())
                self.bus.emit("agent.status", run.run_id, inst.id, status="queued")
        run.timings["agents_start"] = time.perf_counter()
        return {"plan": the_plan, "approved": True}

    @staticmethod
    def _fan_out(state: GraphState) -> list[Send] | str:
        if not state.get("approved") or not state["plan"].team:
            return "advise"
        return [Send("agent", {**state, "instance": inst}) for inst in state["plan"].team]

    async def _agent_node(self, state: GraphState) -> dict[str, Any]:
        inst = state["instance"]
        slots = self.cloud_slots if inst.is_cloud else self.local_slots
        runner = AgentRunner(self.router, self.bus, state["run_id"], self.ctx_factory, self.max_steps)
        async with slots:
            try:
                result = await runner.run(inst, state["message"])
            except asyncio.CancelledError:
                self.bus.emit("agent.status", state["run_id"], inst.id, status="cancelled")
                raise
            except Exception as exc:  # one broken agent must not sink the team
                logger.exception("Agent {} failed", inst.name)
                result = AgentResult(
                    agent_id=inst.id, type=inst.type, name=inst.name, brief=inst.brief, status="failed", error=str(exc)
                )
                self.bus.emit("agent.done", state["run_id"], inst.id, status="failed", error=str(exc))
        return {"results": [result]}

    async def _verify_node(self, state: GraphState) -> dict[str, Any]:
        run = self.runs[state["run_id"]]
        started = run.timings.pop("agents_start", time.perf_counter())
        run.timings["agents"] = _ms(started)
        return {}

    async def _advise_node(self, state: GraphState) -> dict[str, Any]:
        run = self.runs[state["run_id"]]
        started = time.perf_counter()
        results = state.get("results", [])
        if not state.get("approved", True):
            text = "I held the team back because it was not approved. Approve it, or change the briefs, to continue."
            await run.deltas.put(text)
            run.timings["advise"] = _ms(started)
            return {"answer": text, "advisor": {"provider": "rules", "model": ""}}
        parts: list[str] = []
        meta: dict[str, Any] = {"provider": "", "model": "", "usage": Usage()}
        async for chunk in advise(self.router, state["message"], state["plan"], results):
            if chunk.delta:
                parts.append(chunk.delta)
                await run.deltas.put(chunk.delta)
            if chunk.done and chunk.completion is not None:
                meta = {
                    "provider": chunk.completion.provider,
                    "model": chunk.completion.model,
                    "usage": chunk.completion.usage,
                }
        run.timings["advise"] = _ms(started)
        return {"answer": "".join(parts).strip(), "advisor": meta}

    # ---------------------------------------------------------------- runs
    def start(self, message: str) -> RunContext:
        run = RunContext(run_id=f"run_{uuid.uuid4().hex[:10]}", message=message)
        self.runs[run.run_id] = run
        self._trim()
        run.task = asyncio.create_task(self._execute(run))
        return run

    async def _execute(self, run: RunContext) -> ChatResult:
        started = time.perf_counter()
        self.bus.emit("run.started", run.run_id, message=run.message)
        try:
            state = await self.graph.ainvoke({"run_id": run.run_id, "message": run.message, "results": []})
        except asyncio.CancelledError:
            self.bus.emit("run.finished", run.run_id, status="cancelled")
            await run.deltas.put(None)
            raise
        except Exception as exc:
            logger.exception("Run {} failed", run.run_id)
            self.bus.emit("run.finished", run.run_id, status="failed", error=str(exc))
            await run.deltas.put(None)
            raise
        result = self._result(run, state, _ms(started))
        run.result = result
        self.bus.emit(
            "run.finished",
            run.run_id,
            status=result.status,
            verified=result.verified,
            elapsed_ms=result.elapsed_ms,
        )
        await run.deltas.put(None)
        return result

    def _result(self, run: RunContext, state: dict[str, Any], elapsed_ms: float) -> ChatResult:
        the_plan: Plan = state["plan"]
        results: list[AgentResult] = state.get("results", [])
        artifacts = [a for r in results for a in r.artifacts]
        metrics = [
            MetricOut(
                metric=a.data["metric"],
                label=a.data["label"],
                value=a.data["value"],
                unit=a.data["unit"],
                as_of=a.data["as_of"],
                agent_id=a.agent_id,
                lineage=a.data["lineage"],
            )
            for a in artifacts
            if a.kind == "metric_card"
        ]
        citations: list[Citation] = []
        for r in results:
            citations.extend(c for c in r.citations if c not in citations)
        answer = state.get("answer", "")
        known = [n for r in results for n in r.numbers]
        context = run.message + "\n" + "\n".join(r.text for r in results if r.verified)
        advisor_issues = [f"advisor number without lineage: {n}" for n in verify_numbers(answer, known, context)]
        issues = [f"{r.name}: {i}" for r in results for i in r.issues] + advisor_issues
        advisor = state.get("advisor", {})
        usage = sum((r.usage for r in results), Usage()) + advisor.get("usage", Usage())
        approved = bool(state.get("approved", True))
        return ChatResult(
            run_id=run.run_id,
            message=run.message,
            answer=answer,
            intent=the_plan.intent,
            decision_type=the_plan.decision_type,
            reversibility=the_plan.reversibility,
            planner=the_plan.planner,
            intent_decision_id=the_plan.intent_decision_id,
            team=the_plan.team,
            approved=approved,
            agents=results,
            metrics=metrics,
            artifacts=artifacts,
            citations=citations,
            verified=not issues and all(r.status == "done" for r in results),
            issues=issues,
            advisor_provider=str(advisor.get("provider", "")),
            advisor_model=str(advisor.get("model", "")),
            usage=usage,
            timings_ms={k: v for k, v in run.timings.items() if k != "agents_start"},
            elapsed_ms=elapsed_ms,
            status="done" if approved else "rejected",
        )

    def approve(self, run_id: str, approved: bool = True) -> bool:
        run = self.runs.get(run_id)
        if run is None or run.approval.is_set():
            return False
        run.approved = approved
        run.approval.set()
        return True

    def cancel(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if run is None or run.task is None or run.task.done():
            return False
        run.task.cancel()
        return True

    def _trim(self, keep: int = 100) -> None:
        finished = [rid for rid, r in self.runs.items() if r.task is not None and r.task.done()]
        for rid in finished[: max(0, len(self.runs) - keep)]:
            self.runs.pop(rid, None)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
