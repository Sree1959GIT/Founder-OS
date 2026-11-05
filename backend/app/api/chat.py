"""`/api/chat` (streaming SSE or JSON), `/api/events` (agent event stream), `/api/runs/*`, `/api/agents`.

SSE frames are `id: <seq>` / `event: <type>` / `data: <json>`. The chat stream carries this run's agent events, then
`delta` frames with the Advisor's text as it is generated, then one `done` frame with the full `ChatResult`
(answer, metrics with lineage, citations, verification, timings).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.events import AgentEvent, EventBus
from app.agents.graph import AgentOrchestrator, ChatResult, RerunOutcome, RunContext, TeamEdit
from app.agents.registry import REGISTRY

router = APIRouter(tags=["agents"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
KEEPALIVE_S = 15.0


def get_orchestrator(request: Request) -> AgentOrchestrator:
    orchestrator: AgentOrchestrator = request.app.state.orchestrator
    return orchestrator


def get_bus(request: Request) -> EventBus:
    bus: EventBus = request.app.state.event_bus
    return bus


OrchestratorDep = Annotated[AgentOrchestrator, Depends(get_orchestrator)]
BusDep = Annotated[EventBus, Depends(get_bus)]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    stream: bool = Field(True, description="true: Server-Sent Events; false: one JSON ChatResult when finished")


def sse(event: str, data: Any, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _chat_stream(run: RunContext, bus: EventBus) -> AsyncIterator[str]:
    yield sse("run", {"run_id": run.run_id})
    merged: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def pump_events() -> None:
        async for event in bus.subscribe(run_id=run.run_id):
            await merged.put(("event", event))

    async def pump_deltas() -> None:
        while (delta := await run.deltas.get()) is not None:
            await merged.put(("delta", delta))
        await merged.put(("end", None))

    tasks = [asyncio.create_task(pump_events()), asyncio.create_task(pump_deltas())]
    sent: set[int] = set()
    try:
        while True:
            kind, item = await merged.get()
            if kind == "event":
                assert isinstance(item, AgentEvent)
                sent.add(item.seq)
                yield sse(item.type, item.model_dump(mode="json"), item.seq)
            elif kind == "delta":
                yield sse("delta", {"text": item})
            else:
                break
        assert run.task is not None
        try:
            result = await run.task
            for event in bus.history(run.run_id):  # events published after the last delta
                if event.type == "run.finished" and event.seq not in sent:
                    yield sse(event.type, event.model_dump(mode="json"), event.seq)
            yield sse("done", result.model_dump(mode="json"))
        except asyncio.CancelledError:
            yield sse("error", {"detail": "run cancelled"})
        except Exception as exc:
            yield sse("error", {"detail": f"{type(exc).__name__}: {exc}"})
    finally:
        for task in tasks:
            task.cancel()


@router.post("/chat", response_model=None)
async def chat(body: ChatRequest, orchestrator: OrchestratorDep, bus: BusDep) -> StreamingResponse | ChatResult:
    """Ask the advisor. The Planner picks a team, agents run in parallel, the Verifier checks, the Advisor answers."""
    run = orchestrator.start(body.message.strip())
    if body.stream:
        return StreamingResponse(_chat_stream(run, bus), media_type="text/event-stream", headers=SSE_HEADERS)
    assert run.task is not None
    try:
        return await run.task
    except asyncio.CancelledError as exc:
        raise HTTPException(status_code=409, detail="run cancelled") from exc


@router.get("/events")
async def events(
    bus: BusDep,
    run_id: Annotated[str | None, Query(description="Only this run")] = None,
    since: Annotated[int, Query(ge=0, description="Resume after this seq")] = 0,
) -> StreamingResponse:
    """Agent events for the Agent Activity panel (SSE, never ends; a comment line every 15 s keeps it open)."""

    async def stream() -> AsyncIterator[str]:
        async for event in bus.stream(run_id=run_id, since=since, keepalive_s=KEEPALIVE_S):
            if event is None:
                yield ": keep-alive\n\n"
            else:
                yield sse(event.type, event.model_dump(mode="json"), event.seq)

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


class ApprovalRequest(BaseModel):
    approved: bool = True
    edit: TeamEdit | None = Field(None, description="Briefs edited, agents removed or added when approving")


class RerunRequest(BaseModel):
    brief: str | None = Field(None, max_length=2000, description="The edited brief. Empty keeps the old one")


@router.get("/runs/{run_id}")
async def get_run(run_id: str, orchestrator: OrchestratorDep, bus: BusDep) -> dict[str, Any]:
    run = orchestrator.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
    status = "running" if run.task is not None and not run.task.done() else "finished"
    return {
        "run_id": run_id,
        "status": status,
        "awaiting_approval": run.plan is not None
        and not run.approval.is_set()
        and orchestrator.needs_approval(run.plan.team),
        "result": run.result.model_dump(mode="json") if run.result else None,
        "snapshot": run.context.model_dump(mode="json") if run.context is not None else None,
        "events": [e.model_dump(mode="json") for e in bus.history(run_id)],
    }


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: str, body: ApprovalRequest, orchestrator: OrchestratorDep) -> dict[str, Any]:
    if not orchestrator.approve(run_id, body.approved, body.edit):
        raise HTTPException(status_code=409, detail="run not found or not waiting for approval")
    return {"run_id": run_id, "approved": body.approved}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, orchestrator: OrchestratorDep) -> dict[str, Any]:
    if not orchestrator.cancel(run_id):
        raise HTTPException(status_code=409, detail="run not found or already finished")
    return {"run_id": run_id, "cancelled": True}


@router.post("/runs/{run_id}/agents/{agent_id}/cancel")
async def cancel_agent(run_id: str, agent_id: str, orchestrator: OrchestratorDep) -> dict[str, Any]:
    """Cancel one instance. The rest of the team goes on."""
    if not orchestrator.cancel_agent(run_id, agent_id):
        raise HTTPException(status_code=409, detail="agent not found or not running")
    return {"run_id": run_id, "agent_id": agent_id, "cancelled": True}


@router.post("/runs/{run_id}/agents/{agent_id}/rerun")
async def rerun_agent(run_id: str, agent_id: str, body: RerunRequest, orchestrator: OrchestratorDep) -> RerunOutcome:
    """Re-run with an edited brief: restarts a running instance, or starts a new run once this one has finished."""
    outcome = orchestrator.rerun_agent(run_id, agent_id, body.brief)
    if outcome is None:
        raise HTTPException(status_code=409, detail="unknown agent, or its team is still working: wait for the run")
    return outcome


@router.get("/agents")
async def agents(orchestrator: OrchestratorDep) -> dict[str, Any]:
    """The registered agent types, where each one runs now, this month's cost and latency, and the settings."""
    out = []
    ledger = orchestrator.router.ledger
    stats = ledger.stats() if ledger is not None else {}
    for spec in REGISTRY.values():
        provider = orchestrator.router.primary(spec.privacy, needs_tools=bool(spec.tools), agent_type=spec.name)
        out.append(
            {
                "type": spec.name,
                "title": spec.title,
                "job": spec.job,
                "tools": list(spec.tools),
                "privacy": spec.privacy,
                "cost": spec.cost,
                "core": spec.core,
                "spawnable": spec.spawnable,
                "stage": spec.stage,
                "provider": provider.name,
                "model": provider.model,
                "is_cloud": provider.is_cloud,
                "this_month": stats.get(spec.name),
            }
        )
    return {
        "agents": out,
        "approval_policy": orchestrator.approval_policy,
        "max_local_agents": orchestrator.max_local,
        "max_cloud_agents": orchestrator.max_cloud,
        "cloud": {
            "allowed": orchestrator.router.cloud_allowed,
            "default_provider": orchestrator.router.cloud.name if orchestrator.router.cloud else None,
            **(ledger.summary() if ledger is not None else {}),
        },
    }
