"""M5 fix round 8 (founder live check after round 7, 2026-11-16).

- W3: a decision answer ends on ONE offer, said and shown in the chat; "yes" walks through the risks, "no" does nothing.
- W4: "Ok, I will leave it as it is." and its close variants keep things as they are: no read-back, no team.
- W5: "Re-run the Analyst." after a Librarian-only team uses the most recent decision team that had one, and says so.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.conversation.classifier import is_leave
from app.conversation.manager import LEAVE, YES_TO_WHAT, change_reminder
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from tests.test_voice_round2 import DUBAI, finished, lane

CHANGE = "Assume three hires."


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


def recaps(manager: Any, run_id: str) -> list[str]:
    return [e.data["text"] for e in manager.bus.history(run_id) if e.type == "recap"]


async def answered(manager: Any) -> Any:
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    return first


# --- W3 -------------------------------------------------------------------------------------------------------------
async def test_a_decision_answer_shows_one_offer_and_yes_goes_through_the_risks(finance: Any) -> None:
    manager = lane(finance)
    first = await answered(manager)
    shown = recaps(manager, first.run_id)
    assert len(shown) == 1 and shown[0].startswith("The answer is ready") and shown[0].endswith("?")  # one offer
    yes = await manager.turn(first.session_id, "yes")
    assert not yes.started_run and yes.reply and "?" not in yes.reply
    again = await manager.turn(first.session_id, "yes")
    assert not again.started_run and again.reply == YES_TO_WHAT  # founder Y2: asked once, and never silence


async def test_no_to_the_offer_does_nothing(finance: Any) -> None:
    manager = lane(finance)
    first = await answered(manager)
    no = await manager.turn(first.session_id, "no")
    assert no.reply == "" and not no.started_run


async def test_an_open_change_takes_the_place_of_the_offer(finance: Any) -> None:
    manager = lane(finance)
    first = await answered(manager)
    change = await manager.turn(first.session_id, CHANGE)
    assert change.reply == change_reminder(CHANGE)
    yes = await manager.turn(first.session_id, "yes")
    assert yes.started_run  # yes means the restart, never the risks


# --- W1 -------------------------------------------------------------------------------------------------------------
async def test_the_same_change_twice_after_the_answer_says_the_reminder_again_and_starts_nothing(finance: Any) -> None:
    manager = lane(finance)
    first = await answered(manager)
    one = await manager.turn(first.session_id, CHANGE)
    two = await manager.turn(first.session_id, CHANGE)
    assert two.reply == change_reminder(CHANGE) and two.amendment_id == one.amendment_id and not two.started_run
    state = manager.state(first.session_id)
    assert [a["status"] for a in state["amendments"]] == ["offered"]


# --- W4 -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "said",
    ["Ok, I will leave it as it is.", "leave it", "Keep it as is.", "That's fine.", "Okay, leave it.", "It's fine."],
)
def test_leave_phrases(said: str) -> None:
    assert is_leave(said)


@pytest.mark.parametrize("said", ["Should we leave Dubai?", "keep going", "fine", "That is the question.", "it's"])
def test_not_leave_phrases(said: str) -> None:
    assert not is_leave(said)


@pytest.mark.parametrize("said", ["Ok, I will leave it as it is.", "Keep it as is.", "That's fine."])
async def test_leave_it_after_an_answer_keeps_things_as_they_are(finance: Any, said: str) -> None:
    manager = lane(finance)
    first = await answered(manager)
    out = await manager.turn(first.session_id, said)
    assert out.reply == LEAVE and not out.started_run


async def test_leave_it_declines_an_open_change(finance: Any) -> None:
    manager = lane(finance)
    first = await answered(manager)
    await manager.turn(first.session_id, CHANGE)
    out = await manager.turn(first.session_id, "Ok, I will leave it as it is.")
    assert out.reply == LEAVE and not out.started_run and out.answered and out.answered["accept"] is False
    assert [a["status"] for a in manager.state(first.session_id)["amendments"]] == ["declined"]


# --- W5 -------------------------------------------------------------------------------------------------------------
async def test_rerun_the_analyst_after_a_librarian_only_team_uses_the_last_decision_team(finance: Any) -> None:
    manager = lane(finance)
    first = await answered(manager)
    past = await manager.turn(first.session_id, "What did we decide before about Dubai?")
    await finished(manager, past.run_id)
    run = manager.orchestrator.runs[past.run_id]
    assert all(i.type != "financial_analyst" for i in run.plan.team)
    manager.sessions[first.session_id].decision_run_id = None  # the open decision is lost: the session's runs remain
    out = await manager.turn(first.session_id, "Re-run the Analyst.")
    assert out.started_run, out.reply
    assert out.reply.startswith("Re-running only the Financial Analyst on the Dubai question")
    await finished(manager, out.run_id)


async def test_rerun_an_agent_no_recent_team_had(finance: Any) -> None:
    manager = lane(finance)
    past = await manager.turn(None, "What did we decide before about Dubai?")
    await finished(manager, past.run_id)
    out = await manager.turn(past.session_id, "Re-run the Analyst.")
    assert out.reply == "The Financial Analyst is not on this team." and not out.started_run
