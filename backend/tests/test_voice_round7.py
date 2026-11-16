"""M5 fix round 7 (founder RL2, 2026-11-16): a change is always said aloud, and the run's stage is on screen.

- A change said after the run has finished gets the reminder ("Your change to three hires isn't in this answer yet.
  Say yes to restart with it."), once, and never the mid-run offer.
- A change said while the summary is being spoken stops it, and the reminder is said in its place.
- `run.progress`: "Step N of M: <agent> working…", then "Verifying…", then "Done"; text only, never spoken.
- `FOUNDEROS_STAGE_DELAY_S` (dev only) pauses before each stage.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.graph import PROGRESS_DONE, PROGRESS_VERIFYING, progress_line
from app.config import Settings
from app.conversation.manager import RESTART_OFFER, change_reminder
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from tests.test_voice import make
from tests.test_voice_round2 import DUBAI, finished, lane, wait_for
from tests.test_voice_round5 import cards, said

CHANGE = "Assume three hires."
REMINDER = change_reminder(CHANGE)


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


def progress(manager: Any, run_id: str) -> list[str]:
    return [e.data["text"] for e in manager.bus.history(run_id) if e.type == "run.progress"]


# --- the progress line ------------------------------------------------------------------------------------------------
def test_the_progress_line_names_the_stage_and_its_agents() -> None:
    assert progress_line(1, 3, ["Librarian"]) == "Step 1 of 3: Librarian working…"
    assert progress_line(2, 3, ["Market Scout", "Financial Analyst", "People and Ops"]) == (
        "Step 2 of 3: Market Scout, Financial Analyst and People and Ops working…"
    )


async def test_a_team_run_shows_each_stage_then_verifying_then_done(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    lines = progress(manager, first.run_id or "")
    steps = [line for line in lines if line.startswith("Step ")]
    assert len(steps) >= 2 and steps[0].startswith("Step 1 of ")
    total = steps[0].split(" of ")[1].split(":")[0]
    assert steps[-1].startswith(f"Step {total} of {total}:") and all(s.endswith("working…") for s in steps)
    assert lines[-2:] == [PROGRESS_VERIFYING, PROGRESS_DONE]
    history = manager.bus.history(first.run_id)
    done = next(e.seq for e in history if e.type == "run.progress" and e.data["text"] == PROGRESS_DONE)
    assert done < next(e.seq for e in history if e.type == "run.finished")


async def test_the_progress_line_is_never_spoken(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    await finished(manager, wire.of("turn")[0]["outcome"]["run_id"])
    await asyncio.sleep(0.3)
    assert not any(t.startswith(("Step ", "Verifying", "Done")) for t in said(wire))
    await session.close()


def test_the_stage_delay_is_off_by_default_and_read_from_its_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).founderos_stage_delay_s == 0  # type: ignore[call-arg]
    monkeypatch.setenv("FOUNDEROS_STAGE_DELAY_S", "1.5")
    assert Settings(_env_file=None).founderos_stage_delay_s == 1.5  # type: ignore[call-arg]


async def test_the_stage_delay_pauses_before_each_stage(finance: Any) -> None:
    manager = lane(finance, stage_delay_s=0.3)
    started = time.perf_counter()
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    stages = sum(line.startswith("Step ") for line in progress(manager, first.run_id or ""))
    assert time.perf_counter() - started >= 0.3 * stages - 0.05


# --- a change after the run has finished -----------------------------------------------------------------------------
async def test_a_change_after_the_answer_gets_the_reminder_once_and_yes_restarts(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    change = await manager.turn(first.session_id, CHANGE, spoken=True)
    assert change.reply == REMINDER and change.amendment_id and not change.started_run
    again = await manager.turn(first.session_id, CHANGE, spoken=True)  # said twice: still one card
    assert again.amendment_id == change.amendment_id and len(cards(manager)) == 1
    yes = await manager.turn(first.session_id, "Yes.", spoken=True)
    assert yes.started_run


async def test_by_voice_a_change_after_the_summary_is_said_once_as_the_reminder(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run_id = wire.of("turn")[0]["outcome"]["run_id"]
    await finished(manager, run_id)
    await wait_for(lambda: any(t.startswith("Want") for t in said(wire)))
    before = len(said(wire))
    await session.control({"type": "text", "text": CHANGE})
    await wait_for(lambda: REMINDER in said(wire))
    await asyncio.sleep(0.3)
    assert said(wire)[before:] == [REMINDER] and RESTART_OFFER not in said(wire)
    await session.close()


async def test_a_change_said_while_the_summary_plays_stops_it_and_says_the_reminder(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never", still_working_s=0)
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run_id = wire.of("turn")[0]["outcome"]["run_id"]
    await finished(manager, run_id)
    await wait_for(lambda: bool(said(wire, "answer")))
    assert session.speaking() or session._current is not None or not session._says.empty()
    sent = len(wire.messages)
    await session.control({"type": "text", "text": CHANGE})
    await wait_for(lambda: REMINDER in said(wire))
    await asyncio.sleep(0.3)
    later = wire.messages[sent:]
    kinds = [m.get("type") for m in later if isinstance(m, dict)]
    assert "interrupt" in kinds
    cut = kinds.index("interrupt")
    after = [m["text"] for m in [m for m in later if isinstance(m, dict)][cut:] if m.get("type") == "say"]
    assert after == [REMINDER]
    assert len(cards(manager)) == 1
    await session.close()
