"""M6b: a re-run with a change already in the answer (HANDOVER next step 4) and the Kokoro engine choice."""

from __future__ import annotations

from typing import Any

from tests.test_voice_round2 import finished, lane
from tests.test_voice_round8 import answered, finance  # noqa: F401  (the fixture)


async def test_rerun_with_a_change_already_in_the_answer_reruns_only_that_agent(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    old = manager.orchestrator.runs[first.run_id or ""]
    again = await manager.turn(first.session_id, "Re-run the analyst, assume two hires.")
    assert again.started_run and again.run_id != first.run_id
    assert again.reply == (
        "That's already in this answer: it assumes two local hires. "
        "Re-running only the Financial Analyst again. The rest of the team's findings stand."
    )
    new_run = manager.orchestrator.runs[again.run_id or ""]
    assert new_run.message == old.message  # no change added to the request: the same decision
    new = await finished(manager, again.run_id)
    analyst = next(a for a in new.team if a.type == "financial_analyst")
    assert "The founder then added" not in analyst.brief


async def test_rerun_with_a_real_change_still_runs_the_whole_team(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    again = await manager.turn(first.session_id, "Re-run the analyst, assume three hires.")
    assert again.reply.startswith("That changes the decision, so the whole team runs again with it")
    await finished(manager, again.run_id)
