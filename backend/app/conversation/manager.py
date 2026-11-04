"""The conversation lane (PRD F3, F5): stays responsive while the inference lane (agents + Verifier) runs.

A turn with nothing running starts a run. A turn during a run is classified: a backchannel gets no reply, a status
question is answered from real events, an amendment offers cancel-and-re-run with the edited request, a new question
joins a first-in-first-out queue and is offered after delivery, and stop cancels.

The lane never states a figure. Numbers belong to the inference lane, where the Verifier checks them. Narration comes
from templates over real events, so it cannot invent progress. The optional fast model only rephrases a status reply
or asks the assumption question, under a short timeout, and any reply with a figure in it is thrown away.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.agents.events import AgentEvent, EventBus, EventType
from app.agents.graph import AgentOrchestrator, RunContext
from app.agents.verifier import extract_figures
from app.conversation.classifier import Classified, TurnClassifier, TurnKind
from app.conversation.contexts import GlobalContext, LocalContext, RunSnapshot
from app.llm.base import LLMError, LLMProvider, Message

MAX_SESSIONS = 100
ASSUMPTION_QUESTION = "While the team works: which assumption here would change your mind if it turned out wrong?"
FAST_SYSTEM = (
    "You are the quick voice of FounderOS, speaking while a team of agents works. Reply in one short sentence, to "
    '"you", the founder. Use only what you are given. Never state a number, amount or date.'
)


class Amendment(BaseModel):
    id: str
    run_id: str
    text: str
    edited_message: str
    status: str = "offered"


class QueuedQuestion(BaseModel):
    id: str
    text: str
    status: str = "queued"


class TurnOutcome(BaseModel):
    session_id: str
    kind: TurnKind | None = Field(default=None, description="Empty when the turn started a run with nothing running")
    classified_by: str | None = None
    reply: str = ""
    run_id: str | None = Field(default=None, description="The run this turn started, or the one still running")
    amendment_id: str | None = None
    queue_id: str | None = None


class Session:
    def __init__(self, session_id: str, quiet: bool) -> None:
        self.id = session_id
        self.quiet = quiet
        self.local = LocalContext()
        self.run_id: str | None = None
        self.queue: list[QueuedQuestion] = []
        self.amendments: dict[str, Amendment] = {}
        self.narration: list[str] = []
        self.narrators: set[asyncio.Task[None]] = set()


class ConversationError(ValueError):
    """The founder acted on something that is gone or not on offer (the API answers 409)."""


class ConversationManager:
    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        *,
        classifier: TurnClassifier | None = None,
        fast: LLMProvider | None = None,
        fast_timeout_s: float = 4.0,
        global_context: Callable[[], GlobalContext] = GlobalContext,
        quiet: bool = False,
    ) -> None:
        self.orchestrator = orchestrator
        self.bus: EventBus = orchestrator.bus
        self.classifier = classifier or TurnClassifier(orchestrator.decisions, fast_timeout_s)
        self.fast = fast
        self.fast_timeout_s = fast_timeout_s
        self.global_context = global_context
        self.default_quiet = quiet
        self.sessions: dict[str, Session] = {}

    # --- sessions --------------------------------------------------------------------------------------------------
    def session(self, session_id: str | None = None) -> Session:
        sid = session_id or f"ses_{uuid.uuid4().hex[:10]}"
        if sid not in self.sessions:
            for old in [s for s in self.sessions if not self._active(self.sessions[s])][: -MAX_SESSIONS + 1 or None]:
                if len(self.sessions) >= MAX_SESSIONS:
                    del self.sessions[old]
            self.sessions[sid] = Session(sid, self.default_quiet)
        return self.sessions[sid]

    def _running(self, session: Session) -> RunContext | None:
        run = self.orchestrator.runs.get(session.run_id) if session.run_id else None
        return run if run is not None and run.task is not None and not run.task.done() else None

    def _active(self, session: Session) -> bool:
        return self._running(session) is not None

    def state(self, session_id: str) -> dict[str, Any] | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        run = self.orchestrator.runs.get(session.run_id) if session.run_id else None
        return {
            "session_id": session.id,
            "quiet": session.quiet,
            "run_id": session.run_id,
            "running": self._active(session),
            "snapshot": run.context.model_dump(mode="json") if run is not None and run.context is not None else None,
            "queue": [q.model_dump() for q in session.queue],
            "amendments": [a.model_dump() for a in session.amendments.values()],
            "narration": session.narration[-20:],
            "recent_turns": [t.model_dump() for t in session.local.recent()],
        }

    def _emit(self, session: Session, type_: EventType, **data: Any) -> None:
        self.bus.emit(type_, session.run_id or session.id, session_id=session.id, **data)

    def _say(self, session: Session, text: str, type_: EventType = "narration") -> None:
        """Narration, unless the founder asked for quiet."""
        if session.quiet:
            return
        session.narration.append(text)
        session.local.add("lane", text)
        self._emit(session, type_, text=text)

    # --- runs ------------------------------------------------------------------------------------------------------
    def _start_run(self, session: Session, message: str, amendment_of: str | None = None) -> RunContext:
        snapshot = RunSnapshot(
            session_id=session.id,
            message=message,
            workspace=self.global_context(),
            recent_turns=session.local.recent(),
            amendment_of=amendment_of,
        )
        run = self.orchestrator.start(message, context=snapshot)
        session.run_id = run.run_id
        task = asyncio.create_task(self._narrate(session, run.run_id))
        session.narrators.add(task)
        task.add_done_callback(session.narrators.discard)
        return run

    async def _narrate(self, session: Session, run_id: str) -> None:
        """Follows one run's real events until it finishes."""
        asked = False
        try:
            async for event in self.bus.subscribe(run_id):
                if event.type == "run.finished":
                    self._finished(session, run_id, event)
                    return
                if event.type == "team.approved" and not asked:
                    asked = True
                    self._say(session, await self._assumption_question(session, run_id))
                text = self._line_for(run_id, event)
                if text:
                    self._say(session, text)
        except Exception:  # the lane must never disturb the run it is describing
            logger.exception("Narration of {} stopped", run_id)

    def _agent_name(self, run_id: str, agent_id: str | None) -> str:
        run = self.orchestrator.runs.get(run_id)
        team = run.plan.team if run is not None and run.plan is not None else []
        return next((i.name for i in team if i.id == agent_id), "An agent")

    def _line_for(self, run_id: str, event: AgentEvent) -> str:
        """One template per real event, none with a figure in it."""
        data = event.data
        if event.type == "team.proposed":
            names = ", ".join(i["name"] for i in data.get("team", []))
            if not names:
                return ""
            return (
                f"Waiting for your approval of this team: {names}." if data.get("needs_approval") else f"Team: {names}."
            )
        name = self._agent_name(run_id, event.agent_id)
        if event.type == "agent.status" and data.get("status") == "waiting_cloud":
            return f"{name} is waiting for a cloud model."
        if event.type == "agent.step" and "sent back by the Verifier" in str(data.get("step", "")):
            return f"The Verifier sent {name} back to check a figure."
        if event.type == "agent.rerun":
            return f"{name} restarted with your edited brief."
        if event.type == "agent.done":
            if data.get("status") == "done":
                return f"{name} finished." if data.get("verified") else f"{name} finished, with something unverified."
            return f"{name} stopped: {data.get('status')}."
        return ""

    def _finished(self, session: Session, run_id: str, event: AgentEvent) -> None:
        status = event.data.get("status")
        recap = {"cancelled": "That run was cancelled.", "failed": "That run failed."}.get(
            str(status),
            "The answer is ready."
            if event.data.get("verified")
            else "The answer is ready, but some of it is unverified.",
        )
        self._say(session, recap, "recap")
        if session.run_id == run_id:
            self._offer_next(session)

    def _offer_next(self, session: Session) -> None:
        head = next((q for q in session.queue if q.status in ("queued", "offered")), None)
        if head is None or head.status == "offered":
            return
        head.status = "offered"
        self._emit(session, "queue.offered", queue_id=head.id, text=head.text)

    async def _fast_line(self, instruction: str, fallback: str, session: Session) -> str:
        """The small model's wording, or the template when it is absent, slow, down, or states a figure."""
        if self.fast is None:
            return fallback
        recent = "\n".join(f"{t.role}: {t.text}" for t in session.local.recent()[-6:])
        messages = [Message.system(FAST_SYSTEM), Message.user(f"{recent}\n\n{instruction}")]
        try:
            completion = await asyncio.wait_for(self.fast.complete(messages), timeout=self.fast_timeout_s)
        except (TimeoutError, LLMError) as exc:
            logger.info("Fast lane using its template: {}", type(exc).__name__)
            return fallback
        text = (completion.text or "").strip()
        return text if text and not extract_figures(text) else fallback

    async def _assumption_question(self, session: Session, run_id: str) -> str:
        run = self.orchestrator.runs.get(run_id)
        request = run.message if run is not None else ""
        return await self._fast_line(
            f"The founder asked: {request}\nAsk one question about an assumption this depends on.",
            ASSUMPTION_QUESTION,
            session,
        )

    def _status_text(self, run: RunContext) -> str:
        if run.plan is None:
            return "The team is still being chosen."
        if not run.approval.is_set() and self.orchestrator.needs_approval(run.plan.team):
            return "The team is waiting for your approval."
        finished = {e.agent_id for e in self.bus.history(run.run_id) if e.type == "agent.done"}
        done = [i.name for i in run.plan.team if i.id in finished]
        working = [i.name for i in run.plan.team if i.id in run.agent_tasks]
        waiting = [i.name for i in run.plan.team if i.id not in finished and i.id not in run.agent_tasks]
        if not working and not waiting:
            return f"Finished: {', '.join(done)}. The answer is being written."
        parts = [f"Working: {', '.join(working)}." if working else ""]
        parts.append(f"Finished: {', '.join(done)}." if done else "")
        parts.append(f"Still to start: {', '.join(waiting)}." if waiting else "")
        return " ".join(p for p in parts if p)

    # --- turns -----------------------------------------------------------------------------------------------------
    async def turn(self, session_id: str | None, text: str) -> TurnOutcome:
        session = self.session(session_id)
        running = self._running(session)
        session.local.add("founder", text)
        if running is None:
            return await self._turn_when_idle(session, text)
        classified = await self.classifier.classify(text, running.message)
        self._emit(session, "turn.classified", kind=classified.kind, by=classified.by, text=text)
        match classified.kind:
            case "backchannel":
                outcome = self._reply(session, classified, "", running.run_id)
            case "answerable_now":
                reply = await self._fast_line(
                    f"The founder asked: {text}\nThe status is: {self._status_text(running)}",
                    self._status_text(running),
                    session,
                )
                outcome = self._reply(session, classified, reply, running.run_id)
            case "stop":
                self.orchestrator.cancel(running.run_id)
                outcome = self._reply(session, classified, "Stopping the team.", running.run_id)
            case "amendment":
                outcome = self._offer_amendment(session, classified, running, text)
            case _:
                outcome = self._enqueue(session, classified, running, text)
        return outcome

    async def _turn_when_idle(self, session: Session, text: str) -> TurnOutcome:
        classified = await self.classifier.classify(text, "")
        if classified.kind == "backchannel":
            return self._reply(session, classified, "", session.run_id)
        if classified.kind == "stop":
            return self._reply(session, classified, "Nothing is running.", session.run_id)
        run = self._start_run(session, text)
        return TurnOutcome(session_id=session.id, reply="", run_id=run.run_id)

    def _reply(self, session: Session, classified: Classified, reply: str, run_id: str | None) -> TurnOutcome:
        if reply:
            session.local.add("lane", reply)
        return TurnOutcome(
            session_id=session.id, kind=classified.kind, classified_by=classified.by, reply=reply, run_id=run_id
        )

    def _offer_amendment(self, session: Session, classified: Classified, running: RunContext, text: str) -> TurnOutcome:
        amendment = Amendment(
            id=f"amd_{uuid.uuid4().hex[:8]}",
            run_id=running.run_id,
            text=text,
            edited_message=f"{running.message}\nThe founder then added: {text}",
        )
        session.amendments[amendment.id] = amendment
        reply = "That changes the request. Cancel this run and start again with your change?"
        self._emit(session, "amendment.offered", amendment_id=amendment.id, text=text, reply=reply)
        outcome = self._reply(session, classified, reply, running.run_id)
        return outcome.model_copy(update={"amendment_id": amendment.id})

    def _enqueue(self, session: Session, classified: Classified, running: RunContext, text: str) -> TurnOutcome:
        item = QueuedQuestion(id=f"que_{uuid.uuid4().hex[:8]}", text=text)
        session.queue.append(item)
        waiting = sum(q.status in ("queued", "offered") for q in session.queue)
        self._emit(session, "queue.added", queue_id=item.id, text=text, position=waiting)
        reply = "I'll keep that for when this run finishes."
        outcome = self._reply(session, classified, reply, running.run_id)
        return outcome.model_copy(update={"queue_id": item.id})

    # --- what the founder answers ----------------------------------------------------------------------------------
    def set_quiet(self, session_id: str, quiet: bool) -> Session:
        session = self.session(session_id)
        session.quiet = quiet
        return session

    def answer_amendment(self, session_id: str, amendment_id: str, accept: bool) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        amendment = session.amendments.get(amendment_id) if session else None
        if session is None or amendment is None or amendment.status != "offered":
            raise ConversationError("no such amendment on offer")
        amendment.status = "accepted" if accept else "declined"
        if not accept:
            return {"accepted": False, "run_id": session.run_id}
        self.orchestrator.cancel(amendment.run_id)
        run = self._start_run(session, amendment.edited_message, amendment_of=amendment.run_id)
        return {"accepted": True, "run_id": run.run_id, "replaces": amendment.run_id}

    def answer_queue(self, session_id: str, queue_id: str, accept: bool) -> dict[str, Any]:
        """Only the offered question can be answered, so the order stays first in, first out."""
        session = self.sessions.get(session_id)
        item = next((q for q in session.queue if q.id == queue_id), None) if session else None
        if session is None or item is None or item.status != "offered":
            raise ConversationError("that question is not on offer")
        if accept and self._active(session):
            raise ConversationError("a run is still working")
        item.status = "started" if accept else "dismissed"
        session.queue.remove(item)
        if not accept:
            self._offer_next(session)
            return {"accepted": False, "run_id": None}
        return {"accepted": True, "run_id": self._start_run(session, item.text).run_id}
