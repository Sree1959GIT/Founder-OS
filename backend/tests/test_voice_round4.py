"""M5 founder re-test, round 3 (2026-11-14): S1 to S5, and the open questions the founder answered.

S1 a run the founder stopped is never summarised or spoken; S2 each offer is said once; S3 after an offer the voice
waits (its own echo and an unclear sound are never a yes); S4 a change said while the team works is offered in the
same words as after the answer, and is not lost if it goes unanswered; S5 the same goal and the same memo are told
once, and a memo is never given a date it does not have. A typed "stop" stops at once; a spoken one is asked about.

WAV fixtures in, fake STT and TTS, no GPU, microphone or network.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.dedupe import near_duplicate, same_goal, without_repeats
from app.agents.runtime import _SentenceGate, asks_about_a_draft, misdates_a_record
from app.conversation.classifier import TurnClassifier
from app.conversation.manager import CHANGE_STILL_OPEN, RESTART_OFFER, STOP_QUESTION
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.vault.decisions import DecisionRecord
from tests.test_specialists import slow_provider
from tests.test_voice import make, stream, wav_bytes
from tests.test_voice_round2 import DUBAI, finished, lane, wait_for

TEAM_QUESTION = "Should we expand the team this year?"
GOAL = "Extend runway past 12 months without new financing"
# The founder's Dubai answer of 2026-11-14, as code and the model wrote it.
LEAD_FULL_MODEL = (
    "The full model, Full office, is $30,000.00 up front and $32,347.24 a month, moving projected runway from 11.23 "
    f'to 9.16 months (-2.07), which moves you away from your goal "{GOAL}"; all of these are assumptions to confirm.'
)
GOAL_AGAIN = (
    f'This moves you away from your goal "{GOAL}": runway is 10.65 months today, and the base case changes '
    "projected runway by -2.07 months."
)
LEAD_MEMO = (
    "You already have a proposed memo on this from 2026-11-06 [decisions/2026-11-06-dubai-office.md]: what has "
    "changed since you drafted it?"
)
MEMO_AGAIN = "You already proposed a Dubai office in 2027 with a Travel-led pilot."
DUBAI_MEMO = DecisionRecord(
    path="decisions/2026-11-06-dubai-office.md",
    title="Dubai office",
    status="proposed",
    review_date="2026-12-06",
    predictions=["Runway stays above 10.44 months by 2027-05-06"],
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


async def summarised(session: Any, wire: Any, manager: Any, question: str = DUBAI) -> str:
    """Asks by typing, and waits until the spoken summary has ended on its offer. Returns the run's id."""
    await session.control({"type": "text", "text": question})
    await wait_for(lambda: bool(wire.of("turn")))
    run_id = wire.of("turn")[0]["outcome"]["run_id"]
    await finished(manager, run_id)
    await wait_for(lambda: any(t.startswith("Want") for t in said(wire)))
    await asyncio.sleep(0.2)
    return str(run_id)


# --- S1: a stopped run is never summarised or spoken ------------------------------------------------------------------
async def test_a_stop_that_lands_too_late_to_interrupt_still_cancels_the_run(finance: Any) -> None:
    """The graph returned a full state although the founder had stopped the run: it is cancelled all the same."""
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    run = manager.orchestrator.runs[first.run_id or ""]
    run.cancel_requested = True  # as `cancel()` sets it; here the task itself is left to finish its work
    with pytest.raises(asyncio.CancelledError):
        await run.task  # type: ignore[misc]
    await asyncio.sleep(0.05)
    assert run.result is None
    ended = [e for e in manager.bus.history(run.run_id) if e.type == "run.finished"]
    assert [e.data["status"] for e in ended] == ["cancelled"]
    assert manager.sessions[first.session_id].narration[-1] == "That run was cancelled."


async def test_stop_and_yes_by_voice_and_the_summary_is_never_spoken(finance: Any) -> None:
    """The founder's case: "stop", "yes", "Stopping the team.", and then the summary was spoken anyway. Here the
    cancel is made to miss on purpose (the run finishes "done"): the voice still says nothing of its answer."""
    session, wire, _, _tts, manager = make(
        finance, ["Stop.", "Yes."], mode="duplex", approval_policy="never", still_working_s=0
    )
    orchestrator = manager.orchestrator
    orchestrator.cancel = lambda run_id: True  # type: ignore[method-assign]
    hold = asyncio.Event()
    advise = orchestrator.graph.ainvoke

    async def held(*args: Any, **kwargs: Any) -> Any:
        state = await advise(*args, **kwargs)
        await hold.wait()  # the team has its answer, but the run has not ended yet
        return state

    orchestrator.graph.ainvoke = held  # type: ignore[method-assign]
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run = orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    await wait_for(lambda: any(t.startswith("I've put together") for t in said(wire)))
    await asyncio.sleep(0.2)
    session.speaking_until = 0.0
    await stream(session, wav_bytes("okay"))  # heard as "Stop."
    await wait_for(lambda: STOP_QUESTION in said(wire))
    await asyncio.sleep(0.2)
    session.speaking_until = 0.0
    await stream(session, wav_bytes("okay"))  # heard as "Yes."
    await wait_for(lambda: "Stopping the team." in said(wire))
    hold.set()
    result = await run.task  # type: ignore[misc]
    assert result.status == "done" and "Proposed: " in result.answer  # the cancel missed: there is an answer
    await asyncio.sleep(0.5)
    assert not said(wire, "answer")
    assert not any(t.startswith(("My proposal is", "The full office", "Want ")) for t in said(wire))
    assert session.offers.more == []
    await session.close()


async def test_a_cancelled_run_takes_its_waiting_lines_with_it(finance: Any) -> None:
    """The summary was already waiting to be said when the run was reported cancelled (the Cancel button, or a stop
    typed in another window): none of it is said."""
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run_id = wire.of("turn")[0]["outcome"]["run_id"]
    session._floor.clear()  # the founder is speaking: nothing is played yet
    await finished(manager, run_id)
    await session._answers_idle.wait()
    waiting = [s for s in session._says._queue if s.lane == "answer"]  # type: ignore[attr-defined]
    assert any(s.text.startswith("My proposal is") for s in waiting)
    manager.bus.emit("recap", run_id, session_id=session.session_id, text="That run was cancelled.", status="cancelled")
    await wait_for(lambda: run_id in session._stopped)
    session._floor.set()
    await wait_for(lambda: "That run was cancelled." in said(wire))
    await asyncio.sleep(0.3)
    assert not said(wire, "answer")
    await session.close()


# --- typed "stop" stops at once; spoken "stop" is asked about (founder decision 2026-11-14) --------------------------
async def test_a_typed_stop_stops_at_once_and_a_spoken_one_is_asked_about(finance: Any) -> None:
    provider = slow_provider()
    manager = lane(finance, provider)
    first = await manager.turn(None, TEAM_QUESTION)
    run = manager.orchestrator.runs[first.run_id or ""]
    asked = await manager.turn(first.session_id, "Stop.", spoken=True)
    assert (asked.kind, asked.reply) == ("confirm", STOP_QUESTION) and not run.task.done()  # type: ignore[union-attr]
    await manager.turn(first.session_id, "No.", spoken=True)
    typed = await manager.turn(first.session_id, "stop")
    assert (typed.kind, typed.reply) == ("stop", "Stopping the team.")
    with pytest.raises(asyncio.CancelledError):
        await run.task  # type: ignore[misc]
    provider.release.set()


async def test_stop_typed_into_the_panel_while_the_voice_is_on_stops_at_once(finance: Any) -> None:
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance, [], provider=provider, mode="duplex", approval_policy="never", still_working_s=0
    )
    await session.start()
    await session.control({"type": "text", "text": TEAM_QUESTION})
    await wait_for(lambda: bool(wire.of("turn")))
    run = manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    await session.control({"type": "text", "text": "stop"})
    await wait_for(lambda: run.task.done())  # type: ignore[union-attr]
    await wait_for(lambda: "That run was cancelled." in said(wire))
    assert "Stopping the team." in said(wire) and STOP_QUESTION not in said(wire)
    provider.release.set()
    await session.close()


# --- S2: each offer is said once --------------------------------------------------------------------------------------
async def test_an_offer_is_said_once_whatever_noises_follow_it(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await summarised(session, wire, manager)
    offer = session.offers.more[0].offer
    for noise in ("Uh-huh.", "Mm.", "Right."):
        await session.control({"type": "text", "text": noise})
        await wait_for(lambda: session.metrics.turns[-1].turn_ms is not None and session.metrics.turns[-1].kind != "")
        await asyncio.sleep(0.2)
    assert said(wire).count(offer) == 1
    await session.close()


async def test_an_offer_that_a_barge_in_dropped_is_still_said_once(finance: Any) -> None:
    """Founder re-test R5 stands: a turn never ends without its offer. The offer was dropped before it was said, so
    a listening noise brings it back; a second noise does not bring it back again."""
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    session._floor.clear()  # the founder is speaking: the summary waits
    await finished(manager, wire.of("turn")[0]["outcome"]["run_id"])
    await session._answers_idle.wait()
    await session._interrupt("barge-in")  # what was still to be said is dropped, the offer with it
    session._floor.set()
    offer = session.offers.more[0].offer
    assert offer not in said(wire)
    await session.control({"type": "text", "text": "Uh-huh."})
    await wait_for(lambda: offer in said(wire))
    await session.control({"type": "text", "text": "Mm."})
    await asyncio.sleep(0.4)
    assert said(wire).count(offer) == 1
    await session.close()


async def test_going_through_one_part_offers_the_next_once(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await summarised(session, wire, manager)
    session.offers.more.append(type(session.offers.more[0])("detail", "Want me to go through the costs?", ["x."]))
    await session.control({"type": "text", "text": "yes"})
    await wait_for(lambda: "Want me to go through the costs?" in said(wire))
    await session.control({"type": "text", "text": "Hmm."})
    await asyncio.sleep(0.4)
    assert said(wire).count("Want me to go through the costs?") == 1
    await session.close()


# --- S3: after an offer the voice waits -------------------------------------------------------------------------------
async def test_silence_after_the_offer_says_nothing_more(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], mode="duplex", approval_policy="never")
    await session.start()
    await summarised(session, wire, manager)
    before = len(wire.of("say"))
    await stream(session, bytes(16_000 * 2 * 2))  # two seconds of silence from the microphone
    await asyncio.sleep(0.5)
    assert len(wire.of("say")) == before and len(wire.of("turn")) == 1
    await session.close()


@pytest.mark.parametrize("still_playing", [True, False])
async def test_its_own_offer_heard_back_is_not_a_yes(finance: Any, still_playing: bool) -> None:
    """ "…the other options?" from the loudspeaker reads as a yes to its own offer. It is its echo: not a turn."""
    session, wire, _, _tts, manager = make(
        finance, ["the other options?"], mode="duplex", approval_policy="never", barge_in_ms=5000
    )
    await session.start()
    await summarised(session, wire, manager)
    before = len(wire.of("say"))
    now = session.clock()
    session.speaking_until = now + 30 if still_playing else 0.0
    session._audio_end = now + 30 if still_playing else now  # the offer is playing, or ended this instant
    await stream(session, wav_bytes("okay"))
    await wait_for(lambda: bool(wire.of("echo")))
    await asyncio.sleep(0.3)
    assert len(wire.of("turn")) == 1 and len(wire.of("say")) == before  # no turn, and nothing more said
    assert bool(wire.of("resume")) is still_playing and not wire.of("interrupt")
    assert session.offers.more  # the offer still stands for the founder's own answer
    await session.close()


async def test_the_founders_own_answer_after_the_offer_is_taken(finance: Any) -> None:
    """The same words, said by the founder once the voice has been quiet for a while: an answer."""
    session, wire, _, _tts, manager = make(
        finance, ["The other options.", "Yes."], mode="duplex", approval_policy="never"
    )
    await session.start()
    await summarised(session, wire, manager)
    session.speaking_until, session._audio_end = 0.0, session.clock() - 5
    await stream(session, wav_bytes("okay"))
    await wait_for(lambda: any(t.startswith("The other options: ") for t in said(wire)))
    assert not wire.of("echo")
    await session.close()


async def test_a_plain_yes_over_the_end_of_the_offer_is_an_answer_not_an_echo(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, ["Yes."], mode="duplex", approval_policy="never")
    await session.start()
    await summarised(session, wire, manager)
    session.speaking_until = session._audio_end = session.clock() + 30
    await stream(session, wav_bytes("okay"))
    await wait_for(lambda: any(t.startswith("The other options: ") for t in said(wire)))
    await session.close()


async def test_a_sound_the_recogniser_is_unsure_of_is_not_a_yes(finance: Any) -> None:
    """A breath that comes out as "Okay." with low confidence does not start the next part."""
    session, wire, stt, _tts, manager = make(
        finance, ["Okay.", "Okay."], mode="duplex", approval_policy="never", confirm_below=0.45
    )
    stt.confidences = [0.2, 0.9]
    await session.start()
    await summarised(session, wire, manager)
    before = len(wire.of("say"))
    session.speaking_until, session._audio_end = 0.0, session.clock() - 5
    await stream(session, wav_bytes("okay"))
    await wait_for(lambda: bool(wire.of("missed")))
    await asyncio.sleep(0.3)
    assert len(wire.of("say")) == before and len(wire.of("turn")) == 1
    await stream(session, wav_bytes("okay"))  # said clearly this time
    await wait_for(lambda: any(t.startswith("The other options: ") for t in said(wire)))
    await session.close()


# --- S4: a change said while the team works ---------------------------------------------------------------------------
async def test_a_change_typed_while_the_team_works_is_offered_as_after_the_answer(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    offered = await manager.turn(first.session_id, "Assume three hires.")
    assert manager.state(first.session_id)["running"] is True  # type: ignore[index]
    assert (offered.kind, offered.reply) == ("amendment", RESTART_OFFER) and offered.amendment_id
    shown = [e for e in manager.bus.history() if e.type == "amendment.offered"]
    assert [e.data["amendment_id"] for e in shown] == [offered.amendment_id]  # the card on screen
    restarted = await manager.turn(first.session_id, "yes")
    assert restarted.reply == "Restarting with your change." and restarted.started_run
    new = await finished(manager, restarted.run_id)
    assert "three local hires, as you asked" in new.answer and "$43,770.86" in new.answer


@pytest.mark.parametrize("heard", ["Assume three hires.", "Assume 3 hires.", "assume three hires"])
@pytest.mark.parametrize("over_the_voice", [False, True])
async def test_a_change_spoken_while_the_team_works_is_shown_and_said(
    finance: Any, heard: str, over_the_voice: bool
) -> None:
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance, [heard], provider=provider, mode="duplex", approval_policy="never", still_working_s=0
    )
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run = manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    await wait_for(lambda: any(t.startswith("I've put together") for t in said(wire)))
    await asyncio.sleep(0.2)
    session.speaking_until = session.clock() + 30 if over_the_voice else 0.0
    await stream(session, wav_bytes("dubai"))
    await wait_for(lambda: len(wire.of("turn")) == 2)
    outcome = wire.of("turn")[1]["outcome"]
    assert outcome["kind"] == "amendment" and outcome["amendment_id"] and outcome["reply"] == RESTART_OFFER
    await wait_for(lambda: RESTART_OFFER in said(wire))
    assert any(e.type == "amendment.offered" for e in manager.bus.history())
    assert not run.task.done()  # type: ignore[union-attr]
    provider.release.set()
    await finished(manager, run.run_id)
    await session.close()


async def test_a_short_change_over_the_voice_is_not_left_to_a_model(finance: Any) -> None:
    """Two words said over the opening turn went to the decision model, which may call them a listening noise: then
    the speech resumed and the change was lost. The lane's own rules know a change: no model is asked."""
    noise = DecisionService(FakeDecisionProvider(rules=lambda state, question, options: ("yes", 0.99)))
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance,
        ["Assume three."],
        provider=provider,
        decisions=noise,
        mode="duplex",
        approval_policy="never",
        still_working_s=0,
        barge_in_ms=5000,
    )
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run = manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    session.speaking_until = session.clock() + 30
    await stream(session, wav_bytes("okay"))
    await wait_for(lambda: len(wire.of("turn")) == 2)
    assert session.metrics.barge_ins[-1].by == "rules" and not wire.of("resume")
    provider.release.set()
    await finished(manager, run.run_id)
    await session.close()


async def test_words_said_while_the_team_works_are_never_dropped_on_a_models_guess() -> None:
    says_noise = DecisionService(FakeDecisionProvider(rules=lambda state, question, options: ("backchannel", 0.99)))
    classifier = TurnClassifier(says_noise)
    assert (await classifier.classify("Three hires for the office", DUBAI)).kind == "new_question"
    assert (await classifier.classify("Oh god", DUBAI)).kind == "backchannel"


async def test_a_change_left_unanswered_is_asked_again_when_the_answer_is_ready(finance: Any) -> None:
    """The founder's case: the answer came with two hires and the change was gone. Now its offer stays open."""
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    offered = await manager.turn(first.session_id, "Assume three hires.")
    old = await finished(manager, first.run_id)
    assert "$32,347.24" in old.answer  # this answer does not have the change
    state = manager.state(first.session_id)
    assert state is not None and [a["status"] for a in state["amendments"]] == ["offered"]
    assert state["narration"][-1] == CHANGE_STILL_OPEN
    restarted = await manager.turn(first.session_id, "yes")
    assert restarted.answered == {"what": "amendment", "id": offered.amendment_id, "accept": True}
    new = await finished(manager, restarted.run_id)
    assert "$43,770.86" in new.answer


async def test_the_voice_ends_the_summary_on_the_unanswered_change(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    first_run = wire.of("turn")[0]["outcome"]["run_id"]
    await session.control({"type": "text", "text": "Assume three hires."})
    await wait_for(lambda: len(wire.of("turn")) == 2)
    assert wire.of("turn")[1]["outcome"]["reply"] == RESTART_OFFER
    await finished(manager, first_run)
    await wait_for(lambda: CHANGE_STILL_OPEN in said(wire))
    await asyncio.sleep(0.3)
    assert said(wire)[-1] == CHANGE_STILL_OPEN and not any(t.startswith("Want") for t in said(wire))
    await session.control({"type": "text", "text": "yes"})
    await wait_for(lambda: "Restarting with your change." in said(wire))
    restarted = wire.of("turn")[-1]["outcome"]
    new = await finished(manager, restarted["run_id"])
    assert "$43,770.86" in new.answer
    await session.close()


# --- S5: the same goal and the same memo are told once; a memo keeps its own date -------------------------------------
def test_the_goal_line_is_told_once_whatever_figures_the_second_telling_has() -> None:
    assert same_goal(GOAL_AGAIN, LEAD_FULL_MODEL, [GOAL]) and near_duplicate(GOAL_AGAIN, LEAD_FULL_MODEL, [GOAL])
    answer = f"Proposed: Travel-led pilot, $3,000.00 a month, runway -0.21 months. {LEAD_FULL_MODEL} {GOAL_AGAIN}"
    once = without_repeats(answer, [GOAL])
    assert once.count("moves you away from your goal") == 1 and "which moves you away" in once
    # A sentence that only names the goal does not hide the one that says which way the decision moves it.
    named = f'Your goal is "{GOAL}".'
    assert not same_goal(GOAL_AGAIN, named, [GOAL])
    assert "This moves you away" in without_repeats(f"{named} {GOAL_AGAIN}", [GOAL])


def test_the_dubai_answer_tells_the_goal_and_the_memo_once() -> None:
    """The founder's strings: the goal line twice, the prior memo twice, and "in 2027" for a memo of 2026-11-06."""
    gate = _SentenceGate([], DUBAI, None, [], records=[DUBAI_MEMO])
    gate.draft_on_record = True
    gate.goals = [GOAL]
    gate.shown.extend([LEAD_FULL_MODEL, LEAD_MEMO])
    prose = f"{GOAL_AGAIN} {MEMO_AGAIN} The pilot is the easier step to undo. "
    assert gate._budgeted(prose).strip() == "The pilot is the easier step to undo."
    answer = f"{LEAD_FULL_MODEL} {LEAD_MEMO} {gate._budgeted(prose)}"
    assert answer.count("moves you away from your goal") == 1
    assert answer.count("You already") == 1 and "2027" not in answer and "2026-11-06" in answer


def test_the_memo_told_again_without_the_word_memo_is_still_the_memo() -> None:
    assert asks_about_a_draft(MEMO_AGAIN)
    assert asks_about_a_draft("As you proposed earlier, a pilot comes first.")
    assert asks_about_a_draft("Your earlier proposal was a Travel-led pilot.")
    assert not asks_about_a_draft("The pilot is the easier step to undo.")


@pytest.mark.parametrize(
    "sentence",
    [
        MEMO_AGAIN,
        "You already have a proposed memo on this from 2026-11-16.",
        "Your memo from March 2027 proposed a pilot.",
        "The memo you drafted on 6 November 2025 chose the pilot.",
        "The proposed memo is up for review on 2027-01-06.",
    ],
)
def test_a_memo_is_never_given_a_date_it_does_not_have(sentence: str) -> None:
    assert misdates_a_record(sentence, [DUBAI_MEMO])
    # Whether or not a draft is on record, the sentence never reaches the founder.
    gate = _SentenceGate([], DUBAI, None, [], records=[DUBAI_MEMO])
    assert gate._budgeted(f"{sentence} The pilot is the easier step to undo. ").strip() == (
        "The pilot is the easier step to undo."
    )


@pytest.mark.parametrize(
    "sentence",
    [
        "You already have a proposed memo on this from 2026-11-06.",
        "The memo you drafted in November 2026 chose the pilot.",
        "The proposed memo is up for review on 2026-12-06.",
        "The memo forecasts runway above its target by 2027-05-06.",
        "The pilot is the easier step to undo.",
        "Dubai's free zones renew licences each year from 2027.",
    ],
)
def test_a_memos_own_dates_and_other_sentences_are_left_alone(sentence: str) -> None:
    assert not misdates_a_record(sentence, [DUBAI_MEMO])
    assert not misdates_a_record(MEMO_AGAIN, [])  # no memo on record: nothing to compare with
