from __future__ import annotations

from pathlib import Path

import pytest

from app.decision.base import (
    DecisionError,
    DecisionLog,
    DecisionService,
    FakeDecisionProvider,
    LLMDecisionProvider,
)
from app.llm.base import LLMUnavailable
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter


async def test_llm_decision_uses_an_enum_schema() -> None:
    fake = FakeProvider(['{"choice": "finance", "probability": 0.9}'])
    decision = await LLMDecisionProvider(LLMRouter(fake)).choose(
        {"message": "runway?"}, "intent?", ["finance", "chitchat"]
    )
    assert decision.choice == "finance" and decision.probability == 0.9 and decision.provider == "llm:fake-model"
    schema = fake.calls[0]["json_schema"]
    assert schema["properties"]["choice"]["enum"] == ["finance", "chitchat"]


@pytest.mark.parametrize(
    "reply",
    ['{"choice": "banana", "probability": 0.9}', "not json", LLMUnavailable("ollama down"), '{"probability": 1}'],
)
async def test_llm_decision_failures_raise_decision_error(reply: object) -> None:
    provider = LLMDecisionProvider(LLMRouter(FakeProvider([reply])))  # type: ignore[list-item]
    with pytest.raises(DecisionError):
        await provider.choose({}, "q", ["a", "b"])


async def test_options_are_validated() -> None:
    with pytest.raises(DecisionError):
        await FakeDecisionProvider().choose({}, "q", ["only"])
    with pytest.raises(DecisionError):
        await FakeDecisionProvider().choose({}, "q", ["a", "a"])


async def test_service_logs_and_escalates_low_confidence(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "ws" / "decision_log.jsonl")
    primary = FakeDecisionProvider({"runway": "finance"}, probability=0.4)
    fallback = FakeDecisionProvider({"runway": "knowledge"}, probability=0.9)
    service = DecisionService(primary, log, fallback=fallback, min_confidence=0.75)
    decision = await service.choose("about runway", ["finance", "knowledge"], {"m": 1}, kind="intent")
    assert decision.choice == "knowledge" and decision.escalated_from == "fake"
    confident = DecisionService(FakeDecisionProvider(probability=0.8), log, fallback=fallback)
    assert (await confident.choose("x", ["a", "b"])).escalated_from is None
    rows = log.read()
    assert (
        len(rows) == 2
        and rows[0]["kind"] == "intent"
        and rows[0]["state"] == {"m": 1}
        and rows[0]["correction"] is None
    )
    log.correct(rows[0]["id"], "finance", "founder fixed it")
    assert log.read()[-1] == {**log.read()[-1], "correction_for": rows[0]["id"], "correct": "finance"}


async def test_service_falls_back_when_primary_fails(tmp_path: Path) -> None:
    broken = LLMDecisionProvider(LLMRouter(FakeProvider([LLMUnavailable("down")])))
    service = DecisionService(broken, None, fallback=FakeDecisionProvider())
    decision = await service.choose("q", ["a", "b"])
    assert decision.choice == "a" and decision.escalated_from == "llm"
    with pytest.raises(DecisionError):
        await DecisionService(LLMDecisionProvider(LLMRouter(FakeProvider([LLMUnavailable("d")])))).choose(
            "q", ["a", "b"]
        )


async def test_yes_no_and_score() -> None:
    service = DecisionService(FakeDecisionProvider({"one-way": "no"}, probability=0.8))
    assert (await service.yes_no("Is this a one-way door?")).choice == "no"
    scores = await service.score("which?", ["a", "b", "c"])
    assert scores == pytest.approx({"a": 0.8, "b": 0.1, "c": 0.1})


def test_log_survives_unwritable_path(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    log = DecisionLog(blocker / "decision_log.jsonl")  # parent is a file: cannot be created
    from app.decision.base import Decision

    log.record(Decision(question="q", options=["a", "b"], choice="a", probability=1, provider="fake"), {}, "choose")
    assert log.read() == []
