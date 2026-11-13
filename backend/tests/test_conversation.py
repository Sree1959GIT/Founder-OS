"""The conversation lane: what a turn means, what the lane says, and that it never touches the running work."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.decision_frame import parse_inputs
from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.tools import ToolContext
from app.config import Settings
from app.conversation.classifier import Classified, TurnClassifier, by_rules
from app.conversation.contexts import GlobalContext, LocalContext, RunSnapshot
from app.conversation.manager import (
    MAX_SESSIONS,
    ConversationError,
    ConversationManager,
)
from app.decision.base import Decision, DecisionError, DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.main import create_app
from tests.test_specialists import _until, slow_provider

REQUEST = "Should we expand the team this year?"


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


def lane(finance: Any, *, fast: Any = None, quiet: bool = False) -> tuple[ConversationManager, Any]:
    provider = slow_provider()
    orch = AgentOrchestrator(
        LLMRouter(provider),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, None, aid),
    )
    return ConversationManager(orch, fast=fast, fast_timeout_s=0.2, quiet=quiet), provider


async def started(manager: ConversationManager) -> tuple[str, Any]:
    outcome = await manager.turn(None, REQUEST)
    run = manager.orchestrator.runs[outcome.run_id or ""]
    await _until(lambda: len(run.agent_tasks) == 2)
    return outcome.session_id, run


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


# --- classifying ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("ok thanks", "backchannel"),
        ("Got it.", "backchannel"),
        ("How long will this take?", "answerable_now"),
        ("who is working on it", "answerable_now"),
        ("Actually, assume two hires instead of three", "amendment"),
        ("Make it a 12 month plan", "amendment"),
        ("What is our churn?", "new_question"),
        ("stop", "stop"),
        ("Actually, cancel that.", "stop"),
        ("never mind", "stop"),
        ("The Dubai thing worries me", None),
        ("What is the status?", "answerable_now"),
        ("how long does this take", "answerable_now"),
        ("where are we?", "answerable_now"),
        # A review caught these: business questions and requests that sound like the work's status or a stop.
        ("How long is our runway?", "new_question"),
        ("What's the status of the Acme deal?", "new_question"),
        ("Where are we on hiring?", "new_question"),
        ("Can we make it to December?", "new_question"),
        ("Cancel the Acme contract", None),
        ("Stop hiring contractors", None),
        # Founder review 21: a change to the running request, worded as an addition, was queued as a question.
        ("also make it a two person team", "amendment"),
        ("Add a travel budget of 2000 a month", "amendment"),
        ("only two hires", "amendment"),
        ("change the rent to 3000", "amendment"),
        ("Use a partner instead", "amendment"),
        ("assume 4k rent", "amendment"),
        ("what about our churn?", "new_question"),
        ("What does adding a hire do to runway?", "new_question"),
    ],
)
def test_clear_turns_need_no_model(text: str, kind: str | None) -> None:
    assert by_rules(text) == kind


@pytest.mark.parametrize(
    "text", ["also make it a two person team", "a two-person team", "make it two people", "only 2 local hires"]
)
def test_an_amendment_changes_the_runs_inputs(text: str) -> None:
    """Accepted, the amendment re-runs with the founder's own count: local hires = 2, not the placeholder."""
    assert parse_inputs(text, "new_office") == {"hires": 2.0}


class Unsure(FakeDecisionProvider):
    def __init__(self, choice: str, probability: float) -> None:
        self.choice, self.probability = choice, probability

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        return Decision(
            question=question, options=options, choice=self.choice, probability=self.probability, provider="x"
        )


class Slow(FakeDecisionProvider):
    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        await asyncio.sleep(5)
        raise AssertionError


class Broken(FakeDecisionProvider):
    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        raise DecisionError("down")


async def test_an_unclear_turn_goes_to_the_model_and_is_queued_if_it_is_unsure_slow_or_down() -> None:
    unclear = "The Dubai thing worries me"
    sure = await TurnClassifier(DecisionService(Unsure("amendment", 0.95))).classify(unclear, REQUEST)
    assert sure.kind == "amendment" and sure.by == "decision"
    unsure = await TurnClassifier(DecisionService(Unsure("stop", 0.1), min_confidence=0.6)).classify(unclear, REQUEST)
    assert unsure.kind == "new_question"
    slow = await TurnClassifier(DecisionService(Slow()), timeout_s=0.05).classify(unclear, REQUEST)
    assert slow.kind == "new_question"
    broken = await TurnClassifier(DecisionService(Broken())).classify(unclear, REQUEST)
    assert broken.kind == "new_question"
    assert (await TurnClassifier().classify(unclear, REQUEST)).kind == "new_question"


# --- contexts ---------------------------------------------------------------------------------------------------------
def test_the_run_snapshot_is_frozen_and_the_local_window_is_bounded() -> None:
    snapshot = RunSnapshot(session_id="s", message="m", workspace=GlobalContext())
    with pytest.raises(ValidationError):
        snapshot.message = "changed"  # type: ignore[misc]
    local = LocalContext(size=2)
    for text in "abc":
        local.add("founder", text)
    assert [t.text for t in local.recent()] == ["b", "c"]


async def test_a_run_keeps_the_context_it_started_with(finance: Any) -> None:
    months = [["2026-09"]]
    provider = slow_provider()
    provider.release.set()
    orch = AgentOrchestrator(
        LLMRouter(provider),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, None, aid),
    )
    manager = ConversationManager(orch, global_context=lambda: GlobalContext(latest_month=months[0][-1]))
    outcome = await manager.turn(None, REQUEST)
    months[0] = ["2026-10"]
    assert orch.runs[outcome.run_id or ""].context.workspace.latest_month == "2026-09"
    assert manager.global_context().latest_month == "2026-10"
    await orch.runs[outcome.run_id or ""].task


# --- turns during a run -----------------------------------------------------------------------------------------------
async def test_an_idle_turn_starts_a_run_and_a_backchannel_does_not(finance: Any) -> None:
    manager, provider = lane(finance)
    assert (await manager.turn("s1", "thanks")).run_id is None
    assert (await manager.turn("s1", "stop")).reply == "Nothing is running."
    outcome = await manager.turn("s1", REQUEST)
    assert outcome.run_id is not None
    provider.release.set()
    await manager.orchestrator.runs[outcome.run_id].task


async def test_a_backchannel_gets_no_reply_and_a_status_question_is_answered_from_real_events(finance: Any) -> None:
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    assert (await manager.turn(session_id, "ok")).reply == ""
    status = await manager.turn(session_id, "How long will this take?")
    assert status.kind == "answerable_now" and "Financial Analyst" in status.reply and "Working" in status.reply
    assert not run.task.done()
    provider.release.set()
    await run.task


async def test_the_lane_never_states_a_figure_even_if_the_fast_model_does(finance: Any) -> None:
    fast = FakeProvider(default=lambda m, t, s: "Your runway is 10.65 months and $400,000.")
    manager, provider = lane(finance, fast=fast)
    session_id, run = await started(manager)
    status = await manager.turn(session_id, "What is the status?")
    assert "10.65" not in status.reply and "Working" in status.reply
    provider.release.set()
    await run.task
    await _until(lambda: not manager.sessions[session_id].narrators)
    said = " ".join(manager.sessions[session_id].narration)
    assert "10.65" not in said and "$" not in said and "While the team works" in said


async def test_the_fast_model_words_a_reply_and_a_slow_one_is_not_waited_for(finance: Any) -> None:
    fast = FakeProvider(default=lambda m, t, s: "The analyst and the librarian are on it.")
    manager, provider = lane(finance, fast=fast)
    session_id, run = await started(manager)
    assert (await manager.turn(session_id, "status?")).reply == "The analyst and the librarian are on it."

    class Hanging(FakeProvider):
        async def complete(self, *args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(5)

    manager.fast = Hanging()
    assert "Working" in (await manager.turn(session_id, "status?")).reply
    provider.release.set()
    await run.task


async def test_stop_cancels_the_run(finance: Any) -> None:
    manager, _ = lane(finance)
    session_id, run = await started(manager)
    asked = await manager.turn(session_id, "stop")
    assert asked.kind == "confirm" and asked.reply == "Stop the team? Say yes to stop."  # founder re-test R1
    assert not run.task.done()
    outcome = await manager.turn(session_id, "yes")
    assert outcome.kind == "stop" and outcome.reply == "Stopping the team."
    with pytest.raises(asyncio.CancelledError):
        await run.task
    await _until(lambda: not manager.sessions[session_id].narrators)
    assert "That run was cancelled." in manager.sessions[session_id].narration


async def test_an_amendment_is_only_offered_until_accepted_then_the_run_restarts(finance: Any) -> None:
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    offer = await manager.turn(session_id, "Actually, assume two hires")
    assert offer.kind == "amendment" and offer.amendment_id and not run.task.done()
    declined = await manager.turn(session_id, "Actually, assume three hires")
    assert manager.answer_amendment(session_id, declined.amendment_id or "", False)["accepted"] is False
    assert not run.task.done()
    accepted = manager.answer_amendment(session_id, offer.amendment_id or "", True)
    assert accepted["replaces"] == run.run_id
    with pytest.raises(asyncio.CancelledError):
        await run.task
    new_run = manager.orchestrator.runs[accepted["run_id"]]
    assert "assume two hires" in new_run.message and new_run.context.amendment_of == run.run_id
    provider.release.set()
    await new_run.task
    with pytest.raises(ConversationError):
        manager.answer_amendment(session_id, offer.amendment_id or "", True)


async def test_new_questions_wait_their_turn_first_in_first_out(finance: Any) -> None:
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    first = await manager.turn(session_id, "What is our churn?")
    second = await manager.turn(session_id, "What is our runway?")
    assert first.kind == "new_question" and first.queue_id and not run.task.done()
    with pytest.raises(ConversationError):
        manager.answer_queue(session_id, first.queue_id, True)  # not on offer yet: the run is still working
    provider.release.set()
    await run.task
    await _until(lambda: not manager.sessions[session_id].narrators)
    bus = manager.orchestrator.bus
    assert [e.data["queue_id"] for e in bus.history() if e.type == "queue.offered"] == [first.queue_id]
    with pytest.raises(ConversationError):
        manager.answer_queue(session_id, second.queue_id or "", True)  # out of order
    assert manager.answer_queue(session_id, first.queue_id, False)["accepted"] is False
    assert [e.data["queue_id"] for e in bus.history() if e.type == "queue.offered"][-1] == second.queue_id
    started_run = manager.answer_queue(session_id, second.queue_id or "", True)
    assert manager.orchestrator.runs[started_run["run_id"]].message == "What is our runway?"
    await manager.orchestrator.runs[started_run["run_id"]].task


async def test_quiet_mode_says_nothing_but_still_offers_the_queue(finance: Any) -> None:
    manager, provider = lane(finance, quiet=True)
    session_id, run = await started(manager)
    queued = await manager.turn(session_id, "What is our churn?")
    provider.release.set()
    await run.task
    await _until(lambda: not manager.sessions[session_id].narrators)
    bus = manager.orchestrator.bus
    assert not [e for e in bus.history() if e.type in ("narration", "recap")]
    assert [e.data["queue_id"] for e in bus.history() if e.type == "queue.offered"] == [queued.queue_id]


async def test_narration_follows_real_events(finance: Any) -> None:
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    provider.release.set()
    await run.task
    await _until(lambda: not manager.sessions[session_id].narrators)
    said = manager.sessions[session_id].narration
    assert said[0].startswith("Team: ") and said[-1].startswith("The answer is ready")
    assert any(line.startswith("Financial Analyst") and " done; " in line for line in said)


async def test_an_idle_turn_never_waits_for_a_model_and_old_idle_sessions_make_room(finance: Any) -> None:
    manager, provider = lane(finance)
    manager.classifier = TurnClassifier(DecisionService(Slow()), timeout_s=30)
    provider.release.set()
    outcome = await asyncio.wait_for(manager.turn("s", "The Dubai thing worries me"), timeout=2)
    await manager.orchestrator.runs[outcome.run_id or ""].task
    for i in range(MAX_SESSIONS + 5):
        manager.session(f"other{i}")
    assert len(manager.sessions) == MAX_SESSIONS


async def test_a_rejected_team_is_not_called_an_answer(finance: Any) -> None:
    manager, _ = lane(finance)
    session = manager.session("s")
    event = SimpleNamespace(data={"status": "rejected", "verified": True})
    manager._finished(session, "run_x", event)  # type: ignore[arg-type]
    assert session.narration == ["The team was not approved, so nothing ran."]


async def test_only_one_amendment_can_replace_a_run(finance: Any) -> None:
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    first = await manager.turn(session_id, "Actually, assume two hires")
    second = await manager.turn(session_id, "Actually, assume three hires")
    accepted = manager.answer_amendment(session_id, first.amendment_id or "", True)
    with pytest.raises(ConversationError):
        manager.answer_amendment(session_id, second.amendment_id or "", True)  # would orphan the new run
    assert manager.sessions[session_id].run_id == accepted["run_id"]
    with pytest.raises(asyncio.CancelledError):
        await run.task
    provider.release.set()
    await manager.orchestrator.runs[accepted["run_id"]].task


async def test_an_offer_ends_with_its_run(finance: Any) -> None:
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    offer = await manager.turn(session_id, "Actually, assume two hires")
    provider.release.set()
    await run.task
    await _until(lambda: not manager.sessions[session_id].narrators)
    with pytest.raises(ConversationError):
        manager.answer_amendment(session_id, offer.amendment_id or "", True)


async def test_a_run_ending_while_the_classifier_thinks_does_not_lose_the_turn(finance: Any) -> None:
    manager, provider = lane(finance)
    session_id, run = await started(manager)

    class EndsTheRun(TurnClassifier):
        async def classify(self, text: str, running_message: str) -> Classified:
            provider.release.set()
            await run.task
            return Classified(kind="new_question", by="default")

    manager.classifier = EndsTheRun()
    outcome = await manager.turn(session_id, "The Dubai thing worries me")
    assert outcome.run_id != run.run_id and manager.sessions[session_id].queue == []
    await manager.orchestrator.runs[outcome.run_id or ""].task


# --- API --------------------------------------------------------------------------------------------------------------
def test_the_api(client: TestClient) -> None:
    turn = client.post("/api/conversation/turn", json={"text": "What is our runway?"})
    assert turn.status_code == 200 and turn.json()["run_id"]
    session_id = turn.json()["session_id"]
    state = client.get(f"/api/conversation/{session_id}").json()
    assert state["snapshot"]["message"] == "What is our runway?" and state["session_id"] == session_id
    assert client.post(f"/api/conversation/{session_id}/quiet", json={"quiet": True}).json()["quiet"] is True
    assert client.get("/api/conversation/ses_nope").status_code == 404
    gone = client.post(f"/api/conversation/{session_id}/amendments/amd_nope", json={"accept": True})
    assert gone.status_code == 409
    assert client.post(f"/api/conversation/{session_id}/queue/que_nope", json={"accept": True}).status_code == 409
    assert client.post("/api/conversation/turn", json={"text": ""}).status_code == 422
    assert client.get(f"/api/runs/{turn.json()['run_id']}").json()["snapshot"]["session_id"] == session_id
    assert json.dumps(state)


# --- founder re-test round 2 ------------------------------------------------------------------------------------------
HIRE = "Should we hire SDRs?"


async def test_a_follow_up_after_a_decision_changes_that_decision_not_a_new_run(finance: Any) -> None:
    """40: "also make it a two person team" after the answer re-runs the same decision, same team, with the change."""
    manager, provider = lane(finance)
    provider.release.set()
    first = await manager.turn("s40", HIRE)
    run = manager.orchestrator.runs[first.run_id or ""]
    await run.task
    assert run.plan is not None and run.plan.intent == "decision"
    offer = await manager.turn("s40", "also make it a two person team")
    assert offer.kind == "amendment" and offer.amendment_id and offer.run_id == run.run_id
    assert offer.reply == "That changes the decision. Restart with your change?"
    assert len(manager.orchestrator.runs) == 1  # nothing started before the founder says yes
    accepted = manager.answer_amendment("s40", offer.amendment_id or "", True)
    new_run = manager.orchestrator.runs[accepted["run_id"]]
    await new_run.task
    assert new_run.message.startswith(HIRE) and new_run.context.amendment_of == run.run_id
    assert new_run.plan is not None and new_run.plan.intent == "decision"
    assert [i.type for i in new_run.plan.team] == [i.type for i in run.plan.team]
    assert {i.id for i in new_run.plan.team}.isdisjoint({i.id for i in run.plan.team})
    assert new_run.plan.frame is not None and new_run.plan.frame.hires == 2


async def test_a_follow_up_with_no_decision_open_is_a_new_request(finance: Any) -> None:
    manager, provider = lane(finance)
    provider.release.set()
    outcome = await manager.turn("s40b", "also, what is our churn?")
    assert outcome.amendment_id is None and outcome.run_id is not None
    await manager.orchestrator.runs[outcome.run_id].task


async def test_the_same_question_is_queued_once(finance: Any) -> None:
    """42: case, spacing and the end mark do not make it a second question."""
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    first = await manager.turn(session_id, "what is our runway?")
    again = await manager.turn(session_id, "  What is our  RUNWAY?")
    assert first.queue_id and again.queue_id == first.queue_id
    assert again.reply == "That question is already queued."
    assert len(manager.sessions[session_id].queue) == 1
    provider.release.set()
    await run.task


def test_what_if_is_a_follow_up() -> None:
    assert by_rules("what if we hired three instead?") == "amendment"


async def test_a_follow_up_to_the_dubai_answer_is_offered_not_run_at_once(finance: Any) -> None:
    """40, seen live: the Dubai frame asks for inputs, so "make it a two person team" re-ran with no offer."""
    manager, provider = lane(finance)
    provider.release.set()
    first = await manager.turn("s40d", "Should we open a Dubai office?")
    run = manager.orchestrator.runs[first.run_id or ""]
    await run.task
    offer = await manager.turn("s40d", "also make it a two person team")
    assert offer.amendment_id and offer.reply == "That changes the decision. Restart with your change?"
    accepted = manager.answer_amendment("s40d", offer.amendment_id or "", True)
    new_run = manager.orchestrator.runs[accepted["run_id"]]
    await new_run.task
    assert new_run.plan is not None and new_run.plan.frame is not None and new_run.plan.frame.cost_model is not None
    hires = next(i for i in new_run.plan.frame.cost_model.items if i.key == "hires")
    assert hires.base == 2 and hires.basis == "founder"
    assert [i.type for i in new_run.plan.team] == [i.type for i in run.plan.team]  # type: ignore[union-attr]


async def test_every_queued_question_is_offered_one_at_a_time(finance: Any) -> None:
    """56: never asked by itself; each is offered with Ask it now / Drop it, in order."""
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    first = await manager.turn(session_id, "What is our runway?")
    second = await manager.turn(session_id, "What is our churn?")
    provider.release.set()
    await run.task
    await _until(lambda: manager.sessions[session_id].queue[0].status == "offered")
    queue = manager.sessions[session_id].queue
    assert [(q.id, q.status) for q in queue] == [(first.queue_id, "offered"), (second.queue_id, "queued")]
    assert manager.answer_queue(session_id, first.queue_id or "", False) == {"accepted": False, "run_id": None}
    assert [(q.id, q.status) for q in manager.sessions[session_id].queue] == [(second.queue_id, "offered")]


async def test_a_queued_question_is_offered_when_an_older_run_ends_and_nothing_runs(finance: Any) -> None:
    """56: the session had moved on to another run, already finished: the queue is still offered."""
    manager, provider = lane(finance)
    session_id, run = await started(manager)
    queued = await manager.turn(session_id, "What is our runway?")
    session = manager.sessions[session_id]
    session.run_id = "run_other"  # a restarted run that has already ended
    provider.release.set()
    await run.task
    await _until(lambda: session.queue[0].status == "offered")
    assert session.queue[0].id == queued.queue_id
