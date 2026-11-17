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

from app.agents.decision_frame import _NUMBER_WORDS as _COUNT_NAMES
from app.agents.decision_frame import _place, inputs_question, parse_inputs, units_of
from app.agents.events import AgentEvent, EventBus, EventType
from app.agents.graph import AgentOrchestrator, RunContext
from app.agents.registry import REGISTRY
from app.agents.runtime import Plan, single_metric
from app.agents.verifier import extract_figures, split_sentences
from app.conversation.classifier import (
    Classified,
    TurnClassifier,
    TurnKind,
    by_rules,
    clear_request,
    is_filler,
    is_greeting,
    is_leave,
    is_noise,
    plain,
)
from app.conversation.contexts import GlobalContext, LocalContext, RunSnapshot
from app.llm.base import LLMError, LLMProvider, Message
from app.voice.domain import count_reading
from app.voice.spoken import summarise

MAX_SESSIONS = 100
ASSUMPTION_QUESTION = 'While the team works on "{request}": which assumption would change your mind if it were wrong?'
RESTART_OFFER = "That changes the decision. Restart with your change?"
RESTART_REQUEST = "That changes the request. Restart with your change?"
# A change offered while the team worked and not answered by the time the answer was ready (founder re-test S4).
CHANGE_STILL_OPEN = "You asked for a change while the team worked, and this answer does not have it. Restart with it?"
GREETING = "Hello. What would you like to look at?"
LEAVE = "Okay, leaving it as it is."
UNCLEAR = "I'm not sure what you'd like me to look at. Ask it as a question, or name the decision."
_CHANGE_WORDS = re.compile(
    r"^(?:(?:actually|also|and|so|wait|ok|okay|please|sorry)[,\s]+)*(?:assume|assuming|make it|change it to|use)\s+",
    re.I,
)


def change_reminder(change: str) -> str:
    """The one spoken reminder after an answer that does not have the founder's change (founder decision
    2026-11-15): "Your change to three hires isn't in this answer yet. Say yes to restart with it." """
    what = change.strip().rstrip(".!? ")
    short = _CHANGE_WORDS.sub("", what)
    named = f"to {short}" if short != what else f'"{what}"'
    return f"Your change {named} isn't in this answer yet. Say yes to restart with it."


def _distance(a: str, b: str) -> int:
    """Edit distance, for an agent's name as the recogniser heard it ("Analyt" for "analyst")."""
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def fuzzy_agent(said: str) -> tuple[str, str, int, bool] | None:
    """The agent a re-run names, heard imperfectly (founder re-test U3): (kind, alias, words used, sure). Sure: the
    heard words are a prefix of the name ("analyt", "devil") or one letter off; unsure: two letters off."""
    words = re.findall(r"[a-z']+", said.lower().replace("\u2019", "'"))
    best: tuple[int, str, str, int] | None = None
    for kind, names in AGENT_ALIASES.items():
        for alias in names:
            parts = alias.split()
            for n in {1, len(parts)}:
                head = " ".join(words[:n])
                target = " ".join(parts[:n])
                if len(head) < 4:
                    continue
                score = 0 if target.startswith(head) or head.startswith(target) else _distance(head, target)
                if score <= 2 and (best is None or score < best[0]):
                    best = (score, kind, alias, n)
    if best is None:
        return None
    score, kind, alias, n = best
    return kind, alias, n, score <= 1


# A follow-up names its subject only by reference: "and what about churn?", "how about burn?" (founder decision D).
_WHAT_ABOUT = re.compile(
    r"^(?:(?:and|so|ok|okay|then|also|now)[,\s]+)*(?:(?:what|how)\s+about|and)\s+(?:our\s+|the\s+|my\s+)?"
    r"(?P<rest>[^?]+?)\s*\??$",
    re.I,
)
# "Why that option?", "why this one?", "why not the full office?": answered from the open decision, by code.
_WHY_OPTION = re.compile(
    r"^(?:(?:and|but|so|ok|okay)[,\s]+)*why\b(?:\s*\??$|.*\b(?:that|this|the)\s+(?:option|one|proposal|choice|pick)\b|"
    r"\s+(?:that|this|it)\s*\??$|\s+not\b)",
    re.I,
)
# "Re-run the analyst, assume three hires", "redo the Devil's Advocate" (founder decision E).
_RERUN = re.compile(
    r"^(?:please\s+|can you\s+|could you\s+)?(?:re-?\s?run|re-?\s?ran|redo|re-do)\s+(?:the\s+)?(?P<rest>.+)$", re.I
)
AGENT_ALIASES: dict[str, tuple[str, ...]] = {
    "financial_analyst": ("financial analyst", "finance analyst", "analyst", "financials", "finance"),
    "librarian": ("librarian",),
    "market_scout": ("market scout", "scout"),
    "revenue_customer": ("revenue and customer", "revenue & customer", "revenue"),
    "people_ops": ("people and ops", "people & ops", "people and operations", "people ops", "people"),
    "regulatory_tax": ("regulatory and tax", "regulatory & tax", "regulatory", "tax"),
    "prioritiser": ("prioritiser", "prioritizer"),
    "perspective_lens": ("perspective lens", "lens"),
    "devils_advocate": ("devil's advocate", "devils advocate", "advocate"),
    "memo_writer": ("memo writer", "memo"),
}
STOP_QUESTION = "Stop the team? Say yes to stop."
# Answers to the one yes/no question the lane has open (founder re-test R1, R3, R8). Naming the action again counts
# as yes ("stop", "restart"); "keep going" counts as no.
_YES = re.compile(
    r"^(?:(?:yes|yeah|yep|yup|sure|ok|okay|correct|right|exactly|that's right|that is right|do it|go ahead|"
    r"please do|confirm|i did|i do)\b[\s.!,]*)+"
    # M6a carry-over: "Yes, thank you." and "Yes sir." are a yes too.
    r"(?:please|thanks|thank you|sir|stop(?: it| the team)?|restart(?: it)?|ask it|i did)?"
    r"[\s.!]*$",
    re.I,
)
_NO = re.compile(
    r"^(?:(?:no|nope|nah|no thanks|no thank you|don't|do not|leave it|keep (?:it )?going|carry on|not that|"
    r"that's wrong|wrong)\b[\s.!,]*)+(?:keep (?:it )?going|carry on|drop it|don't stop)?[\s.!]*$",
    re.I,
)
_YES_BY_KIND = {
    "stop": re.compile(r"^(?:please\s+)?(?:stop|cancel|halt)(?:\s+(?:it|the team|now|please))*[\s.!]*$", re.I),
    "amendment": re.compile(
        r"^(?:(?:yes|yeah|yep|ok|okay|sure|please)\s+)?restart(?: it| with (?:it|my change|the change|that))?"
        r"(?:\s+please)?$",
        re.I,
    ),
    "queue": re.compile(r"^ask it(?: now)?[\s.!]*$", re.I),
    "more": re.compile(
        r"^(?:(?:yes|yeah|ok|okay|sure|please)\s+)?(?:go through|tell me|what are|give me)?\s*(?:the|them)?\s*"
        r"risks?(?:\s+please)?$",
        re.I,
    ),
}
_NO_BY_KIND = {"queue": re.compile(r"^(?:drop|skip) it[\s.!]*$", re.I)}
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


class Asked(BaseModel):
    """The one yes/no question the lane has open. The next turn answers it, or it lapses."""

    kind: str  # stop | amendment | queue | number | said
    ref: str = ""  # the run to stop, the amendment or the queued question on offer
    text: str = ""  # number: the founder's turn as it will be read if they say yes


class TurnOutcome(BaseModel):
    session_id: str
    kind: TurnKind | None = Field(default=None, description="Empty when the turn started a run with nothing running")
    classified_by: str | None = None
    reply: str = ""
    run_id: str | None = Field(default=None, description="The run this turn started, or the one still running")
    amendment_id: str | None = None
    queue_id: str | None = None
    started_run: bool = Field(default=False, description="This turn started the run in `run_id`")
    answered: dict[str, Any] | None = Field(
        default=None,
        description='This turn answered an offer on screen: {"what": "amendment" | "queue", "id": ..., "accept": ...}',
    )


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
        self.last_wave: list[dict[str, Any]] = []  # the stage the last grouped line reported, for the voice
        self.decision_run_id: str | None = None  # the last decision answered: what "that option" refers to
        self.asked: Asked | None = None
        self.more: tuple[str, str, list[str]] | None = None  # founder W3: (run, the offer, what yes says)


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
    if data.get("team_ran") is False:
        return ""  # founder re-test T4: no team ran, so there is nothing to call verified or unverified
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

    def _say(self, session: Session, text: str, type_: EventType = "narration", **extra: Any) -> None:
        """Narration, unless the founder asked for quiet. `extra` says what kind of line it is (the voice speaks a
        team line and one line a stage, not every step)."""
        if session.quiet:
            return
        session.narration.append(text)
        session.local.add("lane", text)
        self._emit(session, type_, text=text, **extra)

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
        self,
        session: Session,
        message: str,
        amendment_of: str | None = None,
        plan_override: Plan | None = None,
        reuse: dict[str, Any] | None = None,
    ) -> RunContext:
        session.asked = None  # a new run: whatever was being asked about the old one is over
        session.more = None
        snapshot = RunSnapshot(
            session_id=session.id,
            message=message,
            workspace=self.global_context(),
            recent_turns=session.local.recent(),
            amendment_of=amendment_of,
        )
        run = self.orchestrator.start(message, context=snapshot, plan_override=plan_override, reuse=reuse)
        session.run_id = run.run_id
        task = asyncio.create_task(self._narrate(session, run.run_id))
        session.narrators.add(task)
        task.add_done_callback(session.narrators.discard)
        return run

    async def _narrate(self, session: Session, run_id: str) -> None:
        """Follows one run's real events until it finishes."""
        asked = False
        run = self.orchestrator.runs.get(run_id)
        # Founder RZ re-test S6: a re-run of one agent was announced like a new team ("Team: …", the inputs question,
        # "Financial Analyst is done; writing your answer now."). Its reply already said who redoes what.
        redo = run is not None and bool(run.reuse)
        try:
            async for event in self.bus.subscribe(run_id):
                if event.type == "run.finished":
                    self._finished(session, run_id, event)
                    return
                if event.type == "team.approved" and not asked:
                    asked = True
                    # A metric lookup rests on no assumption to question (founder review 9): only a decision is asked.
                    if self._is_decision(run_id) and not redo:
                        self._say(session, await self._assumption_question(session, run_id), kind="question")
                session.last_wave = []
                text = self._grouped_line(session, run_id, event) or self._line_for(run_id, event)
                if redo and (event.type == "team.proposed" or session.last_wave):
                    continue
                if text.strip():
                    self._say(session, text, **self._line_kind(session, run_id, event))
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
        # Founder note 60: a held-back team's agents are "cancelled" without ever starting. That is not "done".
        if not any(e.type == "agent.spawned" and e.agent_id == inst.id for e in self.bus.history(run_id)):
            return " "
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
        outcome = {e.agent_id: e.data.get("status", "done") for e in self.bus.history(run_id) if e.type == "agent.done"}
        session.last_wave = [
            {
                "type": i.type,
                "name": i.name,
                "status": outcome.get(i.id, "cancelled"),
                "verified": bool(dict(ended_so_far).get(i.id)),
            }
            for i in wave
        ]
        caveat = f" Something from {' and '.join(doubts)} is unverified." if doubts else ""
        return f"{joined} {verb} done; {next_step}.{caveat}"

    def _line_kind(self, session: Session, run_id: str, event: AgentEvent) -> dict[str, Any]:
        """What a narration line is about, for a listener that says less than the screen shows."""
        run = self.orchestrator.runs.get(run_id)
        size = len(run.plan.team) if run is not None and run.plan is not None else 0
        if session.last_wave:
            return {"kind": "wave", "wave": session.last_wave, "team_size": size}
        if event.type == "team.proposed" and run is not None and run.reuse:
            return {"kind": "step"}  # one agent is redoing its part: the team was introduced the first time
        if event.type == "team.proposed":
            topic = run.plan.frame.subject if run is not None and run.plan is not None and run.plan.frame else ""
            team = [{"type": i.get("type"), "name": i.get("name")} for i in event.data.get("team", [])]
            return {"kind": "approval" if event.data.get("needs_approval") else "team", "team": team, "topic": topic}
        if event.type == "team.rejected":
            return {"kind": "held"}
        return {"kind": "step"}

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
        if event.type == "team.rejected":
            return "I held the team back: no agent ran."
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
        self._remember_answer(session, run_id)
        offer = self._more_offer(session, run_id) if status in (None, "done") and recap else ""
        if recap:
            self._say(session, f"{recap} {offer}".strip(), "recap", status=str(status or "done"), offer=offer)
        # Founder re-test S4: a change the founder asked for while the team worked, and never answered, is not lost
        # when the answer arrives without it. Its offer stays open on this finished run: "yes" still restarts, and
        # its card still works. Founder re-test T3: one change, one offer, one card, so the lane adds no second
        # line here (the voice asks again only if its offer was never said aloud).
        unanswered = next(
            (
                a
                for a in session.amendments.values()
                if a.status == "offered" and a.run_id == run_id == session.run_id and status in (None, "done")
            ),
            None,
        )
        if unanswered is not None:
            session.asked = Asked(kind="amendment", ref=unanswered.id)
            session.more = None
        elif session.more is not None and session.more[0] == run_id and session.asked is None:
            session.asked = Asked(kind="more", ref=run_id)
        # Founder re-test 56: every queued question is offered, one at a time, once nothing is running, whichever run
        # ended (the session may have moved on to a restarted run that has already finished).
        if session.run_id == run_id or not self._active(session):
            self._offer_next(session)
        keep = run_id if unanswered is not None else (session.run_id if session.run_id != run_id else None)
        self._close_offers(session, keep=keep)

    def _more_offer(self, session: Session, run_id: str) -> str:
        """Founder W3: a decision answer ends on ONE offer ("Want me to go through the risks?"), shown and said once.
        None when a change is still open (yes means the restart) or a queued question waits (its offer comes first)."""
        session.more = None
        run = self.orchestrator.runs.get(run_id)
        result = run.result if run is not None else None
        if result is None or result.status != "done" or result.decision_frame is None or session.run_id != run_id:
            return ""
        if any(a.status == "offered" and a.run_id == run_id for a in session.amendments.values()):
            return ""
        if any(q.status in ("queued", "offered") for q in session.queue):
            return ""
        try:
            more = summarise(result).more
        except Exception:  # the offer is a courtesy: never let it break the end of a run
            logger.exception("No offer of more for {}", run_id)
            return ""
        if not more or not more[0].lines:
            return ""
        session.more = (run_id, more[0].offer, list(more[0].lines))
        return more[0].offer

    def more_taken(self, session_id: str) -> None:
        """The voice answered the offer of more itself: the lane's question is over."""
        session = self.sessions.get(session_id)
        if session is not None:
            session.more = None
            if session.asked is not None and session.asked.kind == "more":
                session.asked = None

    def _remember_answer(self, session: Session, run_id: str) -> None:
        """Founder decision D: a follow-up is answered in context, so the session keeps what was answered (its first
        sentences; the figures stay checked text, and the Advisor is told to restate none of them unsourced)."""
        run = self.orchestrator.runs.get(run_id)
        result = run.result if run is not None else None
        if result is None or result.status != "done" or not result.answer.strip():
            return
        first = [p.strip() for p in split_sentences(result.answer) if p.strip()][:2]
        session.local.add("advisor", " ".join(first)[:500])
        if result.decision_frame is not None:
            session.decision_run_id = run_id

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
        if session.asked is None:
            session.asked = Asked(kind="queue", ref=head.id)
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
    async def turn(self, session_id: str | None, text: str, *, spoken: bool = False) -> TurnOutcome:
        """`spoken`: the words came from the recogniser, not the keyboard. Only that changes how "stop" is taken
        (founder decision 2026-11-14): a typed "stop" stops the team at once, a spoken one is asked about first,
        because a recogniser can hear "stop" in a noise."""
        session = self.session(session_id)
        running = self._running(session)
        session.local.add("founder", text)
        answered = await self._answer_asked(session, text, spoken)
        if answered is not None:
            return answered
        if is_leave(text):
            return self._leave(session, running)
        unclear = self._unclear_number(session, running, text)
        if unclear is not None:
            return unclear
        rerun = self._rerun(session, text)
        if rerun is not None:
            return rerun
        if running is None:
            return await self._turn_when_idle(session, text)
        if self._gives_inputs(running, text):
            return self._offer_amendment(session, Classified(kind="amendment", by="rules"), running, text)
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
            case "stop" if not spoken:
                # Founder decision 2026-11-14: typed words are what the founder meant, so a typed "stop" stops at
                # once, like the Cancel button.
                self.orchestrator.cancel(running.run_id)
                outcome = self._reply(session, classified, "Stopping the team.", running.run_id)
            case "stop":
                # Founder re-test R1: a team is never cancelled on one hearing of one word. Ask, then stop on yes.
                session.asked = Asked(kind="stop", ref=running.run_id)
                asking = Classified(kind="confirm", by=classified.by)
                outcome = self._reply(session, asking, STOP_QUESTION, running.run_id)
            case "amendment":
                outcome = self._offer_amendment(session, classified, running, text)
            case _:
                outcome = self._enqueue(session, classified, running, text)
        return outcome

    def _leave(self, session: Session, running: RunContext | None) -> TurnOutcome:
        """Founder W4: "Ok, I will leave it as it is." keeps things as they are: a change still on its card is
        declined (as its "Keep going" button does), nothing is read back and no team starts."""
        change = next(
            (a for a in session.amendments.values() if a.status == "offered" and a.run_id == session.run_id), None
        )
        if change is not None:
            declined = self._accept(session, "amendment", change.id, False)
            if declined is not None:
                return declined
        rules = Classified(kind="backchannel", by="rules")
        return self._reply(session, rules, LEAVE, running.run_id if running is not None else session.run_id)

    # --- the lane's own yes/no questions (founder re-test R1, R3, R8) ----------------------------------------------
    def has_question(self, session_id: str, text: str) -> bool:
        """True when `text` answers the question the lane has open, so no other listener should take it."""
        session = self.sessions.get(session_id)
        asked = (session.asked or self._open_change(session, text)) if session is not None else None
        if asked is not None and asked.kind == "more":
            return False  # the voice says the risks itself, with their figures (the lane never states one)
        return asked is not None and self._yes_no(asked, text) is not None

    def _open_change(self, session: Session, text: str) -> Asked | None:
        """Founder RZ re-test S3: a change still on its card after the answer is the open question, even when a
        turn in between (a sound the recogniser wrote as a word) closed the lane's question. A plain yes or no
        answers it; nothing else does."""
        if self._active(session):
            return None
        change = next(
            (a for a in session.amendments.values() if a.status == "offered" and a.run_id == session.run_id), None
        )
        if change is None:
            return None
        asked = Asked(kind="amendment", ref=change.id)
        return asked if self._yes_no(asked, text) is not None else None

    @staticmethod
    def _yes_no(asked: Asked, text: str) -> bool | None:
        # Founder re-test T2: Whisper wrote a spoken "yes" as "Yes?", and it ran as a new question. An answer is the
        # same answer whatever its case and its marks: "Yes?", "yes.", "Yeah!", "okay?".
        words = plain(text)
        yes_too, no_too = _YES_BY_KIND.get(asked.kind), _NO_BY_KIND.get(asked.kind)
        if _YES.match(words) or (yes_too is not None and yes_too.match(words)):
            return True
        if _NO.match(words) or (no_too is not None and no_too.match(words)):
            return False
        return None

    async def _answer_asked(self, session: Session, text: str, spoken: bool = False) -> TurnOutcome | None:
        """Yes or no to what the lane asked. Any other turn is taken as itself: a stop or a number that was not
        confirmed lapses (nothing changed), while an offer with a card on screen stays on its card."""
        asked, session.asked = session.asked or self._open_change(session, text), None
        if asked is None:
            return None
        yes = self._yes_no(asked, text)
        if yes is None:
            if is_noise(text):
                # Founder re-test U2: a listening noise ("Ugh.", "mm") is never an answer, neither yes nor no:
                # whatever was asked is still the open question.
                session.asked = asked
            return None
        by = Classified(kind="answerable_now", by="rules")
        if asked.kind == "more":
            # Founder W3: yes walks through the risks briefly; no does nothing.
            more, session.more = session.more, None
            if not yes or more is None or more[0] != asked.ref:
                return self._reply(session, Classified(kind="backchannel", by="rules"), "", session.run_id)
            return self._reply(session, by, " ".join(more[2]), session.run_id)
        if asked.kind == "stop":
            running = self._running(session)
            if running is None or running.run_id != asked.ref:
                return None
            if not yes:
                return self._reply(session, by, "Okay, the team carries on.", running.run_id)
            self.orchestrator.cancel(running.run_id)
            return self._reply(session, Classified(kind="stop", by="rules"), "Stopping the team.", running.run_id)
        if asked.kind == "said":
            # Founder rule U0: an unclear turn was read back ("Did you say …?"). Yes runs it as it was said.
            if not yes:
                return self._reply(session, by, "Okay. Say it again.", session.run_id)
            run = self._start_run(session, asked.text)
            return TurnOutcome(session_id=session.id, reply="", run_id=run.run_id, started_run=True)
        if asked.kind == "number":
            if not yes:
                reply = "Okay, nothing has changed. Say the number with what it counts, for example three hires."
                return self._reply(session, by, reply, session.run_id)
            outcome = await self.turn(session.id, asked.text, spoken=spoken)
            if outcome.amendment_id:  # already confirmed once: the change is applied without a second question
                return self._accept(session, "amendment", outcome.amendment_id, True) or outcome
            return outcome
        return self._accept(session, asked.kind, asked.ref, yes)

    def answer_offer(self, session_id: str, what: str, ref: str, accept: bool) -> TurnOutcome | None:
        """For a listener that heard the answer itself (the voice: "restart", "ask it"). None: the offer has gone."""
        session = self.sessions.get(session_id)
        return self._accept(session, what, ref, accept) if session is not None else None

    def _accept(self, session: Session, what: str, ref: str, accept: bool) -> TurnOutcome | None:
        """An offer answered in words, typed or spoken: the same paths as its buttons, and the screen is told."""
        try:
            if what == "amendment":
                answer = self.answer_amendment(session.id, ref, accept)
                reply = "Restarting with your change." if accept else LEAVE
            else:
                answer = self.answer_queue(session.id, ref, accept)
                reply = "Running it now." if accept else "Dropped."
        except ConversationError:
            return None  # the offer has closed: the turn is taken as itself
        kind: TurnKind = "amendment" if what == "amendment" else "new_question"
        outcome = self._reply(session, Classified(kind=kind, by="rules"), reply, answer.get("run_id"))
        return outcome.model_copy(
            update={"started_run": accept, "answered": {"what": what, "id": ref, "accept": accept}}
        )

    def _unclear_number(self, session: Session, running: RunContext | None, text: str) -> TurnOutcome | None:
        """Founder re-test R3: "2%" where the decision counts people, or "two" with no unit, is asked about before
        it changes anything ("Did you mean two people?")."""
        run = running or (self.orchestrator.runs.get(session.run_id) if session.run_id else None)
        frame = run.plan.frame if run is not None and run.plan is not None else None
        if run is None or frame is None:
            return None
        counts, percents = units_of(frame.type)
        reading = count_reading(text, counts=counts, percents=percents)
        if reading is None:
            return None
        question, meant = reading
        session.asked = Asked(kind="number", text=meant)
        return self._reply(session, Classified(kind="confirm", by="rules"), question, run.run_id)

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
        why = self._why_reply(session, text)
        if why:
            return self._reply(session, Classified(kind="answerable_now", by="rules"), why, session.run_id)
        text = self._in_context(text)
        kind = by_rules(text)
        # A decision is still open on screen: a follow-up ("also…", "make it…", "what if…") changes that decision,
        # once the founder says yes (founder re-test 40). Plain figures in reply to the lane's question re-run at once.
        if kind == "amendment" and last is not None and self._is_decision(last.run_id):
            return self._offer_amendment(session, Classified(kind=kind, by="rules"), last, text)
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
                started_run=True,
            )
        rules = Classified(kind="answerable_now", by="rules")
        if is_greeting(text):
            # Founder re-test U4: "Hello? Yes?" got the earlier answer's text back. A greeting gets a greeting.
            return self._reply(session, rules, GREETING, session.run_id)
        if kind == "backchannel" or is_filler(text):
            return self._reply(session, Classified(kind="backchannel", by="rules"), "", session.run_id)
        if kind == "stop":
            return self._reply(session, Classified(kind=kind, by="rules"), "Nothing is running.", session.run_id)
        if not (clear_request(text) or single_metric(text)):
            # Founder rule U0: an unclear, very short or unrecognised turn never starts a team. It is read back,
            # and only a yes runs it.
            if extract_figures(text):
                return self._reply(session, rules, UNCLEAR, session.run_id)
            session.asked = Asked(kind="said", text=text)
            asking = f"Did you say: {text.strip().rstrip('.!? ')}? Say yes to look into it, or say it again."
            return self._reply(session, Classified(kind="confirm", by="rules"), asking, session.run_id)
        run = self._start_run(session, text)
        return TurnOutcome(session_id=session.id, reply="", run_id=run.run_id, started_run=True)

    # --- follow-ups in context (founder decision D) ----------------------------------------------------------------
    @staticmethod
    def _in_context(text: str) -> str:
        """ "And what about churn?" names a metric by reference: it becomes the plain question, so the same checked
        routine answers it. Anything else is left as the founder said it; the Advisor gets the earlier turns."""
        match = _WHAT_ABOUT.match(text.strip())
        if match is None:
            return text
        plain = f"What is our {match['rest'].strip()}?"
        return plain if single_metric(plain) else text

    def _open_decision(self, session: Session) -> RunContext | None:
        """The last decision this session got an answer to, even if a metric was looked up since: what "that
        option" and "the Devil's Advocate" refer to."""
        run = self.orchestrator.runs.get(session.decision_run_id) if session.decision_run_id else None
        if run is None or run.result is None or run.result.decision_frame is None:
            return None
        return run

    def _why_reply(self, session: Session, text: str) -> str:
        """Why the proposed option, from the open decision's own frame. Code's words, and no figure: the lane states
        none (the costs are on the card)."""
        run = self._open_decision(session)
        if run is None or run.result is None or not _WHY_OPTION.match(text.strip()):
            return ""
        frame = run.result.decision_frame
        if frame is None or not frame.options:
            return ""
        proposed = next((o for o in frame.options if o.name == frame.default_option), frame.options[0])
        full = next((o for o in frame.options if o.is_full and o.name != proposed.name), None)
        away = next((g.goal for g in frame.goals if g.status == "moves_away"), "")
        # An option's name may carry a figure ("Change prices by +10 %"): then it is named by its role.
        name = "that option" if extract_figures(proposed.name) else proposed.name
        reason = "it is the smallest step that tests the decision"
        if full is not None:
            other = "the full option" if extract_figures(full.name) else full.name
            both = proposed.modelled and full.modelled
            cheaper = both and (proposed.monthly, proposed.one_off) != (full.monthly, full.one_off)
            cheaper = cheaper and proposed.monthly <= full.monthly and proposed.one_off <= full.one_off
            if away and not extract_figures(away):
                reason = f'{other} moves you away from your goal "{away}"'
            elif away:
                reason = f"{other} moves you away from one of your goals"
            elif cheaper:
                reason = f"it costs less than {other} and is easier to undo"
            else:
                reason = f"it is easier to undo than {other}"
        # `trade_off` is what the proposal gives up: said as that, never as a reason for it.
        gives_up = proposed.trade_off.strip().rstrip(".")
        trade_off = f" The trade-off: {gives_up}." if gives_up and not extract_figures(gives_up) else ""
        return f"I proposed {name} because {reason}.{trade_off} The costs of each option are on screen."

    # --- re-run one agent (founder decision E) ---------------------------------------------------------------------
    def _rerun(self, session: Session, text: str) -> TurnOutcome | None:
        """ "Re-run the analyst, assume three hires": the existing re-run path while that agent works, the amendment
        path once its findings have moved on, and a fresh run of the same team after the answer. None: not a re-run
        request, or it names no agent (then it is an ordinary turn)."""
        match = _RERUN.match(text.strip())
        if match is None:
            return None
        said = match["rest"].strip().replace("\u2019", "'")
        found = next(
            (
                (kind, alias)
                for kind, names in AGENT_ALIASES.items()
                for alias in names
                if re.match(rf"{re.escape(alias)}\b", said, re.I)
            ),
            None,
        )
        if found is None:
            fuzzy = fuzzy_agent(said)
            by_ = Classified(kind="confirm", by="rules")
            if fuzzy is None:
                return None  # "Redo the forecast": no agent named, an ordinary turn (rule U0 still applies)
            kind, alias, used, sure = fuzzy
            rest = " ".join(said.split()[used:])
            if not sure:
                session.asked = Asked(kind="number", text=f"Re-run the {alias} {rest}".strip())
                return self._reply(session, by_, f"Did you mean re-run the {REGISTRY[kind].title}?", session.run_id)
            said = f"{alias} {rest}".strip()
            found = (kind, alias)
        kind, alias = found
        change = re.sub(r"^(?:\s*again)?[\s,;:.!]*(?:and\s+|but\s+)?", "", said[len(alias) :]).strip().rstrip(".! ")
        by = Classified(kind="amendment", by="rules")
        run = self._running(session) or (self.orchestrator.runs.get(session.run_id) if session.run_id else None)
        if run is None or run.plan is None:
            return self._reply(session, by, "There is no team to re-run yet. Ask me something first.", session.run_id)
        title = REGISTRY[kind].title
        inst = next((i for i in run.plan.team if i.type == kind), None)
        decision = self._open_decision(session)
        switched = False
        if inst is None and not self._active(session):
            # A metric was looked up since, or a Librarian-only question (founder W5): "re-run the Analyst" still
            # means the most recent decision team that had one, and the reply says which question.
            earlier = self._team_with(session, kind, decision)
            if earlier is not None and earlier.plan is not None:
                run, switched = earlier, True
                inst = next((i for i in earlier.plan.team if i.type == kind), None)
        if inst is None or run.plan is None:
            return self._reply(session, by, f"The {title} is not on this team.", run.run_id)
        brief = f"{inst.brief}\nThe founder then added: {change}" if change else inst.brief
        if run.task is not None and not run.task.done():
            outcome = self.orchestrator.rerun_agent(run.run_id, inst.id, brief)
            if outcome is not None and outcome.restarted:
                how = "with your change" if change else "from the start"
                return self._reply(session, by, f"Re-running the {inst.name} {how}.", run.run_id)
            if change:  # its findings have gone to the next stage: only a restart of the run can take the change
                return self._offer_amendment(session, by, run, change)
            reply = f"The {inst.name} has handed its findings on. I can redo it when this run finishes."
            return self._reply(session, by, reply, run.run_id)
        # After the answer (founder re-test R8): only this agent runs again. The rest of the team's findings are kept
        # as they were, and the Advisor writes the answer again from all of them.
        frame = run.plan.frame
        changes_inputs = bool(change) and (
            bool(parse_inputs(change, frame.type if frame is not None else "")) or self._gives_inputs(run, change)
        )
        if changes_inputs:
            # "Assume three hires" changes the decision itself: every agent's findings rest on the old cost model,
            # so the whole team runs again with the change, as for any amendment.
            plan = self._same_decision(run.run_id) or run.plan
            team = [i.model_copy(update={"brief": brief}) if i.type == kind else i for i in plan.team]
            new = self._start_run(
                session,
                f"{run.message}\nThe founder then added: {change}",
                amendment_of=run.run_id,
                plan_override=plan.model_copy(update={"team": team}),
            )
            reply = f"That changes the decision, so the whole team runs again with it, the {inst.name} included."
            return self._reply(session, by, reply, new.run_id).model_copy(update={"started_run": True})
        earlier = {r.agent_id: r for r in (run.result.agents if run.result is not None else [])}
        team, reuse = [], {}
        for old in run.plan.team:
            fresh = old.model_copy(update={"id": f"agt_{uuid.uuid4().hex[:8]}"})
            if old.id == inst.id:
                fresh = fresh.model_copy(update={"brief": brief})
            elif old.id in earlier and earlier[old.id].status == "done":
                reuse[fresh.id] = earlier[old.id]
            team.append(fresh)
        new = self._start_run(
            session,
            run.message,
            amendment_of=run.run_id,
            plan_override=run.plan.model_copy(update={"team": team}),
            reuse=reuse,
        )
        how = "with your change" if change else "again"
        if switched:
            place = _place(run.message)
            on = f"on the {place} question" if place else f'on "{_topic(run.message)}"'
            how = f"{on} with your change" if change else on
        reply = f"Re-running only the {inst.name} {how}. The rest of the team's findings stand."
        return self._reply(session, by, reply, new.run_id).model_copy(update={"started_run": True})

    def _team_with(self, session: Session, kind: str, decision: RunContext | None) -> RunContext | None:
        """The most recent finished decision run of this session whose team had an agent of `kind`."""
        if decision is not None and decision.plan is not None and any(i.type == kind for i in decision.plan.team):
            return decision
        for run in reversed(list(self.orchestrator.runs.values())):
            ctx = run.context
            if ctx is None or getattr(ctx, "session_id", None) != session.id or run.plan is None:
                continue
            done = run.result is not None and run.result.status == "done"
            if done and self._is_decision(run.run_id) and any(i.type == kind for i in run.plan.team):
                return run
        return None

    def _reply(self, session: Session, classified: Classified, reply: str, run_id: str | None) -> TurnOutcome:
        if reply:
            session.local.add("lane", reply)
        return TurnOutcome(
            session_id=session.id, kind=classified.kind, classified_by=classified.by, reply=reply, run_id=run_id
        )

    @staticmethod
    def _already_in(running: RunContext, text: str) -> str:
        """M6a carry-over (founder, M5 gate): "Assume two hires." when the answer already rests on two local hires is
        not a change, so no restart is offered. Every number the founder gave must equal the base case of the frame
        this run used; the reply names counts in words and other figures by name only (the lane states no figure)."""
        frame = running.result.decision_frame if running.result is not None else None
        if frame is None and running.plan is not None:
            frame = running.plan.frame
        if frame is None or frame.cost_model is None:
            return ""
        given = parse_inputs(text, frame.type)
        items = {i.key: i for i in frame.cost_model.items}
        if not given or any(k not in items or abs(items[k].base - v) > 1e-9 for k, v in given.items()):
            return ""
        words = {v: k for k, v in _COUNT_NAMES.items()}
        parts = []
        for key, value in given.items():
            item = items[key]
            if item.cadence == "count" and float(value).is_integer() and int(value) in words:
                parts.append(f"{words[int(value)]} {item.name.lower()}")
            else:
                parts.append(f"that {item.name.lower()}")
        what = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
        if running.task is not None and not running.task.done():
            return f"The team is already assuming {what}. Nothing to restart."
        return f"That's already in this answer: it assumes {what}. Nothing to restart."

    def _offer_amendment(self, session: Session, classified: Classified, running: RunContext, text: str) -> TurnOutcome:
        same_as_answer = self._already_in(running, text)
        if same_as_answer:
            return self._reply(session, classified, same_as_answer, running.run_id)
        # A run whose team is still being chosen has no plan yet: only a run known not to be a decision is a
        # "request".
        known_other = running.plan is not None and not self._is_decision(running.run_id)
        reply = RESTART_REQUEST if known_other else RESTART_OFFER
        if running.task is not None and running.task.done():
            # Founder RL2 (2026-11-16): the answer is already out, so the change is not in it. Said once:
            # "Your change to three hires isn't in this answer yet. Say yes to restart with it."
            reply = change_reminder(text)
        # Founder re-test T3: one change, one offer, one card. The same change said again (the founder repeating
        # it, or the recogniser hearing it twice) is the offer already open, not a second one.
        same = next(
            (
                a
                for a in session.amendments.values()
                if a.status == "offered" and a.run_id == running.run_id and _same(a.text, text)
            ),
            None,
        )
        if same is not None:
            session.asked = Asked(kind="amendment", ref=same.id)
            return self._reply(session, classified, reply, running.run_id).model_copy(update={"amendment_id": same.id})
        amendment = Amendment(
            id=f"amd_{uuid.uuid4().hex[:8]}",
            run_id=running.run_id,
            text=text,
            edited_message=f"{running.message}\nThe founder then added: {text}",
        )
        session.amendments[amendment.id] = amendment
        session.asked = Asked(kind="amendment", ref=amendment.id)  # "yes" answers it, as the card's button does
        # Founder re-test S4: the same offer, in the same words, while the team works as after the answer.
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
        return {"accepted": True, "run_id": self._start_run(session, self._in_context(item.text)).run_id}
