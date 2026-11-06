"""Bake-off of decision providers (PRD F7): accuracy, calibration and latency on ~200 labelled routing examples.

Three kinds of decision: `intent` (what the Planner does first), `team` (the specialist a question most needs) and
`turn` (what a turn means while a run works). Each provider sees the question and options the app really asks.
Examples carry a stable `split`: `train` for fine-tuning, `test` held out for this table.

Calibration is the expected calibration error (ECE, 10 bins) and the Brier score. A model's confidence is only useful
for the fallback if it means something: Laya's own docs warn its scores can be rankings, not probabilities.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.runtime import INTENT_OPTIONS, INTENT_QUESTION, rule_intent
from app.agents.specialists import team_for_message
from app.conversation.classifier import KINDS, TURN_QUESTION, by_rules
from app.decision.base import Decision, DecisionError, DecisionProvider

EXAMPLES_PATH = Path(__file__).with_name("routing_examples.json")
TEAM_OPTIONS = [
    "financial_analyst",
    "librarian",
    "market_scout",
    "revenue_customer",
    "people_ops",
    "regulatory_tax",
    "prioritiser",
    "perspective_lens",
    "devils_advocate",
]
TEAM_QUESTION = (
    "Which specialist does this founder's question need most? financial_analyst: metrics, scenarios and runway. "
    "librarian: the founder's notes and past decisions. market_scout: market size, competitors, local conditions. "
    "revenue_customer: pricing, churn, pipeline and segments. people_ops: hiring plan, capacity, ownership, execution. "
    "regulatory_tax: licences, tax and compliance. prioritiser: ranking options. perspective_lens: one outside "
    "viewpoint. devils_advocate: pre-mortem and what could go wrong."
)
QUESTIONS: dict[str, tuple[str, list[str]]] = {
    "intent": (INTENT_QUESTION, INTENT_OPTIONS),
    "team": (TEAM_QUESTION, TEAM_OPTIONS),
    "turn": (TURN_QUESTION, KINDS),
}
RUNNING = "Should we open a Dubai office?"


@dataclass(frozen=True)
class RoutingExample:
    kind: str
    text: str
    label: str
    split: str = "test"

    def state(self) -> dict[str, str]:
        return {"turn": self.text, "running": RUNNING} if self.kind == "turn" else {"message": self.text}


def load_examples(path: Path = EXAMPLES_PATH, split: str | None = None) -> list[RoutingExample]:
    rows = [RoutingExample(**r) for r in json.loads(path.read_text(encoding="utf-8"))]
    return [r for r in rows if split is None or r.split == split]


class RulesProvider:
    """Today's routing rules, as a baseline. They abstain (probability 0) where the app would ask a model."""

    name = "rules"

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        text = state.get("message") or state.get("turn") or ""
        if question == INTENT_QUESTION:
            choice: str | None = rule_intent(text)
        elif question == TURN_QUESTION:
            choice = by_rules(text)
        else:
            wanted = team_for_message(text)
            choice = wanted[0] if wanted else None
        known = choice in options
        return Decision(
            question=question,
            options=options,
            choice=choice if known else options[0],  # type: ignore[arg-type]
            probability=1.0 if known else 0.0,
            provider="rules",
        )


@dataclass
class Prediction:
    example: RoutingExample
    choice: str | None
    probability: float
    latency_ms: float
    error: str = ""

    @property
    def correct(self) -> bool:
        return self.choice == self.example.label


@dataclass
class BakeoffRow:
    provider: str
    kind: str
    predictions: list[Prediction] = field(default_factory=list)
    min_confidence: float = 0.75

    @property
    def n(self) -> int:
        return len(self.predictions)

    @property
    def errors(self) -> int:
        return sum(1 for p in self.predictions if p.error)

    @property
    def accuracy(self) -> float:
        return sum(p.correct for p in self.predictions) / self.n if self.n else 0.0

    @property
    def confident(self) -> list[Prediction]:
        return [p for p in self.predictions if p.probability >= self.min_confidence]

    @property
    def coverage(self) -> float:
        """The share it answers without falling back."""
        return len(self.confident) / self.n if self.n else 0.0

    @property
    def confident_accuracy(self) -> float:
        rows = self.confident
        return sum(p.correct for p in rows) / len(rows) if rows else 0.0

    @property
    def ece(self) -> float:
        return expected_calibration_error(self.predictions)

    @property
    def brier(self) -> float:
        rows = [(p.probability - (1.0 if p.correct else 0.0)) ** 2 for p in self.predictions]
        return statistics.fmean(rows) if rows else 0.0

    @property
    def p50_ms(self) -> float:
        return _percentile([p.latency_ms for p in self.predictions], 0.5)

    @property
    def p95_ms(self) -> float:
        return _percentile([p.latency_ms for p in self.predictions], 0.95)

    def cells(self) -> list[str]:
        return [
            self.provider,
            self.kind,
            str(self.n),
            f"{self.accuracy:.1%}",
            f"{self.coverage:.0%}",
            f"{self.confident_accuracy:.1%}",
            f"{self.ece:.3f}",
            f"{self.brier:.3f}",
            f"{self.p50_ms:.0f}",
            f"{self.p95_ms:.0f}",
            str(self.errors),
        ]


HEADERS = [
    "provider",
    "kind",
    "n",
    "accuracy",
    "answers",
    "acc. when answering",
    "ECE",
    "Brier",
    "p50 ms",
    "p95 ms",
    "err",
]


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(int(q * len(ordered)), len(ordered) - 1)]


def expected_calibration_error(predictions: Sequence[Prediction], bins: int = 10) -> float:
    if not predictions:
        return 0.0
    total = 0.0
    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        rows = [p for p in predictions if low <= p.probability < high or (b == bins - 1 and p.probability == 1.0)]
        if rows:
            confidence = statistics.fmean(p.probability for p in rows)
            accuracy = statistics.fmean(1.0 if p.correct else 0.0 for p in rows)
            total += len(rows) / len(predictions) * abs(confidence - accuracy)
    return total


async def predict(provider: DecisionProvider, example: RoutingExample) -> Prediction:
    question, options = QUESTIONS[example.kind]
    started = time.perf_counter()
    try:
        decision = await provider.choose(example.state(), question, list(options))
    except DecisionError as exc:
        return Prediction(example, None, 0.0, (time.perf_counter() - started) * 1000, str(exc))
    return Prediction(example, decision.choice, decision.probability, (time.perf_counter() - started) * 1000)


async def run_bakeoff(
    providers: dict[str, DecisionProvider],
    examples: list[RoutingExample],
    *,
    min_confidence: float = 0.75,
    on_row: Any = None,
) -> list[BakeoffRow]:
    rows: list[BakeoffRow] = []
    for name, provider in providers.items():
        for kind in QUESTIONS:
            row = BakeoffRow(name, kind, min_confidence=min_confidence)
            for example in examples:
                if example.kind == kind:
                    row.predictions.append(await predict(provider, example))
            if row.n:
                rows.append(row)
                if on_row is not None:
                    on_row(row)
    return rows


class CascadeProvider:
    """The real setup: the primary model, then the LLM below the confidence threshold (PRD F7)."""

    def __init__(self, primary: DecisionProvider, fallback: DecisionProvider, min_confidence: float = 0.75) -> None:
        self.primary, self.fallback, self.min_confidence = primary, fallback, min_confidence
        self.name = f"{primary.name}+{fallback.name}"

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        try:
            decision = await self.primary.choose(state, question, options)
        except DecisionError:
            return await self.fallback.choose(state, question, options)
        if decision.probability >= self.min_confidence:
            return decision
        return await self.fallback.choose(state, question, options)


def table(headers: list[str], rows: list[list[str]]) -> str:
    """A plain aligned table, readable in PowerShell 5.1."""
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))]
    lines.append("  ".join("-" * w for w in widths))
    lines += ["  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)) for r in rows]
    return "\n".join(lines)


def recommend(rows: list[BakeoffRow], baseline: str = "llm", min_gain: float = 0.05) -> str:
    """A reading of the table for the founder. Nothing changes without their approval."""

    def overall(name: str) -> tuple[float, float] | None:
        mine = [p for r in rows if r.provider == name for p in r.predictions]
        if not mine or all(p.error for p in mine):
            return None
        return sum(p.correct for p in mine) / len(mine), _percentile([p.latency_ms for p in mine], 0.5)

    names = list(dict.fromkeys(r.provider for r in rows))
    scored = {n: overall(n) for n in names}
    llm = next((n for n in names if n.startswith(baseline)), None)
    best = max((n for n in names if scored[n]), key=lambda n: scored[n][0], default=None)  # type: ignore[index]
    if best is None:
        return "No provider answered."
    if llm is None or scored[llm] is None or best == llm:
        return f"Best measured: {best} at {scored[best][0]:.1%}. Keep the current default unless it says otherwise."  # type: ignore[index]
    gain = scored[best][0] - scored[llm][0]  # type: ignore[index]
    if gain >= min_gain:
        return f"{best} beats {llm} by {gain:.1%}. Proposal: consider it as the default; your call."
    return (
        f"{best} does not beat {llm} by {min_gain:.0%} on this set ({gain:+.1%}). Proposal: keep {llm} as the default."
    )
