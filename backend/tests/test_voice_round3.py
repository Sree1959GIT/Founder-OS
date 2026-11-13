"""M5 founder re-test, round 2 (2026-11-13): R1 to R8.

R1 a filler is never "stop", and stop is confirmed; R8 re-running one agent keeps the others' findings, and an accepted
change is applied and shown; R2 barge-in timings; R4 and R5 one opening turn, silence, then a summary that always ends
with an offer; R6 the recogniser's vocabulary, confidence and code's repairs; R3 an unclear number is confirmed before
it is applied; R7 a proposed memo on record gets one question only.

WAV fixtures in (`uh_huh`, `ugh`, `mm`, `hmm`, `right`, `okay`: Kokoro speech at 16 kHz), fake STT and TTS, no GPU,
microphone or network.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.agents.runtime import _SentenceGate, asks_about_a_draft
from app.conversation.classifier import TurnClassifier, by_rules, is_filler
from app.conversation.manager import STOP_QUESTION
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.voice import turn_taking
from app.voice.audio import FRAME, FrameBuffer
from app.voice.domain import HOTWORDS, PROMPT, corrected, count_reading
from app.voice.session import SAY_AGAIN, STILL_WORKING
from app.voice.spoken import summarise
from app.voice.stt import FasterWhisperSTT, confidence_of
from app.voice.vad import Endpointer, EnergyVAD
from tests.test_specialists import slow_provider
from tests.test_voice import make, stream, wav_bytes
from tests.test_voice_round2 import DUBAI, EXACT_FIGURE, finished, lane, wait_for

TEAM_QUESTION = "Should we expand the team this year?"
# What a listening noise comes out of the recogniser as. "Ugh!" is what the founder's "uh-huh" became.
FILLERS = [
    ("uh_huh", "Uh-huh."),
    ("ugh", "Ugh!"),
    ("mm", "Mm."),
    ("hmm", "Hmm."),
    ("right", "Right."),
    ("okay", "Okay."),
]
SILENCE = bytes(FRAME * 2)


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


# --- R1: a filler is a backchannel, never stop ------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "text"), FILLERS)
def test_each_filler_fixture_is_one_short_utterance_and_a_backchannel_by_rules(name: str, text: str) -> None:
    vad, endpointer, frames = EnergyVAD(), Endpointer(), FrameBuffer()
    events = [e for f in frames.push(wav_bytes(name)) if (e := endpointer.push(vad.probability(f))) is not None]
    assert [e.kind for e in events] == ["start", "end"]
    assert is_filler(text) and by_rules(text) == "backchannel"
    verdict = turn_taking.by_rules(text, 400, 1000)
    assert verdict is not None and (verdict.verdict, verdict.by) == ("backchannel", "rules")


@pytest.mark.parametrize("text", ["Ugh!", "Huh.", "Oh.", "Um...", "Uh, uh.", "Thanks.", "Dubai."])
def test_a_noise_or_one_stray_word_is_never_a_command(text: str) -> None:
    assert by_rules(text) == "backchannel"


@pytest.mark.parametrize("text", ["stop", "Stop the team.", "cancel", "Halt.", "Hold it.", "Actually, stop."])
def test_only_explicit_words_mean_stop(text: str) -> None:
    assert by_rules(text) == "stop" and not is_filler(text)


async def test_a_model_that_says_stop_cannot_stop_without_a_stop_word() -> None:
    """The founder's case: no rule matched, the decision model was asked, and it chose "stop"."""
    says_stop = DecisionService(FakeDecisionProvider(rules=lambda state, question, options: ("stop", 0.99)))
    classifier = TurnClassifier(says_stop)
    assert (await classifier.classify("Oh god", TEAM_QUESTION)).kind == "backchannel"
    assert (await classifier.classify("That is not what I had in mind at all", TEAM_QUESTION)).kind == "new_question"


@pytest.mark.parametrize(("name", "text"), FILLERS)
async def test_a_filler_spoken_while_a_team_works_changes_nothing(finance: Any, name: str, text: str) -> None:
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance, [text], provider=provider, mode="duplex", approval_policy="never", still_working_s=0
    )
    await session.start()
    await session.control({"type": "text", "text": TEAM_QUESTION})
    await wait_for(lambda: bool(wire.of("turn")))
    run = manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    await stream(session, wav_bytes(name))
    # The opening line may or may not be playing when the noise arrives (it depends on the machine's timing). Over
    # the voice, the voice resumes; in silence, the lane hears a backchannel. Either way nothing changes.
    await wait_for(lambda: len(wire.of("turn")) == 2 or bool(wire.of("resume")))
    for heard in wire.of("turn")[1:]:
        assert heard["outcome"]["kind"] == "backchannel" and heard["outcome"]["reply"] == ""
    assert not wire.of("interrupt")
    await asyncio.sleep(0.1)
    assert run.task is not None and not run.task.done()  # the team is still working
    said = [m["text"] for m in wire.of("say")]
    assert "Stopping the team." not in said and STOP_QUESTION not in said
    provider.release.set()
    await finished(manager, run.run_id)
    await session.close()


async def test_a_filler_over_the_voice_resumes_it(finance: Any) -> None:
    """ "uh-huh" heard as "Ugh!" while FounderOS speaks: its verdict comes from the rules, and the speech resumes."""
    session, wire, *_ = make(finance, ["Ugh!"], mode="duplex", barge_in_ms=3000)
    await session.start()
    session.speaking_until = session.clock() + 30
    await stream(session, wav_bytes("ugh"))
    await wait_for(lambda: bool(wire.of("resume")))
    barge = session.metrics.barge_ins[-1]
    assert (barge.verdict, barge.by, barge.text) == ("backchannel", "rules", "Ugh!")
    assert not wire.of("interrupt") and not wire.of("turn")
    await session.close()


async def test_stop_is_asked_about_and_only_yes_stops_the_team(finance: Any) -> None:
    provider = slow_provider()
    manager = lane(finance, provider)
    first = await manager.turn(None, TEAM_QUESTION)
    run = manager.orchestrator.runs[first.run_id or ""]
    asked = await manager.turn(first.session_id, "Stop the team.")
    assert (asked.kind, asked.reply) == ("confirm", "Stop the team? Say yes to stop.")
    kept = await manager.turn(first.session_id, "No, keep going.")
    assert kept.reply == "Okay, the team carries on." and not run.task.done()  # type: ignore[union-attr]
    # A question that was not answered lapses: a later "yes" stops nothing.
    await manager.turn(first.session_id, "stop")
    await manager.turn(first.session_id, "Hmm.")
    stray = await manager.turn(first.session_id, "yes")
    assert stray.kind == "backchannel" and not run.task.done()  # type: ignore[union-attr]
    await manager.turn(first.session_id, "hold it")
    stopped = await manager.turn(first.session_id, "Yes, stop.")
    assert (stopped.kind, stopped.reply) == ("stop", "Stopping the team.")
    with pytest.raises(asyncio.CancelledError):
        await run.task  # type: ignore[misc]
    provider.release.set()


async def test_stop_by_voice_is_confirmed_aloud(finance: Any) -> None:
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance, ["Stop.", "Yes."], provider=provider, mode="duplex", approval_policy="never", still_working_s=0
    )
    await session.start()
    await session.control({"type": "text", "text": TEAM_QUESTION})
    await wait_for(lambda: bool(wire.of("turn")))
    run = manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    await stream(session, wav_bytes("okay"))  # heard as "Stop."
    await wait_for(lambda: any(m["text"] == STOP_QUESTION for m in wire.of("say")))
    assert not run.task.done()  # type: ignore[union-attr]
    await asyncio.sleep(0.3)  # the question has been said: the founder answers after it
    session.speaking_until = 0.0
    await stream(session, wav_bytes("okay"))  # heard as "Yes."
    await wait_for(lambda: any(m["text"] == "Stopping the team." for m in wire.of("say")))
    await wait_for(lambda: run.task.done())  # type: ignore[union-attr]
    provider.release.set()
    await session.close()


# --- R2: barge-in timings ---------------------------------------------------------------------------------------------
async def test_barge_in_timing_survives_a_switch_of_mode(finance: Any) -> None:
    """The cause of paused_ms of 35,000 to 168,000: the endpointer counted its frames from zero again, the arrival
    times did not, so a later onset was read from a frame that had arrived long before."""
    session, wire, *_ = make(finance, ["Wait, stop. What about two hires instead?"], mode="duplex", barge_in_ms=600)
    now = [1000.0]
    session.clock = lambda: now[0]

    async def play(data: bytes) -> None:
        for i in range(0, len(data), FRAME * 2):
            now[0] += FRAME / 16000
            await session.audio(data[i : i + FRAME * 2])

    await session.start()
    await play(SILENCE * 400)  # 12.8 s of a quiet room, hands-free
    await session.control({"type": "mode", "mode": "ptt"})
    await session.control({"type": "mode", "mode": "duplex"})
    session.speaking_until = now[0] + 60
    await play(wav_bytes("stop_wait"))
    barge = session.metrics.barge_ins[-1]
    assert (barge.verdict, barge.by) == ("barge_in", "duration")
    assert barge.paused_ms is not None and 0 <= barge.paused_ms < 500, barge
    assert barge.stopped_ms is not None and 500 <= barge.stopped_ms < 1500, barge
    await wait_for(lambda: bool(wire.of("transcript")))
    await wait_for(lambda: barge.text.startswith("Wait, stop."))  # its words, once they are known: no empty row
    await session.close()


async def test_a_stale_onset_is_never_reported(finance: Any) -> None:
    session, *_ = make(finance, [], mode="duplex")
    now = [50.0]
    session.clock = lambda: now[0]
    session.arrivals.append(10.0)  # a frame from 40 s ago, as after the old fault
    assert session._arrival(0) == 50.0
    session.arrivals.append(49.9)
    assert session._arrival(1) == 49.9


# --- R8: re-run one agent; an accepted change is applied and shown ----------------------------------------------------
async def test_rerun_after_the_answer_runs_only_that_agent(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    old = await finished(manager, first.run_id)
    again = await manager.turn(first.session_id, "Re-run the analyst.")
    assert again.started_run and again.run_id != first.run_id
    assert again.reply == "Re-running only the Financial Analyst again. The rest of the team's findings stand."
    new = await finished(manager, again.run_id)
    done = [e for e in manager.bus.history(again.run_id) if e.type == "agent.done"]
    kept = {e.agent_id for e in done if e.data.get("kept")}
    ran = [a for a in new.team if a.id not in kept]
    assert [a.type for a in ran] == ["financial_analyst"] and len(kept) == len(new.team) - 1
    # The others' findings are the ones from before, word for word; the answer is written again from all of them.
    before = {a.type: a.text for a in old.agents}
    assert all(a.text == before[a.type] for a in new.agents if a.agent_id in kept)
    assert new.message == old.message and new.answer.startswith("Proposed: ")
    assert [a.type for a in new.agents] == [a.type for a in old.agents]
    assert not any(n.startswith("Team:") for n in manager.sessions[first.session_id].narration[-3:])


async def test_rerun_with_a_change_to_the_inputs_runs_the_team_with_three_hires(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    again = await manager.turn(first.session_id, "Re-run the analyst, assume three hires.")
    new = await finished(manager, again.run_id)
    assert not any(e.data.get("kept") for e in manager.bus.history(again.run_id) if e.type == "agent.done")
    full = next(o for o in new.decision_frame.options if o.is_full)
    assert (full.monthly, full.runway_change_months) == (43770.86, -2.58)


@pytest.mark.parametrize("answer", ["yes", "Yes.", "Yeah, do it.", "restart", "Okay."])
async def test_an_accepted_change_is_applied(finance: Any, answer: str) -> None:
    """ "Assume 3 hires." offered a restart, and the answers afterwards still showed 2 hires ($32,347.24, -2.07)."""
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    old = await finished(manager, first.run_id)
    assert "$32,347.24" in old.answer and "(-2.07)" in old.answer  # two hires, the placeholder
    offer = await manager.turn(first.session_id, "Assume 3 hires.")
    assert offer.reply == "That changes the decision. Restart with your change?" and offer.amendment_id
    accepted = await manager.turn(first.session_id, answer)
    assert accepted.started_run and accepted.run_id not in (None, first.run_id)
    assert accepted.answered == {"what": "amendment", "id": offer.amendment_id, "accept": True}
    new = await finished(manager, accepted.run_id)
    assert "$43,770.86" in new.answer and "(-2.58)" in new.answer and "three local hires, as you asked" in new.answer
    assert "$32,347.24" not in new.answer
    full = next(o for o in new.decision_frame.options if o.is_full)
    assert (full.monthly, full.runway_change_months) == (43770.86, -2.58)


async def test_the_on_screen_restart_applies_the_change_too(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    offer = await manager.turn(first.session_id, "Assume 3 hires.")
    answer = manager.answer_amendment(first.session_id, offer.amendment_id or "", True)  # the card's button
    new = await finished(manager, answer["run_id"])
    assert "$43,770.86" in new.answer and "(-2.58)" in new.answer
    late = await manager.turn(first.session_id, "yes")  # the offer has been answered: "yes" is only a noise now
    assert late.kind == "backchannel" and not late.started_run


async def test_a_declined_change_changes_nothing(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    offer = await manager.turn(first.session_id, "Assume 3 hires.")
    declined = await manager.turn(first.session_id, "No.")
    assert declined.reply == "Okay, I'll leave it as it is." and not declined.started_run
    assert declined.answered == {"what": "amendment", "id": offer.amendment_id, "accept": False}
    assert manager.sessions[first.session_id].run_id == first.run_id


@pytest.mark.parametrize("words", ["Yes.", "Restart."])
async def test_a_restart_accepted_by_voice_is_shown_and_summarised(finance: Any, words: str) -> None:
    """The run did restart, but the screen was never told, so it went on showing the two-hire answer."""
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    first_run = wire.of("turn")[0]["outcome"]["run_id"]
    await finished(manager, first_run)
    await wait_for(lambda: any(m["text"].startswith("Want") for m in wire.of("say")))
    await session.control({"type": "text", "text": "Assume 3 hires."})
    await wait_for(lambda: len(wire.of("turn")) == 2)
    offered = wire.of("turn")[1]["outcome"]
    assert offered["amendment_id"] and offered["reply"] == "That changes the decision. Restart with your change?"
    await session.control({"type": "text", "text": words})
    await wait_for(lambda: len(wire.of("turn")) == 3)
    restarted = wire.of("turn")[2]["outcome"]  # what the canvas follows
    assert restarted["run_id"] not in (None, first_run) and restarted["started_run"]
    assert restarted["answered"] == {"what": "amendment", "id": offered["amendment_id"], "accept": True}
    new = await finished(manager, restarted["run_id"])
    assert "$43,770.86" in new.answer
    await wait_for(lambda: sum(m["text"].startswith("My proposal is ") for m in wire.of("say")) == 2)
    said = [m["text"] for m in wire.of("say")]
    assert "Restarting with your change." in said
    assert any("around 44 thousand dollars a month" in t for t in said)  # three hires, said rounded
    assert session.metrics.turns[-1].kind == "restarted"
    await session.close()


# --- R4, R5: one opening turn, silence, then a summary that ends with an offer ----------------------------------------
async def test_a_team_run_is_one_opening_turn_then_silence_then_findings_outcome_and_an_offer(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    await finished(manager, wire.of("turn")[0]["outcome"]["run_id"])
    await wait_for(lambda: any(m["text"].startswith("Want") for m in wire.of("say")))
    await asyncio.sleep(0.2)
    says = [(m["lane"], m["text"]) for m in wire.of("say")]
    assert says[0] == ("conversation", "On it.")
    assert says[1] == (
        "conversation",
        "I've put together a team of five: the Financial Analyst, Librarian, Market Scout, Regulatory and Tax and a "
        "Devil's Advocate. They're looking at the Dubai office from different angles so the decision holds up.",
    )
    # Nothing else from the lane: no line per agent or stage, no Verifier line, no assumption question.
    assert [lane_ for lane_, _ in says[2:]] == ["answer"] * (len(says) - 2)
    answer = [text for _, text in says[2:]]
    proposal = next(i for i, text in enumerate(answer) if text.startswith("My proposal is "))
    assert 1 <= proposal <= 3  # the team's two or three key findings come first
    assert answer[0].startswith("The full office would cost ")
    assert answer[proposal + 1].startswith("The trade-off: ")
    # R5: it ends with an offer, and then it stops. (This fake team's Devil's Advocate only asks a question, so
    # there are no risks to offer; with real findings the offer is "Want me to go through the risks?".)
    assert answer[-1] == "Want the other options?" and len(answer) == proposal + 3
    assert not EXACT_FIGURE.search(" ".join(text for _, text in says))
    await session.close()


async def test_a_long_run_gets_one_still_working_line(finance: Any) -> None:
    provider = slow_provider()
    session, wire, _, _tts, manager = make(finance, [], provider=provider, approval_policy="never", still_working_s=0.2)
    await session.start()
    await session.control({"type": "text", "text": TEAM_QUESTION})
    await wait_for(lambda: any(m["text"] == STILL_WORKING for m in wire.of("say")))
    await asyncio.sleep(0.6)
    said = [m["text"] for m in wire.of("say")]
    assert said.count(STILL_WORKING) == 1 and said.index(STILL_WORKING) == 2  # after "On it." and the opening turn
    provider.release.set()
    await finished(manager, wire.of("turn")[0]["outcome"]["run_id"])
    await session.close()


async def test_a_quick_run_gets_no_still_working_line(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0.3)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    await finished(manager, wire.of("turn")[0]["outcome"]["run_id"])
    await asyncio.sleep(0.6)
    assert STILL_WORKING not in [m["text"] for m in wire.of("say")]
    await session.close()


def test_a_decision_summary_always_ends_with_an_offer() -> None:
    """R5: no Devil's Advocate on the team and a single option: there is still an offer to end on."""
    option = SimpleNamespace(
        name="Hire one first",
        modelled=True,
        one_off=0.0,
        monthly=11423.62,
        runway_change_months=-0.7,
        is_full=False,
        trade_off="",
    )
    frame = SimpleNamespace(
        options=[option],
        default_option="Hire one first",
        goals=[],
        currency="USD",
        cost_model=None,
        cost_sentence=lambda: "",
    )
    result = SimpleNamespace(
        answer="x", status="done", decision_frame=frame, metrics=[], cash_risk=None, agents=[], assumptions_to_confirm=0
    )
    spoken = summarise(result)
    assert spoken.lead[-1].startswith("My proposal is Hire one first: ")
    assert spoken.more and spoken.more[0].offer == "Want me to go through the costs?"


async def test_a_listening_noise_after_the_summary_brings_the_offer_back(finance: Any) -> None:
    """R5: "uh-huh" over the summary cut it off before the offer. The offer is said again."""
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    await finished(manager, wire.of("turn")[0]["outcome"]["run_id"])
    await wait_for(lambda: any(m["text"].startswith("Want") for m in wire.of("say")))
    before = len(wire.of("say"))
    await session._interrupt("barge-in")  # as a barge-in does: what was still to be said is dropped
    await session.control({"type": "text", "text": "Uh-huh."})
    await wait_for(lambda: len(wire.of("say")) > before)
    assert wire.of("say")[-1]["text"] == session.offers.more[0].offer == "Want the other options?"
    await session.close()


# --- R6: transcription ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("heard", "meant"),
    [
        ("should be open a Dubai office", "should we open a Dubai office"),
        ("Should be hire two engineers?", "Should we hire two engineers?"),
        ("Freerun the analyst assume 3 hires", "Re-run the analyst assume 3 hires"),
        ("Free run the Devil's Advocate.", "Re-run the Devil's Advocate."),
        ("rerun the market scout", "Re-run the market scout"),
        ("We run the analyst", "Re-run the analyst"),
        # Left as heard: real sentences.
        ("It should be open by March.", "It should be open by March."),
        ("We run payroll on the first.", "We run payroll on the first."),
        ("What is our runway?", "What is our runway?"),
    ],
)
def test_a_commands_opening_is_repaired_by_code(heard: str, meant: str) -> None:
    assert corrected(heard) == meant


def test_the_recogniser_is_told_the_words_it_will_hear() -> None:
    for term in ("Dubai", "hires", "runway", "churn", "FounderOS", "Financial Analyst", "Devil's Advocate"):
        assert term in HOTWORDS or term in PROMPT, term
    assert "Re-run the Financial Analyst, assume three hires." in PROMPT
    assert "Should we open a Dubai office?" in PROMPT and "two person team" in PROMPT

    class Model:
        def __init__(self) -> None:
            self.kwargs: dict[str, Any] = {}

        def transcribe(self, samples: Any, **kwargs: Any) -> tuple[list[Any], None]:
            self.kwargs = kwargs
            return [
                SimpleNamespace(text=" Should we open a Dubai office?", avg_logprob=-0.2, no_speech_prob=0.01)
            ], None

    stt = FasterWhisperSTT.__new__(FasterWhisperSTT)
    stt._model, stt.prompt, stt.hotwords = Model(), PROMPT, HOTWORDS
    heard = stt.transcribe(np.zeros(1600, dtype=np.float32))
    assert stt._model.kwargs["initial_prompt"] == PROMPT and stt._model.kwargs["hotwords"] == HOTWORDS
    assert heard.text == "Should we open a Dubai office?" and 0.8 < heard.confidence < 0.83
    stt.prompt = stt.hotwords = ""  # VOICE_STT_VOCABULARY=false
    stt.transcribe(np.zeros(1600, dtype=np.float32))
    assert stt._model.kwargs["initial_prompt"] is None and stt._model.kwargs["hotwords"] is None


def test_confidence_falls_with_unsure_words_and_with_no_speech() -> None:
    sure = SimpleNamespace(text="What is our runway", avg_logprob=-0.1, no_speech_prob=0.0)
    unsure = SimpleNamespace(text="Freerun the another test", avg_logprob=-1.2, no_speech_prob=0.1)
    noise = SimpleNamespace(text="you", avg_logprob=-0.4, no_speech_prob=0.9)
    assert confidence_of([sure]) > 0.9 > 0.45 > confidence_of([unsure])
    assert confidence_of([noise]) < 0.1 and confidence_of([]) == 1.0


async def test_an_unsure_turn_is_read_back_before_it_is_acted_on(finance: Any) -> None:
    script = ["Freerun the another test assume three hires", "No.", "What is our runway?", "Is it that?", "Yes."]
    session, wire, stt, _tts, _ = make(finance, script, mode="duplex", confirm_below=0.45)
    stt.confidences = [0.3, 0.9, 0.9, 0.3, 0.9]
    await session.start()

    async def say() -> None:
        session.speaking_until = 0.0
        await stream(session, wav_bytes("runway"))

    await say()
    await wait_for(lambda: bool(wire.of("unsure")))
    await wait_for(lambda: bool(wire.of("say")))
    asked = wire.of("say")[0]["text"]
    assert asked == "Did you say: Re-run the another test assume three hires? Say yes, or say it again."
    assert not wire.of("turn")  # nothing has been acted on
    await say()  # "No."
    await wait_for(lambda: any(m["text"] == SAY_AGAIN for m in wire.of("say")))
    assert not wire.of("turn")
    await say()  # said again, and heard clearly this time
    await wait_for(lambda: len(wire.of("turn")) == 1)
    await say()  # unsure again
    await wait_for(lambda: len(wire.of("unsure")) == 2)
    await say()  # "Yes.": taken as it was heard
    await wait_for(lambda: len(wire.of("turn")) == 2)
    assert session.metrics.turns[-1].text == "Is it that?"
    await session.close()


async def test_a_sure_turn_and_a_plain_yes_are_never_read_back(finance: Any) -> None:
    session, wire, stt, *_ = make(finance, ["What is our runway?", "Okay."], mode="duplex", confirm_below=0.45)
    stt.confidences = [0.9, 0.2]
    await session.start()
    await stream(session, wav_bytes("runway"))
    await wait_for(lambda: bool(wire.of("turn")))
    session.speaking_until = 0.0
    await stream(session, wav_bytes("okay"))
    await wait_for(lambda: len(wire.of("transcript")) == 2)
    await asyncio.sleep(0.2)
    assert not wire.of("unsure")
    await session.close()


# --- R3: an unclear number is confirmed before it is applied ----------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "question", "meant"),
    [
        ("Make it a 2% team.", "Did you mean two people?", "Make it a 2 person team."),
        ("assume 2 percent", "Did you mean two people?", "assume 2 hires"),
        ("two", "Did you mean two people?", "Assume 2 hires"),
        ("Assume 3.", "Did you mean three people?", "Assume 3 hires"),
        ("make it four", "Did you mean four people?", "Assume 4 hires"),
        ("Actually, one.", "Did you mean one person?", "Assume 1 hire"),
    ],
)
def test_a_number_with_the_wrong_or_no_unit_is_asked_about(text: str, question: str, meant: str) -> None:
    assert count_reading(text, counts=True, percents=False) == (question, meant)


@pytest.mark.parametrize(
    "text",
    ["Assume 3 hires.", "make it a two person team", "What is 2% of revenue?", "assume 15% growth", "Is it two?"],
)
def test_a_number_with_its_unit_or_a_question_is_not_asked_about(text: str) -> None:
    assert count_reading(text, counts=True, percents=False) is None


def test_a_percentage_is_a_percentage_where_the_decision_has_one() -> None:
    assert count_reading("make it 2%", counts=False, percents=True) is None  # a price change
    assert count_reading("make it 2%", counts=True, percents=True) is None  # the decision has a rate of its own


async def test_two_percent_is_confirmed_as_two_people_before_anything_changes(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    asked = await manager.turn(first.session_id, "Make it a 2% team.")
    assert (asked.kind, asked.reply) == ("confirm", "Did you mean two people?")
    assert not asked.amendment_id and not asked.started_run
    assert not manager.sessions[first.session_id].amendments  # nothing offered, nothing applied
    no = await manager.turn(first.session_id, "No.")
    assert (
        no.reply.startswith("Okay, nothing has changed.") and manager.sessions[first.session_id].run_id == first.run_id
    )
    await manager.turn(first.session_id, "two")
    yes = await manager.turn(first.session_id, "Yes.")
    assert yes.started_run and yes.reply == "Restarting with your change."  # confirmed once, not asked twice
    new = await finished(manager, yes.run_id)
    hires = next(i for i in new.decision_frame.cost_model.items if i.key == "hires")
    assert (hires.base, hires.basis) == (2.0, "founder") and new.message.endswith("Assume 2 hires")


async def test_a_percentage_changes_a_price_decision_without_a_question(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, "Should we raise prices by 10%?")
    await finished(manager, first.run_id)
    change = await manager.turn(first.session_id, "Make it 15%.")
    assert change.kind == "amendment" and change.reply == "That changes the decision. Restart with your change?"


# --- R7: a proposed memo on record gets one question ------------------------------------------------------------------
TARGET_QUESTIONS = [
    "Is the runway still above 10.44 months by 2027-05-06, as predicted?",
    "Is the risk of runway falling below 6 months by March 2027 acceptable?",
]


@pytest.mark.parametrize("question", TARGET_QUESTIONS)
def test_a_target_or_kill_criterion_question_is_about_a_draft(question: str) -> None:
    assert asks_about_a_draft(question)


def test_with_a_proposed_memo_on_record_only_what_has_changed_is_asked() -> None:
    lead = (
        "Proposed: Travel-led pilot, $3,000.00 a month, runway -0.21 months. You already have a proposed memo on "
        "this from 2026-11-06 [decisions/2026-11-06-dubai-office.md]: what has changed since you drafted it?"
    )
    prose = (
        "The pilot is the easier step to undo. "
        + " ".join(TARGET_QUESTIONS)
        + " You already have a proposed memo on this from 6 November. What would make you stop? "
    )
    gate = _SentenceGate([], "Should we open a Dubai office?", None, [])
    gate.draft_on_record = True
    assert gate._budgeted(prose).strip() == "The pilot is the easier step to undo."
    answer = f"{lead} {gate._budgeted(prose).strip()}"
    assert answer.count("?") == 1 and answer.count("proposed memo") == 1  # one question, the memo named once
    assert "what has changed since you drafted it?" in answer
    # With no draft on record the Advisor's own question stays.
    free = _SentenceGate([], "Should we open a Dubai office?", None, [])
    assert "What would make you stop?" in free._budgeted(prose)


def test_the_spoken_risks_are_statements_never_questions_about_targets() -> None:
    option = SimpleNamespace(
        name="Travel-led pilot",
        modelled=True,
        one_off=0.0,
        monthly=3000.0,
        runway_change_months=-0.21,
        is_full=False,
        trade_off="slower to learn the market",
    )
    frame = SimpleNamespace(
        options=[option], default_option="Travel-led pilot", goals=[], currency="USD", cost_model=None
    )
    advocate = SimpleNamespace(
        type="devils_advocate",
        status="done",
        text="Dubai demand is unproven. " + " ".join(TARGET_QUESTIONS) + " A local partner may want exclusivity.",
    )
    result = SimpleNamespace(
        answer="x",
        status="done",
        decision_frame=frame,
        metrics=[],
        cash_risk=None,
        agents=[advocate],
        assumptions_to_confirm=0,
    )
    risks = summarise(result).more[0]
    assert risks.key == "risks" and risks.lines == [
        "Dubai demand is unproven.",
        "A local partner may want exclusivity.",
    ]


async def test_a_yes_spoken_over_the_end_of_the_question_is_still_an_answer(finance: Any) -> None:
    """ "Yes" while "Stop the team? Say yes to stop." is still playing must not be taken for a listening noise."""
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance, ["Yes."], provider=provider, mode="duplex", approval_policy="never", still_working_s=0
    )
    await session.start()
    await session.control({"type": "text", "text": TEAM_QUESTION})
    await wait_for(lambda: bool(wire.of("turn")))
    run = manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    await session.control({"type": "text", "text": "stop"})
    await wait_for(lambda: any(m["text"] == STOP_QUESTION for m in wire.of("say")))
    session.speaking_until = session.clock() + 30  # the question is still being played
    await stream(session, wav_bytes("okay"))  # heard as "Yes."
    await wait_for(lambda: any(m["text"] == "Stopping the team." for m in wire.of("say")))
    await wait_for(lambda: run.task.done())  # type: ignore[union-attr]
    assert session.metrics.barge_ins[-1].verdict == "barge_in"
    provider.release.set()
    await session.close()
