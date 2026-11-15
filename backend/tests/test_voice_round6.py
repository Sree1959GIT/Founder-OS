"""M5 founder re-test, round 5 (2026-11-15): U0 to U5 and the reminder, built from the founder's real turns.

The turns below are the founder's own, as this PC logged them during the RY re-test (2026-11-15, about 14:00 to
15:05 IST): `data/default/decision_log.jsonl` and the voice metrics (`GET /api/voice/metrics`). Only turn text and
timings were taken from those logs.

- RY2: "Assume three hires." was heard twice, both times over FounderOS's own speech (barge-ins by duration), and
  neither became a turn. Then "Ugh.".
- RY4: "Ugh." (the founder's "mm"), "Okay.", "No?", then "Okay, I will leave it as it is.", which started a team.
- RY5: "Hello.", "Yes.", then "Hello? Yes?", which started a run.
- RY6: "Re-run the Analyt.", which started a new team.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.conversation.classifier import clear_request, is_filler, is_greeting, is_noise
from app.conversation.manager import GREETING, RESTART_OFFER, change_reminder, fuzzy_agent
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from tests.test_voice import make, stream, wav_bytes
from tests.test_voice_round2 import DUBAI, finished, lane, wait_for
from tests.test_voice_round5 import LastAgentHeld, cards, one_left, quiet, said

CHANGE = "Assume three hires."
FILLERS = ["Ugh.", "Mm.", "Hmm.", "Uh.", "Uh-huh.", "Ah.", "Oh.", "Mm-hmm."]


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


async def answered_with_change_open(finance: Any) -> tuple[Any, str, str]:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    offered = await manager.turn(first.session_id, CHANGE, spoken=True)
    await finished(manager, first.run_id)
    return manager, first.session_id, offered.amendment_id or ""


# --- U0: only a clear request starts a team ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        DUBAI,
        "What is our runway?",
        "Compare the travel pilot with a full office",
        "Should we hire two engineers this year?",
        "Can you draft a memo on the Dubai office?",
        "We are thinking about raising prices by ten percent",
    ],
)
def test_a_clear_request_is_recognised(text: str) -> None:
    assert clear_request(text)


@pytest.mark.parametrize(
    "text",
    ["Okay, I will leave it as it is.", "Hello? Yes?", "Re-run the Analyt.", "Ugh.", "Yes.", "The Dubai thing"],
)
def test_the_founders_unclear_turns_are_not_requests(text: str) -> None:
    assert not clear_request(text)


@pytest.mark.parametrize("text", ["Okay, I will leave it as it is.", "The Dubai thing worries me"])
async def test_an_unclear_turn_is_read_back_and_runs_only_on_yes(finance: Any, text: str) -> None:
    """RY4's "Okay, I will leave it as it is." started a team (Financial Analyst, Librarian, Perspective lens,
    Devil's Advocate). Now it is read back, and nothing runs unless the founder says yes."""
    manager = lane(finance)
    asked = await manager.turn(None, text, spoken=True)
    assert not asked.started_run and asked.run_id is None and not manager.orchestrator.runs
    assert asked.reply == f"Did you say: {text.rstrip('.')}? Say yes to look into it, or say it again."
    dropped = await manager.turn(asked.session_id, "No.", spoken=True)
    assert dropped.reply == "Okay. Say it again." and not manager.orchestrator.runs
    await manager.turn(asked.session_id, text, spoken=True)
    yes = await manager.turn(asked.session_id, "Yes.", spoken=True)
    assert yes.started_run and manager.orchestrator.runs[yes.run_id or ""].message == text
    await finished(manager, yes.run_id)


# --- U2: a filler does nothing, before or after an offer --------------------------------------------------------------
@pytest.mark.parametrize("filler", FILLERS)
async def test_a_filler_with_nothing_on_offer_does_nothing(finance: Any, filler: str) -> None:
    assert is_filler(filler) and is_noise(filler)
    manager = lane(finance)
    outcome = await manager.turn(None, filler, spoken=True)
    assert (outcome.kind, outcome.reply, outcome.started_run) == ("backchannel", "", False)
    assert not manager.orchestrator.runs


@pytest.mark.parametrize("filler", FILLERS)
async def test_a_filler_after_the_offer_is_neither_yes_nor_no(finance: Any, filler: str) -> None:
    """RY4: "Ugh." after the change's offer. It never declines the change and never starts a team; the "Okay."
    after it still restarts with the change."""
    manager, session_id, amendment_id = await answered_with_change_open(finance)
    runs = len(manager.orchestrator.runs)
    noise = await manager.turn(session_id, filler, spoken=True)
    assert noise.answered is None and noise.reply == "" and not noise.started_run
    assert len(manager.orchestrator.runs) == runs
    state = manager.state(session_id)
    assert state is not None and [a["status"] for a in state["amendments"]] == ["offered"]
    yes = await manager.turn(session_id, "Okay.", spoken=True)
    assert yes.answered == {"what": "amendment", "id": amendment_id, "accept": True}
    new = await finished(manager, yes.run_id)
    assert "$43,770.86" in new.answer


async def test_its_own_reply_heard_back_with_i_will_for_ill_is_an_echo(finance: Any) -> None:
    """RY4: "Okay, I will leave it as it is." is how Whisper writes FounderOS's own "Okay, I'll leave it as it is.";
    heard as it plays, it is an echo, never a turn."""
    session, _wire, _, _tts, _manager = make(finance, [])
    session._own_words.append((session.clock(), "Okay, I'll leave it as it is."))
    assert session._own_echo("Okay, I will leave it as it is.")
    assert not session._own_echo("Okay.")


# --- U1: a change said in the last stage is offered at once -----------------------------------------------------------
async def test_the_founders_ry2_change_over_its_own_speech_in_the_last_stage_is_offered(finance: Any) -> None:
    """RY2, first try, as logged: "Assume three hires." said over FounderOS's speech while the Devil's Advocate
    worked, twice, then "Ugh.". Neither became a turn. The likeliest path, given that no turn was recorded: the
    recogniser was unsure of the first, so it was read back ("Did you say: Assume three hires?"), and the second,
    said over that read-back, matched the read-back's words and was dropped as an echo. Now a change is never read
    back while a team works: its offer is the question, and it is said at once."""
    provider = LastAgentHeld(default=lambda m, t, s: "No numbers here.")
    session, wire, _, _tts, manager = make(
        finance,
        [CHANGE, CHANGE, "Ugh.", "Yes."],
        provider=provider,
        mode="duplex",
        approval_policy="never",
        still_working_s=0,
        confirm_below=0.45,
    )
    session.stt.confidences = [0.3, 0.3, 0.9, 0.9]
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run = manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    provider.is_last = lambda: one_left(manager, run.run_id)
    await wait_for(lambda: provider.holding)  # only the Devil's Advocate is working
    await quiet(session)
    session.speaking_until = session.clock() + 30  # FounderOS is speaking: the founder talks over it
    await stream(session, wav_bytes("dubai"))
    await wait_for(lambda: RESTART_OFFER in said(wire))
    assert not run.task.done() and len(cards(manager)) == 1  # type: ignore[union-attr]
    assert not any(t.startswith("Did you say") for t in said(wire))
    provider.release.set()
    await finished(manager, run.run_id)
    await session._answers_idle.wait()
    await wait_for(lambda: session._says.empty() and session._current is None)
    reminder = change_reminder(CHANGE)
    await wait_for(lambda: reminder in said(wire))
    assert said(wire).count(reminder) == 1 and said(wire).count(RESTART_OFFER) == 1
    await session.close()


async def test_the_same_words_said_over_their_read_back_are_the_founder_not_an_echo(finance: Any) -> None:
    session, _wire, _, _tts, _manager = make(finance, [])
    session._unsure = CHANGE
    session._own_words.append((session.clock(), f"Did you say: {CHANGE.rstrip('.')}? Say yes, or say it again."))
    assert not session._own_echo(CHANGE)


# --- U3: a re-run named imperfectly -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("heard", "kind", "sure"),
    [
        ("Analyt.", "financial_analyst", True),
        ("analist", "financial_analyst", True),
        ("Devil", "devils_advocate", True),
        ("scot", "market_scout", True),
        ("Librarain", "librarian", False),
    ],
)
def test_an_agent_heard_imperfectly_is_found(heard: str, kind: str, sure: bool) -> None:
    found = fuzzy_agent(heard)
    assert found is not None and (found[0], found[3]) == (kind, sure)


def test_words_that_are_no_agent_are_not_matched() -> None:
    assert fuzzy_agent("forecast for next year") is None and fuzzy_agent("numbers") is None


async def test_the_founders_rerun_the_analyt_reruns_only_the_analyst(finance: Any) -> None:
    """RY6: "Re-run the Analyt." started a new team with a Perspective lens, whose answer had 13 metric chips."""
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    old = await finished(manager, first.run_id)
    again = await manager.turn(first.session_id, "Re-run the Analyt.", spoken=True)
    assert again.reply == "Re-running only the Financial Analyst again. The rest of the team's findings stand."
    run = manager.orchestrator.runs[again.run_id or ""]
    assert set(run.reuse) and all(r.type != "financial_analyst" for r in run.reuse.values())
    new = await finished(manager, again.run_id)
    assert run.plan is not None and [i.type for i in run.plan.team] == [i.type for i in old_team(manager, first)]
    metrics = [m.metric for m in new.metrics]
    assert len(metrics) == len(set(metrics))  # U5: one chip per metric
    assert old.answer and new.answer


def old_team(manager: Any, first: Any) -> list[Any]:
    plan = manager.orchestrator.runs[first.run_id].plan
    return list(plan.team)


async def test_a_rerun_two_letters_off_is_asked_about(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    runs = len(manager.orchestrator.runs)
    asked = await manager.turn(first.session_id, "Re-run the Librarain.", spoken=True)
    assert asked.reply == "Did you mean re-run the Librarian?" and len(manager.orchestrator.runs) == runs
    yes = await manager.turn(first.session_id, "Yes.", spoken=True)
    assert yes.reply.startswith("Re-running only the Librarian")
    await finished(manager, yes.run_id)


# --- U4: a greeting gets a greeting -----------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["Hello? Yes?", "Hello.", "Hi there", "Good morning!"])
async def test_a_greeting_gets_a_short_greeting_and_never_an_earlier_answer(finance: Any, text: str) -> None:
    """RY5: "Hello? Yes?" got a reply that repeated the Dubai answer's text."""
    assert is_greeting(text)
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    old = await finished(manager, first.run_id)
    runs = len(manager.orchestrator.runs)
    hello = await manager.turn(first.session_id, text, spoken=True)
    assert hello.reply == GREETING and not hello.started_run and len(manager.orchestrator.runs) == runs
    assert not any(s.strip() and s.strip() in hello.reply for s in old.answer.split(". ")[:3])
    yes = await manager.turn(first.session_id, "Yes.", spoken=True)  # nothing on offer: nothing happens
    assert (yes.reply, yes.started_run) == ("", False) and len(manager.orchestrator.runs) == runs


# --- the reminder -----------------------------------------------------------------------------------------------------
def test_the_reminder_names_the_change() -> None:
    assert change_reminder(CHANGE) == "Your change to three hires isn't in this answer yet. Say yes to restart with it."
    assert change_reminder("Also include tax in Dubai") == (
        'Your change "Also include tax in Dubai" isn\'t in this answer yet. Say yes to restart with it.'
    )


async def test_the_summary_ends_on_one_reminder_and_yes_restarts(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    first_run = wire.of("turn")[0]["outcome"]["run_id"]
    await session.control({"type": "text", "text": CHANGE})
    await wait_for(lambda: RESTART_OFFER in said(wire))
    await finished(manager, first_run)
    reminder = change_reminder(CHANGE)
    await wait_for(lambda: reminder in said(wire))
    await asyncio.sleep(0.3)
    assert said(wire)[-1] == reminder and said(wire).count(reminder) == 1
    assert not any(t.startswith("Want") for t in said(wire))
    await session.control({"type": "text", "text": "Yes."})
    await wait_for(lambda: "Restarting with your change." in said(wire))
    new = await finished(manager, wire.of("turn")[-1]["outcome"]["run_id"])
    assert "$43,770.86" in new.answer
    await session.close()
