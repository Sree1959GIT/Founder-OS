"""Decision-model layer (PRD F7): fast typed choices ("System 1").

A decision provider picks one of the given options and returns a probability. It never produces free text or
numbers. `DecisionService` wraps a provider: it logs every decision to `data/<ws>/decision_log.jsonl` (the
fine-tuning set for Laya in M3c) and escalates to a fallback provider (the LLM) when the probability is below
`DECISION_MIN_CONFIDENCE`.

Implementations: `LLMDecisionProvider` (JSON-schema output on the local LLM, the default), `FakeDecisionProvider`
(tests), and `laya.LayaProvider` and `jev.JevProvider` (optional, chosen by `DECISION_PROVIDER` after the bake-off).
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from loguru import logger
from pydantic import BaseModel, Field

from app.llm.base import LLMError, Message, Timer
from app.llm.router import LLMRouter


class DecisionError(Exception):
    """No provider could make the decision."""


class Decision(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    question: str
    options: list[str]
    choice: str
    probability: float = Field(ge=0, le=1)
    provider: str
    latency_ms: float = 0.0
    escalated_from: str | None = Field(default=None, description="Provider whose answer was below the confidence")


class DecisionProvider(Protocol):
    name: str

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision: ...


def _validate(options: list[str]) -> None:
    if len(options) < 2 or len(set(options)) != len(options):
        raise DecisionError(f"a decision needs at least two distinct options, got {options}")


class LLMDecisionProvider:
    """The local LLM answers with JSON `{choice, probability}` constrained by a schema (enum of the options)."""

    name = "llm"

    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        _validate(options)
        timer = Timer()
        schema = {
            "type": "object",
            "properties": {
                "choice": {"type": "string", "enum": options},
                "probability": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["choice", "probability"],
        }
        messages = [
            Message.system(
                "You are a fast classifier. Pick exactly one option and say how likely it is to be correct "
                "(probability between 0 and 1). Answer with JSON only."
            ),
            Message.user(
                f"Question: {question}\nOptions: {', '.join(options)}\nContext: {json.dumps(state, default=str)[:3000]}"
            ),
        ]
        try:
            completion = await self._router.complete("local", messages, json_schema=schema)
            data = completion.json()
            choice = str(data["choice"])
            probability = float(data.get("probability", 0.5))
        except (LLMError, KeyError, TypeError, ValueError) as exc:
            raise DecisionError(f"LLM decision failed: {exc}") from exc
        if choice not in options:
            raise DecisionError(f"LLM chose {choice!r}, which is not an option")
        return Decision(
            question=question,
            options=options,
            choice=choice,
            probability=min(max(probability, 0.0), 1.0),
            provider=f"llm:{completion.model}",
            latency_ms=timer.ms,
        )


class FakeDecisionProvider:
    """Deterministic: `rules` maps a substring of the question (or a callable) to the choice; default first option."""

    name = "fake"

    def __init__(
        self,
        rules: dict[str, str] | Callable[[dict[str, Any], str, list[str]], tuple[str, float]] | None = None,
        probability: float = 0.95,
    ) -> None:
        self.rules = rules or {}
        self.probability = probability
        self.calls: list[tuple[str, list[str]]] = []

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        _validate(options)
        self.calls.append((question, options))
        choice, probability = options[0], self.probability
        if callable(self.rules):
            choice, probability = self.rules(state, question, options)
        else:
            for needle, answer in self.rules.items():
                if needle.lower() in question.lower() and answer in options:
                    choice = answer
                    break
        return Decision(question=question, options=options, choice=choice, probability=probability, provider="fake")


class DecisionLog:
    """Append-only JSONL: one line per decision, plus correction lines (`{"correction_for": id, ...}`)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _append(self, record: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:  # logging must never break a decision
            logger.warning("Could not write the decision log {}: {}", self.path, exc)

    def record(self, decision: Decision, state: dict[str, Any], kind: str) -> None:
        self._append(
            {
                "at": datetime.now(UTC).isoformat(),
                "kind": kind,
                "state": state,
                **decision.model_dump(),
                "correction": None,
            }
        )

    def correct(self, decision_id: str, correct_choice: str, note: str = "") -> None:
        self._append(
            {
                "at": datetime.now(UTC).isoformat(),
                "correction_for": decision_id,
                "correct": correct_choice,
                "note": note,
            }
        )

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows


class DecisionService:
    """Choose with the primary provider, escalate below the confidence threshold, log everything."""

    def __init__(
        self,
        provider: DecisionProvider,
        log: DecisionLog | None = None,
        *,
        fallback: DecisionProvider | None = None,
        min_confidence: float = 0.75,
    ) -> None:
        self.provider = provider
        self.fallback = fallback
        self.log = log
        self.min_confidence = min_confidence

    async def choose(
        self, question: str, options: list[str], state: dict[str, Any] | None = None, *, kind: str = "choose"
    ) -> Decision:
        state = state or {}
        try:
            decision = await self.provider.choose(state, question, options)
        except DecisionError:
            if self.fallback is None:
                raise
            decision = await self.fallback.choose(state, question, options)
            decision.escalated_from = self.provider.name
        else:
            if decision.probability < self.min_confidence and self.fallback is not None:
                try:
                    better = await self.fallback.choose(state, question, options)
                    better.escalated_from = decision.provider
                    decision = better
                except DecisionError as exc:
                    logger.info("Decision escalation failed, keeping the low-confidence answer: {}", exc)
        if self.log is not None:
            self.log.record(decision, state, kind)
        return decision

    async def yes_no(self, question: str, state: dict[str, Any] | None = None) -> Decision:
        return await self.choose(question, ["yes", "no"], state, kind="yes_no")

    async def score(self, question: str, options: list[str], state: dict[str, Any] | None = None) -> dict[str, float]:
        """Probability per option: the chosen one gets its probability, the rest share the remainder equally."""
        decision = await self.choose(question, options, state, kind="score")
        rest = (1.0 - decision.probability) / (len(options) - 1)
        return {o: (decision.probability if o == decision.choice else rest) for o in options}
