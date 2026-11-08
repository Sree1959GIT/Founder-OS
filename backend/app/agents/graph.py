"""The agent graph (LangGraph) and the run manager.

    plan ──Send(instance)──▶ agent (N instances, in parallel, capped) ──▶ verify ──▶ advise ──▶ END
      │                        ▲                                           │           ▲
      │                        └───────────── next stage of the team ──────┘           │
      └──(no team: chitchat)───────────────────────────────────────────────────────────┘

- **plan**: the Planner picks the intent and the team; then the team-approval policy applies (`TEAM_APPROVAL`:
  `always` | `cloud_only` (default: only teams with a cloud agent wait for the founder) | `never`).
- **agent**: one node per instance via LangGraph `Send`. Concurrency is capped by two semaphores shared by all
  runs (`MAX_LOCAL_AGENTS`=2, `MAX_CLOUD_AGENTS`=6); extra instances wait as `queued`. Each instance's answer is
  checked by the Verifier and sent back once (inside `AgentRunner`).
- **verify**: joins the fan-out, then sends the next stage of the team, which sees the earlier stages' findings.
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

from app.agents.cash_risk import CashRisk, cash_risk, wants_warning
from app.agents.decision_frame import DecisionFrame, build_frame
from app.agents.events import Artifact, Citation, EventBus
from app.agents.horizon import beyond, beyond_issue
from app.agents.registry import REGISTRY
from app.agents.runtime import (
    AgentInstance,
    AgentResult,
    AgentRunner,
    Plan,
    _team,
    advise,
    metrics_named,
    plan,
    stand_in_note,
    team_impact,
    team_projection,
)
from app.agents.sources import vault_checker
from app.agents.specialists import MemoRef
from app.agents.tools import DecisionImpact, ToolContext
from app.agents.verification import Verification, not_run, verification
from app.agents.verifier import extract_figures, number_supported, verify_numbers
from app.decision.base import DecisionService
from app.engine.metrics import METRICS
from app.llm.base import Usage
from app.llm.router import LLMRouter
from app.vault.decisions import DecisionRecord


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


def _removed_before_shown(results: list[AgentResult]) -> list[str]:
    """Audit lines about a figure the source check then took out: the founder never saw it, so it is counted as a
    removed claim (the chip by the badge), not as a failure of the figures that are shown."""
    resolved: list[str] = []
    for r in results:
        gone = list(r.removed_figures)
        for issue in r.issues:
            if not issue.startswith("number without lineage"):
                continue
            figures = extract_figures(issue.split(":", 1)[1])
            if figures and gone and all(number_supported(f, gone) for f in figures):
                resolved.append(f"{r.name}: {issue}")
    return resolved


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
    citations: list[Citation] = Field(description="Only the sources the agents' answers name")
    past_decisions: list[DecisionRecord] = Field(
        default_factory=list, description="Decisions already on record for this topic"
    )
    decision_impact: DecisionImpact | None = Field(
        default=None, description="What this decision does to costs and runway, computed in code"
    )
    decision_frame: DecisionFrame | None = Field(
        default=None, description="Type, cost model, options and goal check, computed in code"
    )
    assumptions_to_confirm: int = Field(0, description="Placeholder inputs the answer rests on")
    memo: MemoRef | None = Field(default=None, description="The decision memo this run wrote")
    cash_risk: CashRisk | None = Field(default=None, description="Monte Carlo cash-out warning, when it was given")
    est_cost_usd: float | None = Field(default=0.0, description="None: a cloud model with no known price was used")
    verified: bool
    verification: Verification = Field(
        default_factory=lambda: Verification(state="not_verified"),
        description="The badge: verified, figures verified with assumptions to confirm, or not verified (with reasons)",
    )
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
    plan_override: Plan | None = None
    team_edit: TeamEdit | None = None
    agent_tasks: dict[str, asyncio.Task[AgentResult]] = field(default_factory=dict)
    stop_agents: set[str] = field(default_factory=set)
    new_briefs: dict[str, str] = field(default_factory=dict)
    context: Any = None  # the conversation lane's frozen run snapshot
    cash_risk: CashRisk | None = None
    streamed: bool = False  # someone is reading `deltas`: each piece of text goes to one reader


class TeamEdit(BaseModel):
    """What the founder changed when approving a team (PRD F3: approve / edit briefs / add / remove)."""

    briefs: dict[str, str] = Field(default_factory=dict, description="Agent id -> new brief")
    remove: list[str] = Field(default_factory=list, description="Agent ids to leave out")
    add: list[dict[str, str]] = Field(default_factory=list, description='Each {"type": ..., "brief": ...}')
    local_only: bool = Field(False, description="Run everyone on the local model: nothing leaves this PC")


class RerunOutcome(BaseModel):
    restarted: bool = Field(description="True: restarted inside the running team; false: a new run was started")
    run_id: str
    agent_id: str | None = None


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
        cash_risk_warn_at: float = 2.0,
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
        self.cash_risk_warn_at = cash_risk_warn_at  # above 1: never warn
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
        g.add_conditional_edges("verify", self._next_stage, ["agent", "advise"])
        g.add_edge("advise", END)
        return g.compile()

    def needs_approval(self, team: list[AgentInstance]) -> bool:
        if not team or self.approval_policy == "never":
            return False
        # Founder note 63: a one-metric lookup is a local routine whose answer code writes; there is no team to approve.
        if all(i.fast_metric is not None and not i.is_cloud for i in team):
            return False
        return self.approval_policy == "always" or any(i.is_cloud for i in team)

    async def _plan_node(self, state: GraphState) -> dict[str, Any]:
        run = self.runs[state["run_id"]]
        started = time.perf_counter()
        the_plan = run.plan_override or await plan(state["message"], self.router, self.decisions)
        if the_plan.intent == "decision" and the_plan.frame is None:
            ctx = self.ctx_factory("")
            frame = await asyncio.to_thread(build_frame, state["message"], ctx, the_plan.decision_type)
            the_plan = the_plan.model_copy(update={"frame": frame, "decision_type": frame.type})
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
            questions=the_plan.frame.questions if the_plan.frame is not None else [],
            decision_frame=the_plan.frame.model_dump(mode="json") if the_plan.frame is not None else None,
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
            if approved and run.team_edit is not None:
                the_plan = self._edited(the_plan, run.team_edit)
                run.plan = the_plan
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

    def _edited(self, the_plan: Plan, edit: TeamEdit) -> Plan:
        team = [
            i.model_copy(update={"brief": edit.briefs.get(i.id, i.brief)})
            for i in the_plan.team
            if i.id not in edit.remove
        ]
        added = [(a["type"], a.get("brief", "")) for a in edit.add if a.get("type") in REGISTRY]
        added = [(t, brief) for t, brief in added if REGISTRY[t].spawnable]
        everyone = [*team, *_team(added, self.router)]
        if edit.local_only:
            local = self.router.local
            changes = {"local_only": True, "is_cloud": False, "provider": local.name, "model": local.model}
            everyone = [i.model_copy(update=changes) for i in everyone]
        return the_plan.model_copy(update={"team": everyone})

    @staticmethod
    def _stage_of(state: GraphState, done: set[str]) -> list[Send]:
        waiting = [i for i in state["plan"].team if i.id not in done]
        if not waiting:
            return []
        stage = min(REGISTRY[i.type].stage for i in waiting)
        return [Send("agent", {**state, "instance": i}) for i in waiting if REGISTRY[i.type].stage == stage]

    def _fan_out(self, state: GraphState) -> list[Send] | str:
        if not state.get("approved") or not state["plan"].team:
            return "advise"
        return self._stage_of(state, set()) or "advise"

    def _next_stage(self, state: GraphState) -> list[Send] | str:
        return self._stage_of(state, {r.agent_id for r in state.get("results", [])}) or "advise"

    async def _in_a_slot(self, inst: AgentInstance, state: GraphState) -> AgentResult:
        slots = self.cloud_slots if inst.is_cloud else self.local_slots
        runner = AgentRunner(self.router, self.bus, state["run_id"], self.ctx_factory, self.max_steps)
        async with slots:
            return await runner.run(inst, state["message"], state.get("results", []), state["plan"].frame)

    async def _agent_node(self, state: GraphState) -> dict[str, Any]:
        """One instance, as its own task, so the founder can cancel or re-run it without touching the rest."""
        run = self.runs[state["run_id"]]
        inst = state["instance"]
        while True:
            task = asyncio.create_task(self._in_a_slot(inst, state))
            run.agent_tasks[inst.id] = task
            try:
                result = await task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():  # the whole run was cancelled
                    task.cancel()
                    self.bus.emit("agent.status", state["run_id"], inst.id, status="cancelled")
                    raise
                brief = run.new_briefs.pop(inst.id, None)
                if brief is not None:
                    inst = inst.model_copy(update={"brief": brief})
                    self.bus.emit("agent.rerun", state["run_id"], inst.id, brief=brief)
                    continue
                run.stop_agents.discard(inst.id)
                self.bus.emit("agent.status", state["run_id"], inst.id, status="cancelled")
                result = AgentResult(
                    agent_id=inst.id,
                    type=inst.type,
                    name=inst.name,
                    brief=inst.brief,
                    status="cancelled",
                    error="cancelled by the founder",
                )
            except Exception as exc:  # one broken agent must not sink the team
                logger.exception("Agent {} failed", inst.name)
                result = AgentResult(
                    agent_id=inst.id, type=inst.type, name=inst.name, brief=inst.brief, status="failed", error=str(exc)
                )
                self.bus.emit("agent.done", state["run_id"], inst.id, status="failed", error=str(exc))
            finally:
                run.agent_tasks.pop(inst.id, None)
            return {"results": [result]}

    async def _verify_node(self, state: GraphState) -> dict[str, Any]:
        run = self.runs[state["run_id"]]
        started = run.timings.get("agents_start", time.perf_counter())
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
        claim_issues: list[str] = []
        exists = vault_checker(self.ctx_factory(""))
        async for chunk in advise(self.router, state["message"], state["plan"], results, claim_issues, exists):
            if chunk.delta:
                parts.append(chunk.delta)
                await run.deltas.put(chunk.delta)
            if chunk.done and chunk.completion is not None:
                meta = {
                    "provider": chunk.completion.provider,
                    "model": chunk.completion.model,
                    "usage": chunk.completion.usage,
                }
        # Founder note 7: the Advisor speaks up when cash may run out within a year. Code writes it, last.
        asked_for = [m for _, m in metrics_named(state["message"])]
        if results and wants_warning(state["plan"].intent, asked_for):
            finance = getattr(self.ctx_factory(""), "finance", None)
            run.cash_risk = await asyncio.to_thread(cash_risk, finance, self.cash_risk_warn_at)
            if run.cash_risk is not None:
                warning = f" {run.cash_risk.sentence}"
                parts.append(warning)
                await run.deltas.put(warning)
        run.timings["advise"] = _ms(started)
        meta["claim_issues"] = claim_issues
        return {"answer": "".join(parts).strip(), "advisor": meta}

    # ---------------------------------------------------------------- runs
    def start(self, message: str, *, plan_override: Plan | None = None, context: Any = None) -> RunContext:
        run = RunContext(
            run_id=f"run_{uuid.uuid4().hex[:10]}", message=message, plan_override=plan_override, context=context
        )
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
            assumptions=result.assumptions_to_confirm,
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
        past_decisions = list({d.path: d for r in results for d in r.past_decisions}.values())
        citations: list[Citation] = []
        for r in results:
            citations.extend(c for c in r.citations if c not in citations)
        answer = state.get("answer", "")
        frame = the_plan.frame
        known = [
            *(n for r in results for n in r.numbers),
            *(f.value for f in (frame.facts if frame else [])),
            *(f.value for r in results for f in r.record_facts),  # cited to the memo by the source check
            *(run.cash_risk.figures if run.cash_risk is not None else []),
        ]
        cost = [r.est_cost_usd for r in results]
        context = run.message + "\n" + "\n".join(r.text for r in results if r.verified)
        advisor_issues = [f"advisor number without lineage: {n}" for n in verify_numbers(answer, known, context)]
        advisor = state.get("advisor", {})
        issues = (
            [f"{r.name}: {i}" for r in results for i in r.issues] + advisor_issues + advisor.get("claim_issues", [])
        )
        # Placeholder inputs are never "verified", however well the prose checks out.
        assumptions = frame.assumption_count if frame is not None and results else 0
        # Beyond the projection: code gave the last projected month instead, an assumption the founder confirms.
        asked = beyond(run.message, team_projection(results)) if results else None
        assumptions += 1 if asked else 0
        # A metric answered by its closest routine (net revenue churn as net revenue retention): code says so.
        stand_in = stand_in_note(run.message) if the_plan.intent == "finance" and results else None
        assumptions += 1 if stand_in else 0
        # A metric question whose answer does not give that metric is never verified (founder re-test 58: gross
        # revenue churn was answered with gross burn, under a green badge).
        if the_plan.intent == "finance" and results:
            asked_for = list(dict.fromkeys(m for _, m in metrics_named(run.message)))
            missing = [m for m in asked_for if m not in {x.metric for x in metrics}]
            if missing:
                names = ", ".join(METRICS[m].label if m in METRICS else m for m in missing)
                issues.append(f"the answer does not give {names}, which was asked")
        if assumptions:
            issues.append(f"this rests on {assumptions} assumptions to confirm")
        usage = sum((r.usage for r in results), Usage()) + advisor.get("usage", Usage())
        all_done = all(r.status == "done" for r in results)
        model = frame.cost_model if frame is not None and results else None
        to_confirm = [model.item_line(i) for i in model.items if i.basis == "assumption"] if model else []
        if asked:
            to_confirm.append(beyond_issue(asked, team_projection(results)))
        if stand_in:
            to_confirm.append(stand_in.replace(" (assumption, confirm)", ""))
        sources = list(
            dict.fromkeys(
                [*(c.path for c in citations), *(f for r in results for lin in r.lineage for f in lin.source_files)]
            )
        )
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
            past_decisions=past_decisions,
            decision_impact=team_impact(results),
            decision_frame=frame,
            assumptions_to_confirm=assumptions,
            memo=next((r.memo for r in results if r.memo is not None), None),
            cash_risk=run.cash_risk,
            est_cost_usd=None if None in cost else round(sum(c for c in cost if c is not None), 6),
            verified=not issues and all_done,
            # Nothing ran (held back, or a greeting): no check to report, so the badge is a neutral "not run".
            verification=not_run()
            if not approved or not results
            else verification(issues, all_done, to_confirm, sources, resolved=_removed_before_shown(results)),
            issues=issues,
            advisor_provider=str(advisor.get("provider", "")),
            advisor_model=str(advisor.get("model", "")),
            usage=usage,
            timings_ms={k: v for k, v in run.timings.items() if k != "agents_start"},
            elapsed_ms=elapsed_ms,
            status="done" if approved else "rejected",
        )

    def approve(self, run_id: str, approved: bool = True, edit: TeamEdit | None = None) -> bool:
        run = self.runs.get(run_id)
        if run is None or run.approval.is_set():
            return False
        run.approved = approved
        run.team_edit = edit
        run.approval.set()
        return True

    def cancel(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if run is None or run.task is None or run.task.done():
            return False
        run.task.cancel()
        return True

    def cancel_agent(self, run_id: str, agent_id: str) -> bool:
        run = self.runs.get(run_id)
        task = run.agent_tasks.get(agent_id) if run else None
        if run is None or task is None or task.done():
            return False
        run.stop_agents.add(agent_id)
        task.cancel()
        return True

    def rerun_agent(self, run_id: str, agent_id: str, brief: str | None = None) -> RerunOutcome | None:
        """Running instance: restart it with the new brief. Finished run: a new run with this brief edited.

        None when the run or the agent is unknown, or when the agent is done but its team is still working (its
        findings have already gone to the next stage, so re-running it alone would leave the rest out of date).
        """
        run = self.runs.get(run_id)
        if run is None or run.plan is None:
            return None
        inst = next((i for i in run.plan.team if i.id == agent_id), None)
        if inst is None:
            return None
        new_brief = (brief or inst.brief).strip()
        task = run.agent_tasks.get(agent_id)
        if task is not None and not task.done():
            run.new_briefs[agent_id] = new_brief
            task.cancel()
            return RerunOutcome(restarted=True, run_id=run_id, agent_id=agent_id)
        if run.task is not None and not run.task.done():
            return None
        team = [
            i.model_copy(update={"id": _new_agent_id(), "brief": new_brief if i.id == agent_id else i.brief})
            for i in run.plan.team
        ]
        return RerunOutcome(
            restarted=False,
            run_id=self.start(run.message, plan_override=run.plan.model_copy(update={"team": team})).run_id,
        )

    def _trim(self, keep: int = 100) -> None:
        finished = [rid for rid, r in self.runs.items() if r.task is not None and r.task.done()]
        for rid in finished[: max(0, len(self.runs) - keep)]:
            self.runs.pop(rid, None)


def _new_agent_id() -> str:
    return f"agt_{uuid.uuid4().hex[:8]}"


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
