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
import re
import uuid
from collections.abc import Callable
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.agents.decision_frame import inputs_question, parse_inputs
from app.agents.events import AgentEvent, EventBus, EventType
from app.agents.graph import AgentOrchestrator, RunContext
from app.agents.registry import REGISTRY
from app.agents.runtime import Plan
from app.agents.verifier import extract_figures
from app.conversation.classifier import Classified, TurnClassifier, TurnKind, by_rules
from app.conversation.contexts import GlobalContext, LocalContext, RunSnapshot
from app.llm.base import LLMError, LLMProvider, Message

MAX_SESSIONS = 100
ASSUMPTION_QUESTION = 'While the team works on "{request}": which assumption would change your mind if it were wrong?'
INPUTS_REPLY = "Those are your figures. Cancel this run and start again with them?"
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
        self.finished: dict[str, list[tuple[str, bool]]] = {}


_LEFT_IN_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _same(a: str, b: str) -> bool:
    """The same question, whatever its case, spacing or end mark."""

    def key(t: str) -> str:
        return re.sub(r"[\s?.!]+", " ", t).strip().lower()

    return key(a) == key(b)


def _in_words(count: int) -> str:
    """The lane never states a figure, and a count of agents is no exception: it would fail the same check."""
    return _LEFT_IN_WORDS.get(count, "more")


def _topic(request: str) -> str:
    first = request.strip().splitlines()[0] if request.strip() else "this"
    first = re.split(r"(?<=[.!?])\s+", first)[0].rstrip("?.! ")
    return first if len(first) <= 60 else first[:57].rstrip() + "..."


def _ready_line(data: dict[str, Any]) -> str:
    if data.get("assumptions"):
        return "The answer is ready. It rests on assumptions you should confirm."
    return "The answer is ready." if data.get("verified") else "The answer is ready, but some of it is unverified."


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
            idle = [s for s in self.sessions.values() if not self._active(s)]
            for old in idle[: max(0, len(self.sessions) - MAX_SESSIONS + 1)]:
                del self.sessions[old.id]
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
    def _same_decision(self, run_id: str) -> Plan | None:
        """A change to a decision re-runs that decision: the same type and team, with fresh agents. The frame is
        rebuilt from the edited request in code, so "make it a two person team" sets local hires to 2."""
        run = self.orchestrator.runs.get(run_id)
        old = run.plan if run is not None else None
        if old is None or not self._is_decision(run_id):
            return None
        team = [i.model_copy(update={"id": f"agt_{uuid.uuid4().hex[:8]}"}) for i in old.team]
        frame = None if old.intent == "decision" else old.frame
        return old.model_copy(update={"team": team, "frame": frame})

    def _start_run(
        self, session: Session, message: str, amendment_of: str | None = None, plan_override: Plan | None = None
    ) -> RunContext:
        snapshot = RunSnapshot(
            session_id=session.id,
            message=message,
            workspace=self.global_context(),
            recent_turns=session.local.recent(),
            amendment_of=amendment_of,
        )
        run = self.orchestrator.start(message, context=snapshot, plan_override=plan_override)
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
                    # A metric lookup rests on no assumption to question (founder review 9): only a decision is asked.
                    if self._is_decision(run_id):
                        self._say(session, await self._assumption_question(session, run_id))
                text = self._grouped_line(session, run_id, event) or self._line_for(run_id, event)
                if text.strip():
                    self._say(session, text)
        except Exception:  # the lane must never disturb the run it is describing
            logger.exception("Narration of {} stopped", run_id)

    def _grouped_line(self, session: Session, run_id: str, event: AgentEvent) -> str:
        """Agents that work together are reported together, when the last of them ends. No figures."""
        ended = event.type == "agent.done" or (event.type == "agent.status" and event.data.get("status") == "cancelled")
        run = self.orchestrator.runs.get(run_id)
        team = run.plan.team if run is not None and run.plan is not None else []
        inst = next((i for i in team if i.id == event.agent_id), None)
        if not ended or inst is None:
            return ""
        verified = bool(event.data.get("verified")) and event.data.get("status", "done") == "done"
        ended_so_far = session.finished.setdefault(run_id, [])
        ended_so_far.append((inst.id, verified))
        ids = {agent_id for agent_id, _ in ended_so_far}
        stage = REGISTRY[inst.type].stage
        wave = [i for i in team if REGISTRY[i.type].stage == stage]
        if any(i.id not in ids for i in wave):
            return " "  # held until the rest of its wave ends
        names = [i.name for i in wave]
        joined = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        left = sum(i.id not in ids for i in team)
        next_step = "writing your answer now" if not left else f"{_in_words(left)} to go"
        verb = "is" if len(names) == 1 else "are"
        doubts = [i.name for i in wave if not dict(ended_so_far).get(i.id)]
        caveat = f" Something from {' and '.join(doubts)} is unverified." if doubts else ""
        return f"{joined} {verb} done; {next_step}.{caveat}"

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
        return ""

    def _finished(self, session: Session, run_id: str, event: AgentEvent) -> None:
        status = event.data.get("status")
        recap = {
            "cancelled": "That run was cancelled.",
            "failed": "That run failed.",
            "rejected": "The team was not approved, so nothing ran.",
        }.get(
            str(status),
            _ready_line(event.data),
        )
        self._say(session, recap, "recap")
        if session.run_id == run_id:
            self._offer_next(session)
        self._close_offers(session, keep=session.run_id if session.run_id != run_id else None)

    @staticmethod
    def _close_offers(session: Session, keep: str | None = None) -> None:
        """An amendment changes one run. Once that run has ended or been replaced, the offer is over."""
        for amendment in session.amendments.values():
            if amendment.status == "offered" and amendment.run_id != keep:
                amendment.status = "expired"

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

    def _is_decision(self, run_id: str) -> bool:
        run = self.orchestrator.runs.get(run_id)
        plan = run.plan if run is not None else None
        return plan is not None and (plan.intent == "decision" or plan.frame is not None)

    async def _assumption_question(self, session: Session, run_id: str) -> str:
        run = self.orchestrator.runs.get(run_id)
        request = run.message if run is not None else ""
        frame = run.plan.frame if run is not None and run.plan is not None else None
        specific = inputs_question(frame) if frame is not None else ""
        if specific:
            return specific
        return await self._fast_line(
            f"The founder asked: {request}\nAsk one question about an assumption this depends on.",
            ASSUMPTION_QUESTION.format(request=_topic(request)),
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
        if self._gives_inputs(running, text):
            classified = Classified(kind="amendment", by="rules")
            outcome = self._offer_amendment(session, classified, running, text)
            return outcome.model_copy(update={"reply": INPUTS_REPLY})
        classified = await self.classifier.classify(text, running.message)
        running = self._running(session)  # the run may have ended while the classifier was thinking
        if running is None:
            return await self._turn_when_idle(session, text)
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

    @staticmethod
    def _gives_inputs(run: RunContext | None, text: str) -> bool:
        """The founder answering the question the lane asked: figures for this decision's own cost inputs."""
        frame = run.plan.frame if run is not None and run.plan is not None else None
        if frame is None or not frame.questions or text.rstrip().endswith("?"):
            return False
        return bool(parse_inputs(text, frame.type))

    async def _turn_when_idle(self, session: Session, text: str) -> TurnOutcome:
        """Rules only. With nothing to protect, an unclear turn is simply a request: no model call before the run."""
        last = self.orchestrator.runs.get(session.run_id) if session.run_id else None
        if self._gives_inputs(last, text) and last is not None:
            edited = f"{last.message}\nThe founder then added: {text}"
            run = self._start_run(
                session, edited, amendment_of=last.run_id, plan_override=self._same_decision(last.run_id)
            )
            return TurnOutcome(
                session_id=session.id,
                kind="amendment",
                classified_by="rules",
                reply="Running it again with your figures.",
                run_id=run.run_id,
            )
        kind = by_rules(text)
        # A decision is still open on screen: a follow-up ("also…", "make it…", "what if…") changes that decision.
        if kind == "amendment" and last is not None and self._is_decision(last.run_id):
            return self._offer_amendment(session, Classified(kind=kind, by="rules"), last, text)
        if kind == "backchannel":
            return self._reply(session, Classified(kind=kind, by="rules"), "", session.run_id)
        if kind == "stop":
            return self._reply(session, Classified(kind=kind, by="rules"), "Nothing is running.", session.run_id)
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
        finished = running.task is not None and running.task.done()
        reply = (
            "That changes the decision. Restart with your change?"
            if finished
            else "That changes the request. Cancel this run and start again with your change?"
        )
        self._emit(session, "amendment.offered", amendment_id=amendment.id, text=text, reply=reply)
        outcome = self._reply(session, classified, reply, running.run_id)
        return outcome.model_copy(update={"amendment_id": amendment.id})

    def _enqueue(self, session: Session, classified: Classified, running: RunContext, text: str) -> TurnOutcome:
        same = next((q for q in session.queue if q.status in ("queued", "offered") and _same(q.text, text)), None)
        if same is not None:  # asked twice while waiting: one card, kept where it was
            outcome = self._reply(session, classified, "That question is already queued.", running.run_id)
            return outcome.model_copy(update={"queue_id": same.id})
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
        self._close_offers(session)
        run = self._start_run(
            session,
            amendment.edited_message,
            amendment_of=amendment.run_id,
            plan_override=self._same_decision(amendment.run_id),
        )
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
