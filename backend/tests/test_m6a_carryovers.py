"""M6a: the M5 carry-overs from the founder's gate (2026-11-16), reproduced first with `scripts/voice_scenarios.py`.

- X2: "Ok, I will leave as it is." (no "it"), "Leave that as it is.", "Keep as is." keep things as they are.
- X3: a change the answer already has ("Assume two hires." when the office uses two local hires) offers no restart.
- X4: a lone "yes" that Whisper writes as another short word is repaired; "Yes, thank you." is a yes.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.conversation.classifier import is_leave
from app.conversation.manager import LEAVE, change_reminder
from app.voice.domain import corrected
from tests.test_voice_round2 import lane
from tests.test_voice_round8 import answered, finance  # noqa: F401  (the fixture)

ALREADY = "That's already in this answer: it assumes two local hires. Nothing to restart."


# --- X2 -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "said",
    [
        "Ok, I will leave as it is.",
        "Leave that as it is.",
        "Keep as is.",
        "I will leave this as it is.",
        "Leave it like it is.",
        "Let it be.",
        "Leave as is.",
    ],
)
def test_more_leave_phrases(said: str) -> None:
    assert is_leave(said)


@pytest.mark.parametrize("said", ["keep going", "Keep it going.", "Leave the Dubai office as it is.", "keep", "leave"])
def test_still_not_leave_phrases(said: str) -> None:
    assert not is_leave(said)


async def test_leave_as_it_is_after_an_answer(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    out = await manager.turn(first.session_id, "Ok, I will leave as it is.")
    assert out.reply == LEAVE and not out.started_run


# --- X3 -------------------------------------------------------------------------------------------------------------
async def test_a_change_already_in_the_answer_offers_no_restart(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    same = await manager.turn(first.session_id, "Assume two hires.")
    assert same.reply == ALREADY and not same.started_run and same.amendment_id is None
    assert manager.state(first.session_id)["amendments"] == []
    real = await manager.turn(first.session_id, "Assume three hires.")  # a real change still gets its reminder
    assert real.reply == change_reminder("Assume three hires.") and real.amendment_id


async def test_after_a_restart_the_founders_number_is_already_in(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    await manager.turn(first.session_id, "Assume three hires.")
    yes = await manager.turn(first.session_id, "yes")
    assert yes.started_run
    from tests.test_voice_round2 import finished

    await finished(manager, yes.run_id)
    again = await manager.turn(first.session_id, "Assume three hires.")
    assert again.reply == "That's already in this answer: it assumes three local hires. Nothing to restart."
    assert not again.started_run


# --- X4 -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("heard", ["Yas.", "Yess!", "Yesh.", "Jess.", "Yah.", "Yea.", "Yeh?", "Ya.", "Yaffen."])
def test_a_misheard_lone_yes_is_repaired(heard: str) -> None:
    assert corrected(heard) == "Yes."


@pytest.mark.parametrize("heard", ["Yes?", "Yes.", "Jess said no.", "Yeah.", "Yesterday.", "Ya know what, stop."])
def test_other_words_are_left_alone(heard: str) -> None:
    assert corrected(heard) == heard


@pytest.mark.parametrize("said", ["Yes, thank you.", "Yes sir.", "Yes, thanks."])
async def test_yes_with_thanks_answers_the_offer(finance: Any, said: str) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    out = await manager.turn(first.session_id, said)
    assert not out.started_run and out.reply and "did you say" not in out.reply.lower()
