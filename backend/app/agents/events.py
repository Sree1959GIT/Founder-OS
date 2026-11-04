"""Agent event protocol (PRD F3) and the in-process event bus behind `GET /api/events` (SSE).

Event types: `run.started`, `team.proposed`, `team.approved`, `team.rejected`, `agent.spawned`, `agent.status`,
`agent.step`, `agent.tool_call`, `agent.artifact`, `agent.done`, `run.finished`. Every event carries a
monotonically increasing `seq`, so a client that reconnects can resume with `?since=<seq>`.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.engine.lineage import Lineage

EventType = Literal[
    "run.started",
    "team.proposed",
    "team.approved",
    "team.rejected",
    "agent.spawned",
    "agent.status",
    "agent.step",
    "agent.tool_call",
    "agent.artifact",
    "agent.done",
    "run.finished",
    "agent.rerun",
    "turn.classified",
    "narration",
    "amendment.offered",
    "queue.added",
    "queue.offered",
    "recap",
]
AgentStatus = Literal[
    "queued",
    "thinking",
    "querying_data",
    "searching_vault",
    "searching_web",
    "waiting_cloud",
    "verifying",
    "done",
    "failed",
    "cancelled",
]
ArtifactKind = Literal[
    "metric_card",
    "scenario",
    "monte_carlo",
    "priority_matrix",
    "risk_register",
    "decision_memo",
    "chart",
    "table",
    "citation",
    "insight",
]


class Citation(BaseModel):
    path: str
    heading: str
    chunk_id: str


class Artifact(BaseModel):
    """A typed canvas card. `data` is the tool's full result (e.g. a `MetricResult`), so numbers keep lineage."""

    id: str
    kind: ArtifactKind
    title: str
    agent_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    lineage: list[Lineage] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class AgentEvent(BaseModel):
    seq: int = 0
    type: EventType
    run_id: str
    agent_id: str | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    """Fan-out of agent events to SSE subscribers, with a bounded history for replay. Lives on one event loop."""

    def __init__(self, history: int = 2000) -> None:
        self._seq = itertools.count(1)
        self._history: deque[AgentEvent] = deque(maxlen=history)
        self._subscribers: set[asyncio.Queue[AgentEvent]] = set()

    def publish(self, event: AgentEvent) -> AgentEvent:
        event.seq = next(self._seq)
        self._history.append(event)
        for queue in list(self._subscribers):
            # A stuck client must not block agents; it can resume with ?since=.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)
        return event

    def emit(self, type_: EventType, run_id: str, agent_id: str | None = None, **data: Any) -> AgentEvent:
        return self.publish(AgentEvent(type=type_, run_id=run_id, agent_id=agent_id, data=data))

    def history(self, run_id: str | None = None, since: int = 0) -> list[AgentEvent]:
        return [e for e in self._history if e.seq > since and (run_id is None or e.run_id == run_id)]

    async def subscribe(self, run_id: str | None = None, since: int = 0) -> AsyncIterator[AgentEvent]:
        async for event in self.stream(run_id, since):
            if event is not None:
                yield event

    async def stream(
        self, run_id: str | None = None, since: int = 0, keepalive_s: float | None = None
    ) -> AsyncIterator[AgentEvent | None]:
        """Replay history after `since`, then live events. Yields None after `keepalive_s` without an event.

        The timeout wraps `queue.get()` (safe to cancel), never the generator itself: cancelling a pending
        `__anext__()` would close the generator and end the stream.
        """
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        try:
            last = since
            for event in self.history(run_id, since):
                last = event.seq
                yield event
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=keepalive_s)
                except TimeoutError:
                    yield None
                    continue
                if event.seq <= last or (run_id is not None and event.run_id != run_id):
                    continue
                last = event.seq
                yield event
        finally:
            self._subscribers.discard(queue)
