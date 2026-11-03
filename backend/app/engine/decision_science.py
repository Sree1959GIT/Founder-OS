"""Decision-science routines (PRD §F1). Deterministic code; the LLM only elicits the inputs from the founder.

- Weighted scoring / MCDA with a 2x2 priority matrix (bottom-line value x execution feasibility).
- Expected value over discrete outcomes.
- Decision trees (decision, chance and terminal nodes) rolled back to the best policy, e.g. "pilot first" options.
- Kill criteria evaluated against live metric routines (with their lineage).
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.engine.lineage import Lineage
from app.engine.metrics import METRICS, MetricsEngine

PROBABILITY_TOLERANCE = 1e-6


# --- weighted scoring / MCDA -----------------------------------------------------------------------------------
class Criterion(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    weight: float = Field(gt=0)
    direction: Literal["benefit", "cost"] = "benefit"  # "cost": a higher score is worse (e.g. effort)
    axis: Literal["value", "feasibility"] | None = None  # which matrix axis this criterion feeds


class ScoredOption(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scores: dict[str, float]
    cost: float | None = Field(None, ge=0, description="Optional size of the bubble (e.g. investment)")


class ScoringRequest(BaseModel):
    criteria: list[Criterion] = Field(min_length=1, max_length=20)
    options: list[ScoredOption] = Field(min_length=1, max_length=50)
    scale_min: float = 1
    scale_max: float = 5

    @model_validator(mode="after")
    def _check(self) -> ScoringRequest:
        if self.scale_max <= self.scale_min:
            raise ValueError("scale_max must be greater than scale_min")
        names = [c.name for c in self.criteria]
        if len(set(names)) != len(names):
            raise ValueError("criterion names must be unique")
        for option in self.options:
            missing = set(names) - set(option.scores)
            extra = set(option.scores) - set(names)
            if missing or extra:
                raise ValueError(f"{option.name}: scores must cover exactly the criteria ({', '.join(names)})")
            for criterion, score in option.scores.items():
                if not self.scale_min <= score <= self.scale_max:
                    raise ValueError(
                        f"{option.name}/{criterion}: score {score} outside {self.scale_min}..{self.scale_max}"
                    )
        return self


class OptionScore(BaseModel):
    name: str
    total: float = Field(description="Weighted score normalised to 0..1")
    rank: int
    value: float | None = Field(description="Value-axis score 0..1 (None if no criterion feeds it)")
    feasibility: float | None
    quadrant: str | None
    cost: float | None
    contributions: dict[str, float]


class ScoringResult(BaseModel):
    weights: dict[str, float] = Field(description="Normalised weights (sum to 1)")
    options: list[OptionScore]
    formula: str


QUADRANTS = {
    (True, True): "Quick win",
    (True, False): "Big bet",
    (False, True): "Fill-in",
    (False, False): "Deprioritise",
}


def weighted_scoring(request: ScoringRequest) -> ScoringResult:
    total_weight = sum(c.weight for c in request.criteria)
    weights = {c.name: c.weight / total_weight for c in request.criteria}
    span = request.scale_max - request.scale_min

    def normalised(c: Criterion, score: float) -> float:
        x = (score - request.scale_min) / span
        return 1 - x if c.direction == "cost" else x

    rows: list[OptionScore] = []
    for option in request.options:
        contributions = {c.name: weights[c.name] * normalised(c, option.scores[c.name]) for c in request.criteria}
        axes: dict[str, float | None] = {}
        for axis in ("value", "feasibility"):
            members = [c for c in request.criteria if c.axis == axis]
            if not members:
                axes[axis] = None
                continue
            w = sum(c.weight for c in members)
            axes[axis] = round(sum(c.weight * normalised(c, option.scores[c.name]) for c in members) / w, 4)
        value, feasibility = axes["value"], axes["feasibility"]
        quadrant = None if value is None or feasibility is None else QUADRANTS[(value >= 0.5, feasibility >= 0.5)]
        rows.append(
            OptionScore(
                name=option.name,
                total=round(sum(contributions.values()), 4),
                rank=0,
                value=value,
                feasibility=feasibility,
                quadrant=quadrant,
                cost=option.cost,
                contributions={k: round(v, 4) for k, v in contributions.items()},
            )
        )
    rows.sort(key=lambda r: (-r.total, r.name))
    for i, row in enumerate(rows, start=1):
        row.rank = i
    return ScoringResult(
        weights={k: round(v, 4) for k, v in weights.items()},
        options=rows,
        formula="total = sum(weight_c x normalised score_c); normalised = (s - min) / (max - min), inverted for cost "
        "criteria; axes use only their own criteria; quadrant threshold 0.5",
    )


# --- expected value --------------------------------------------------------------------------------------------
class Outcome(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    probability: float = Field(ge=0, le=1)
    value: float


class EVOption(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    outcomes: list[Outcome] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _probabilities_sum_to_one(self) -> EVOption:
        total = sum(o.probability for o in self.outcomes)
        if abs(total - 1) > PROBABILITY_TOLERANCE:
            raise ValueError(f"{self.name}: outcome probabilities sum to {total:.6g}, not 1")
        return self


class EVResult(BaseModel):
    name: str
    expected_value: float
    std_dev: float
    worst: float
    best: float
    probability_of_loss: float


def expected_values(options: list[EVOption]) -> list[EVResult]:
    results = []
    for option in options:
        ev = sum(o.probability * o.value for o in option.outcomes)
        variance = sum(o.probability * (o.value - ev) ** 2 for o in option.outcomes)
        results.append(
            EVResult(
                name=option.name,
                expected_value=round(ev, 2),
                std_dev=round(math.sqrt(variance), 2),
                worst=min(o.value for o in option.outcomes),
                best=max(o.value for o in option.outcomes),
                probability_of_loss=round(sum(o.probability for o in option.outcomes if o.value < 0), 6),
            )
        )
    return sorted(results, key=lambda r: (-r.expected_value, r.name))


# --- decision trees --------------------------------------------------------------------------------------------
class TerminalNode(BaseModel):
    type: Literal["terminal"] = "terminal"
    name: str = ""
    value: float


class ChanceBranch(BaseModel):
    label: str
    probability: float = Field(ge=0, le=1)
    node: TreeNode


class ChanceNode(BaseModel):
    type: Literal["chance"] = "chance"
    name: str = ""
    branches: list[ChanceBranch] = Field(min_length=1)

    @model_validator(mode="after")
    def _probabilities_sum_to_one(self) -> ChanceNode:
        total = sum(b.probability for b in self.branches)
        if abs(total - 1) > PROBABILITY_TOLERANCE:
            raise ValueError(f"chance node {self.name!r}: probabilities sum to {total:.6g}, not 1")
        return self


class DecisionChoice(BaseModel):
    label: str
    cost: float = Field(0, description="Cost of taking this choice, subtracted from its value")
    node: TreeNode


class DecisionNode(BaseModel):
    type: Literal["decision"] = "decision"
    name: str = ""
    choices: list[DecisionChoice] = Field(min_length=1)


TreeNode = Annotated[TerminalNode | ChanceNode | DecisionNode, Field(discriminator="type")]
ChanceBranch.model_rebuild()
DecisionChoice.model_rebuild()

MAX_TREE_NODES = 2000


class TreeResult(BaseModel):
    expected_value: float
    policy: dict[str, str] = Field(description="decision node path -> best choice")
    choice_values: dict[str, dict[str, float]] = Field(description="decision node path -> value of each choice")


def solve_decision_tree(root: TerminalNode | ChanceNode | DecisionNode) -> TreeResult:
    """Roll back the tree: chance nodes take the probability-weighted mean, decisions the best net value."""
    policy: dict[str, str] = {}
    choice_values: dict[str, dict[str, float]] = {}
    count = 0

    def rollback(node: TerminalNode | ChanceNode | DecisionNode, path: str) -> float:
        nonlocal count
        count += 1
        if count > MAX_TREE_NODES:
            raise ValueError(f"decision tree has more than {MAX_TREE_NODES} nodes")
        if isinstance(node, TerminalNode):
            return node.value
        if isinstance(node, ChanceNode):
            return sum(b.probability * rollback(b.node, f"{path}/{b.label}") for b in node.branches)
        values = {c.label: rollback(c.node, f"{path}/{c.label}") - c.cost for c in node.choices}
        best = max(values, key=lambda k: (values[k], -list(values).index(k)))
        key = path or "/"
        policy[key] = best
        choice_values[key] = {k: round(v, 2) for k, v in values.items()}
        return values[best]

    ev = rollback(root, "")
    return TreeResult(expected_value=round(ev, 2), policy=policy, choice_values=choice_values)


# --- kill criteria ---------------------------------------------------------------------------------------------
OPERATORS = {"<": float.__lt__, "<=": float.__le__, ">": float.__gt__, ">=": float.__ge__}


class KillCriterion(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    metric: str
    operator: Literal["<", "<=", ">", ">="]
    threshold: float
    window: int | None = Field(None, ge=1, le=36)

    @model_validator(mode="after")
    def _known_metric(self) -> KillCriterion:
        if self.metric not in METRICS:
            raise ValueError(f"unknown metric {self.metric!r}")
        return self


class KillCheck(BaseModel):
    name: str
    metric: str
    condition: str
    value: float | None
    triggered: bool | None = Field(description="None when the metric is undefined (e.g. runway while cash-positive)")
    lineage: Lineage


def evaluate_kill_criteria(
    metrics: MetricsEngine, criteria: list[KillCriterion], month: str | None = None
) -> list[KillCheck]:
    checks = []
    for criterion in criteria:
        result = metrics.compute(criterion.metric, month, criterion.window)
        value = None if result.value is None else float(result.value)
        triggered = None if value is None else OPERATORS[criterion.operator](value, float(criterion.threshold))
        checks.append(
            KillCheck(
                name=criterion.name,
                metric=criterion.metric,
                condition=f"{criterion.metric} {criterion.operator} {criterion.threshold:g}",
                value=value,
                triggered=triggered,
                lineage=result.lineage,
            )
        )
    return checks
