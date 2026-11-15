"""M5 founder re-test, round 4 (2026-11-15): T1 to T5.

T2 "Yes?" (as Whisper wrote a spoken "yes") answers the offer just made, and so does any clear yes, whatever its case
and marks; T1 a change said while the team works is offered at once, in every stage, the last one and the writing of
the answer included; T3 one change gets one offer and one card; T4 a turn that ran no team gets no verification
line; T5 a trade-off sentence that does not name two of the options is replaced by code's.

WAV fixtures in, fake STT and TTS, no GPU, microphone or network.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.runtime import _SentenceGate, clear_trade_off, code_trade_off
from app.conversation.classifier import by_rules, is_filler, plain
from app.conversation.manager import CHANGE_STILL_OPEN, RESTART_OFFER, _ready_line
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.llm.fake import FakeProvider
from tests.test_specialists import slow_provider
from tests.test_voice import make, stream, wav_bytes
from tests.test_voice_round2 import DUBAI, finished, lane, wait_for

CHANGE = "Assume three hires."
OFFERS = (RESTART_OFFER, CHANGE_STILL_OPEN)
# The founder's sentence of 2026-11-15, as the model wrote it.
UNCLEAR_TRADE_OFF = (
    "The main trade-off is stopping hiring for the pilot while confirming the cost model with three hires."
)


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


def said(wire: Any, lane_: str | None = None) -> list[str]:
    return [m["text"] for m in wire.of("say") if lane_ is None or m["lane"] == lane_]


def cards(manager: Any) -> list[str]:
    return [e.data["amendment_id"] for e in manager.bus.history() if e.type == "amendment.offered"]


class LastAgentHeld(FakeProvider):
    """Every agent answers at once but the last one still working, which waits for `release`: the run is held in
    its last stage (the Devil's Advocate's)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.release = asyncio.Event()
        self.is_last: Any = lambda: False
        self.holding = False

    async def _complete(self, messages, tools, json_schema):  # type: ignore[no-untyped-def]
        if json_schema is None and any("Brief:" in m.content for m in messages) and self.is_last():
            self.holding = True
            await self.release.wait()
        return await super()._complete(messages, tools, json_schema)


def one_left(manager: Any, run_id: str) -> bool:
    run = manager.orchestrator.runs.get(run_id)
    if run is None or run.plan is None:
        return False
    done = {e.agent_id for e in manager.bus.history(run_id) if e.type == "agent.done"}
    return len(done) >= len(run.plan.team) - 1


async def quiet(session: Any) -> None:
    """Nothing is playing and nothing has just played: what is heard next is the founder, not an echo."""
    await asyncio.sleep(0.2)
    session.speaking_until, session._audio_end = 0.0, session.clock() - 5


# --- T2: "Yes?" answers the offer -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "heard",
    ["Yes?", "yes.", "Yeah!", "okay?", "Yep.", "Sure!", "Go ahead.", "Do it!", "Restart?", "YES", "Yes, restart."],
)
@pytest.mark.parametrize("spoken", [True, False])
async def test_a_clear_yes_after_the_offer_restarts_with_the_change(finance: Any, heard: str, spoken: bool) -> None:
    """The founder's case: the change was still open after the answer, they said "yes", Whisper wrote "Yes?", and it
    ran as a new question."""
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    offered = await manager.turn(first.session_id, CHANGE, spoken=spoken)
    await finished(manager, first.run_id)
    runs_before = len(manager.orchestrator.runs)
    assert manager.has_question(first.session_id, heard)
    answer = await manager.turn(first.session_id, heard, spoken=spoken)
    assert answer.answered == {"what": "amendment", "id": offered.amendment_id, "accept": True}
    assert answer.reply == "Restarting with your change." and answer.started_run
    assert len(manager.orchestrator.runs) == runs_before + 1
    new = manager.orchestrator.runs[answer.run_id or ""]
    assert new.message == f"{DUBAI}\nThe founder then added: {CHANGE}"  # the change, never "Yes?" as a question
    await finished(manager, answer.run_id)


async def test_yes_with_a_question_mark_gets_the_changed_figures(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await manager.turn(first.session_id, CHANGE, spoken=True)
    await finished(manager, first.run_id)
    answer = await manager.turn(first.session_id, "Yes?", spoken=True)
    new = await finished(manager, answer.run_id)
    assert "three local hires, as you asked" in new.answer and "$43,770.86" in new.answer and "-2.58" in new.answer


@pytest.mark.parametrize("heard", ["No?", "no.", "Nope!", "Keep going."])
async def test_a_clear_no_after_the_offer_leaves_the_answer_as_it_is(finance: Any, heard: str) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    offered = await manager.turn(first.session_id, CHANGE, spoken=True)
    await finished(manager, first.run_id)
    runs_before = len(manager.orchestrator.runs)
    answer = await manager.turn(first.session_id, heard, spoken=True)
    assert answer.answered == {"what": "amendment", "id": offered.amendment_id, "accept": False}
    assert len(manager.orchestrator.runs) == runs_before


async def test_a_listening_noise_before_the_yes_does_not_close_the_offer(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    offered = await manager.turn(first.session_id, CHANGE, spoken=True)
    await finished(manager, first.run_id)
    noise = await manager.turn(first.session_id, "Mm.", spoken=True)
    assert noise.kind == "backchannel" and not noise.started_run
    answer = await manager.turn(first.session_id, "Yes?", spoken=True)
    assert answer.answered == {"what": "amendment", "id": offered.amendment_id, "accept": True}
    await finished(manager, answer.run_id)


@pytest.mark.parametrize("heard", ["Yes?", "Okay?", "Yeah!", "Sure?"])
async def test_a_bare_yes_with_nothing_asked_never_runs_as_a_question(finance: Any, heard: str) -> None:
    """ "Yes?" went to the Advisor as a question of its own ("What's your reasoning for agreeing…", "Not run")."""
    assert by_rules(heard) == "backchannel" and is_filler(heard)
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    runs_before = len(manager.orchestrator.runs)
    outcome = await manager.turn(first.session_id, heard, spoken=True)
    assert outcome.kind == "backchannel" and not outcome.started_run and outcome.reply == ""
    assert len(manager.orchestrator.runs) == runs_before


def test_plain_takes_the_marks_and_case_off_an_answer() -> None:
    assert [plain(t) for t in ("Yes?", " yes. ", "Yeah!", "OKAY?", "Yes, restart.")] == [
        "yes",
        "yes",
        "yeah",
        "okay",
        "yes restart",
    ]
    # A real question keeps its meaning: it is not a filler, and the rules still see a question.
    assert not is_filler("Yes, but what about tax?") and by_rules("Is it done?") != "backchannel"


async def test_yes_heard_with_a_question_mark_restarts_by_voice(finance: Any) -> None:
    """The whole of the founder's RX4 by voice: the change while the team works, the answer, then "Yes?"."""
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance, [CHANGE, "Yes?"], provider=provider, mode="duplex", approval_policy="never", still_working_s=0
    )
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    first_run = wire.of("turn")[0]["outcome"]["run_id"]
    await wait_for(lambda: any(t.startswith("I've put together") for t in said(wire)))
    await quiet(session)
    await stream(session, wav_bytes("dubai"))  # heard as the change
    await wait_for(lambda: RESTART_OFFER in said(wire))
    provider.release.set()
    await finished(manager, first_run)
    await session._answers_idle.wait()
    await wait_for(lambda: session._says.empty() and session._current is None)
    await quiet(session)
    await stream(session, wav_bytes("okay"))  # heard as "Yes?"
    await wait_for(lambda: "Restarting with your change." in said(wire))
    restarted = wire.of("turn")[-1]["outcome"]
    assert restarted["answered"]["what"] == "amendment" and restarted["answered"]["accept"] is True
    assert not any(r.message == "Yes?" for r in manager.orchestrator.runs.values())
    new = await finished(manager, restarted["run_id"])
    assert "$43,770.86" in new.answer and "-2.58" in new.answer
    await session.close()


# --- T1: a change is offered at once, in every stage ------------------------------------------------------------------
@pytest.mark.parametrize("stage", ["first", "last", "written"])
async def test_a_change_said_in_any_stage_is_offered_at_once_and_only_once(finance: Any, stage: str) -> None:
    """The founder's case: "Assume three hires." said while the Devil's Advocate worked got no offer at that moment.
    `first`: the first agents are working. `last`: only the last agent is. `written`: the team is done and the
    answer is on its way. Each time the offer is said and shown before the run ends, and it is the only one."""
    provider: Any = slow_provider() if stage == "first" else LastAgentHeld(default=lambda m, t, s: "No numbers here.")
    session, wire, _, _tts, manager = make(
        finance, [CHANGE, "Yes?"], provider=provider, mode="duplex", approval_policy="never", still_working_s=0
    )
    orchestrator = manager.orchestrator
    hold = asyncio.Event()
    team_done = asyncio.Event()
    invoke = orchestrator.graph.ainvoke

    async def held(*args: Any, **kwargs: Any) -> Any:
        state = await invoke(*args, **kwargs)
        team_done.set()
        if stage == "written":
            await hold.wait()  # the answer is written, and the run has not ended yet
        return state

    orchestrator.graph.ainvoke = held  # type: ignore[method-assign]
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run = orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    await wait_for(lambda: any(t.startswith("I've put together") for t in said(wire)))
    if stage == "last":
        provider.is_last = lambda: one_left(manager, run.run_id)
        await wait_for(lambda: provider.holding)
    elif stage == "written":
        await team_done.wait()
    await quiet(session)
    assert not run.task.done()  # type: ignore[union-attr]
    await stream(session, wav_bytes("dubai"))  # heard as "Assume three hires."
    await wait_for(lambda: RESTART_OFFER in said(wire))
    assert not run.task.done()  # type: ignore[union-attr]  # at once: the run is still going
    assert not said(wire, "answer")  # and before any line of the answer
    assert len(cards(manager)) == 1
    offer = wire.of("turn")[1]["outcome"]
    assert (offer["kind"], offer["reply"]) == ("amendment", RESTART_OFFER)
    provider.release.set()
    hold.set()
    await finished(manager, run.run_id)
    await session._answers_idle.wait()
    await wait_for(lambda: session._says.empty() and session._current is None)
    await asyncio.sleep(0.3)
    # T3: one change, one offer, one card. No second asking with the answer, and no offer of risks beside it.
    assert [t for t in said(wire) if t in OFFERS] == [RESTART_OFFER]
    assert not any(t.startswith("Want") for t in said(wire)) and session.offers.more == []
    assert len(cards(manager)) == 1
    assert CHANGE_STILL_OPEN not in manager.sessions[session.session_id].narration
    await quiet(session)
    await stream(session, wav_bytes("okay"))  # heard as "Yes?"
    await wait_for(lambda: "Restarting with your change." in said(wire))
    new = await finished(manager, wire.of("turn")[-1]["outcome"]["run_id"])
    assert "$43,770.86" in new.answer
    await session.close()


# --- T3: one change, one offer, one card ------------------------------------------------------------------------------
async def test_the_same_change_said_twice_is_one_offer_and_one_card(finance: Any) -> None:
    manager = lane(finance, slow := slow_provider())
    first = await manager.turn(None, DUBAI)
    one = await manager.turn(first.session_id, CHANGE, spoken=True)
    two = await manager.turn(first.session_id, "assume three hires", spoken=True)
    assert one.amendment_id and two.amendment_id == one.amendment_id and two.reply == RESTART_OFFER
    assert cards(manager) == [one.amendment_id]
    state = manager.state(first.session_id)
    assert state is not None and [a["status"] for a in state["amendments"]] == ["offered"]
    other = await manager.turn(first.session_id, "Assume four hires.", spoken=True)  # another change: its own card
    assert other.amendment_id not in (None, one.amendment_id) and len(cards(manager)) == 2
    slow.release.set()
    await finished(manager, first.run_id)


async def test_the_card_carries_the_words_the_voice_says(finance: Any) -> None:
    manager = lane(finance, slow := slow_provider())
    first = await manager.turn(None, DUBAI)
    await manager.turn(first.session_id, CHANGE)
    event = next(e for e in manager.bus.history() if e.type == "amendment.offered")
    assert event.data["reply"] == RESTART_OFFER and event.data["text"] == CHANGE
    slow.release.set()
    await finished(manager, first.run_id)


async def test_a_change_whose_offer_was_never_said_aloud_is_asked_once_with_the_answer(finance: Any) -> None:
    """Typed in the chat box (not through the voice), so nothing was said: the voice asks, once, after the summary."""
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    first_run = wire.of("turn")[0]["outcome"]["run_id"]
    await manager.turn(session.session_id, CHANGE)  # the chat box's own request, not this socket
    await finished(manager, first_run)
    await wait_for(lambda: CHANGE_STILL_OPEN in said(wire))
    await asyncio.sleep(0.3)
    assert [t for t in said(wire) if t in OFFERS] == [CHANGE_STILL_OPEN]
    assert said(wire)[-1] == CHANGE_STILL_OPEN and not any(t.startswith("Want") for t in said(wire))
    assert len(cards(manager)) == 1
    await session.control({"type": "text", "text": "Yes?"})
    await wait_for(lambda: "Restarting with your change." in said(wire))
    await finished(manager, wire.of("turn")[-1]["outcome"]["run_id"])
    await session.close()


# --- T4: no verification line for a turn that ran no team -------------------------------------------------------------
def test_a_run_with_no_team_has_no_ready_line() -> None:
    assert _ready_line({"team_ran": False, "verified": False}) == ""
    assert _ready_line({"team_ran": True, "verified": False}) == "The answer is ready, but some of it is unverified."
    assert _ready_line({"verified": True}) == "The answer is ready."


async def test_a_reply_that_ran_no_team_says_nothing_about_verification(finance: Any) -> None:
    """The founder's case: a "Not run" badge together with "The answer is ready, but some of it is unverified"."""
    manager = lane(finance)
    first = await manager.turn(None, "Hello there")
    result = await finished(manager, first.run_id)
    assert result.verification.state == "not_run" and not result.agents
    ended = [e for e in manager.bus.history(first.run_id) if e.type == "run.finished"]
    assert ended[-1].data["team_ran"] is False
    lines = manager.sessions[first.session_id].narration
    assert not any("verif" in line.lower() or "answer is ready" in line.lower() for line in lines)
    assert not [e for e in manager.bus.history() if e.type == "recap"]


async def test_a_team_run_still_gets_its_ready_line(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    recaps = [e.data["text"] for e in manager.bus.history() if e.type == "recap"]
    assert len(recaps) == 1 and recaps[0].startswith("The answer is ready")


# --- T5: the trade-off names two options, or code writes it -----------------------------------------------------------
async def test_an_unclear_trade_off_is_replaced_by_codes(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    frame = (await finished(manager, first.run_id)).decision_frame
    assert frame is not None
    written = code_trade_off(frame)
    assert written.startswith("The main trade-off: with Travel-led pilot, ") and "; with Full office, " in written
    assert clear_trade_off(UNCLEAR_TRADE_OFF, frame) == written
    # One that names two of the options stays as the model wrote it, and so does a question or any other sentence.
    clear = "The main trade-off is speed against commitment: the pilot learns slowly, the full office is hard to undo."
    assert clear_trade_off(clear, frame) == clear
    assert clear_trade_off("Which trade-off worries you most?", frame) == "Which trade-off worries you most?"
    assert clear_trade_off("The pilot is the easier step to undo.", frame) == "The pilot is the easier step to undo."
    assert clear_trade_off(UNCLEAR_TRADE_OFF, None) == UNCLEAR_TRADE_OFF
    # In the answer: the unclear sentence never reaches the founder, and code's is there once.
    gate = _SentenceGate([], DUBAI, None, [], frame)
    out = gate._budgeted(f"{UNCLEAR_TRADE_OFF} The trade-off is the pilot's pace. What has changed? ")
    assert "stopping hiring" not in out and out.count("The main trade-off: with Travel-led pilot") == 1
    assert out.count("trade-off") == 1 and out.strip().endswith("What has changed?")
