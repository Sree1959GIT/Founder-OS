"""M7b founder gate (2026-11-26/27), F27: stopping a voice only stops the talking.

The Stop button under the speaking face (and Esc) sends `hush`: queued lines and the audio being made go, the state
returns to listening/idle, and the running team, its research and its numbers carry on. Ending the voice socket
("Voice off") never cancels a team either.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from tests.test_specialists import slow_provider
from tests.test_voice import make
from tests.test_voice_round2 import wait_for


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


async def _working_team(finance: Any) -> tuple[Any, Any, Any, Any, str]:
    provider = slow_provider()
    session, wire, _stt, _tts, manager = make(finance, [], provider=provider, approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": "Should we expand the team this year?"})
    await wait_for(lambda: bool(wire.of("turn")))
    run_id = wire.of("turn")[0]["outcome"]["run_id"]
    await wait_for(lambda: bool(provider.briefs))  # the team is at work
    return provider, session, wire, manager, run_id


async def test_hush_stops_the_speech_and_never_the_team(finance: Any) -> None:
    provider, session, wire, manager, run_id = await _working_team(finance)
    run = manager.orchestrator.runs[run_id]
    await session.control({"type": "hush"})
    await wait_for(lambda: any(m.get("reason") == "hush" for m in wire.of("interrupt")))
    assert wire.of("state")[-1]["state"] == "idle"  # push-to-talk: back to waiting for the member
    assert not run.task.done() and not run.cancel_requested
    assert not any(m["text"] == "That run was cancelled." for m in wire.of("say"))
    provider.release.set()
    result = await run.task
    assert result.status == "done"  # research and numbers carried on to the end
    await session.close()


async def test_ending_the_voice_never_cancels_a_running_team(finance: Any) -> None:
    provider, session, _wire, manager, run_id = await _working_team(finance)
    run = manager.orchestrator.runs[run_id]
    await session.close()  # "Voice off" in the LIVE bar, or the socket dropping
    assert not run.task.done() and not run.cancel_requested
    provider.release.set()
    result = await run.task
    assert result.status == "done"
