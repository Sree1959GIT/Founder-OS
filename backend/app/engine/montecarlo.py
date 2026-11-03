"""Monte Carlo over the scenario drivers (PRD §F1): P10/P50/P90 cash paths, runway range, P(cash < 0).

Each run draws every uncertain adjustment from its distribution (seeded NumPy generator, so the same request always
gives the same answer) and pushes all runs through the same vectorised recurrence as the scenario engine.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator

from app.engine.lineage import Lineage, Number
from app.engine.metrics import MetricError, shift_month
from app.engine.scenario import (
    ADJUSTMENT_FIELDS,
    DEFAULT_HORIZON,
    MAX_HORIZON,
    RUNWAY_SEARCH_MONTHS,
    Adjustments,
    ScenarioEngine,
    adjustment_arrays,
    project,
    runway_months,
)

MAX_RUNS = 20_000


class Distribution(BaseModel):
    """`normal(mean, sd)`, `uniform(low, high)` or `triangular(low, mode, high)` on one adjustment (its units)."""

    kind: Literal["normal", "uniform", "triangular"]
    mean: float | None = None
    sd: float | None = Field(None, ge=0)
    low: float | None = None
    mode: float | None = None
    high: float | None = None

    @model_validator(mode="after")
    def _check(self) -> Distribution:
        if self.kind == "normal" and (self.mean is None or self.sd is None):
            raise ValueError("normal needs mean and sd")
        if self.kind == "uniform" and (self.low is None or self.high is None or self.low > self.high):
            raise ValueError("uniform needs low <= high")
        if self.kind == "triangular" and (
            self.low is None
            or self.mode is None
            or self.high is None
            or not self.low <= self.mode <= self.high
            or self.low == self.high
        ):
            raise ValueError("triangular needs low <= mode <= high and low < high")
        return self

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        if self.kind == "normal":
            return rng.normal(self.mean, self.sd, n)
        if self.kind == "uniform":
            return rng.uniform(self.low, self.high, n)
        return rng.triangular(self.low, self.mode, self.high, n)


def default_distributions() -> dict[str, Distribution]:
    """Plausible uncertainty around "no change" for an early-stage SaaS business."""
    return {
        "churn_change_pts": Distribution(kind="normal", mean=0.0, sd=0.5),
        "cac_change_pct": Distribution(kind="normal", mean=0.0, sd=15.0),
        "acquisition_change_pct": Distribution(kind="normal", mean=0.0, sd=20.0),
        "price_change_pct": Distribution(kind="normal", mean=0.0, sd=2.0),
    }


class MonteCarloRequest(BaseModel):
    adjustments: Adjustments = Field(default_factory=Adjustments, description="Fixed part of the scenario")
    distributions: dict[str, Distribution] = Field(default_factory=default_distributions)
    runs: int = Field(1000, ge=10, le=MAX_RUNS)
    seed: int = 42
    horizon: int = Field(DEFAULT_HORIZON, ge=1, le=MAX_HORIZON)
    as_of: str | None = None


class FanPoint(BaseModel):
    month: str
    p10: Number
    p50: Number
    p90: Number


class MonteCarloResult(BaseModel):
    as_of: str
    currency: str
    runs: int
    seed: int
    points: list[FanPoint]
    runway_p10: Number | None = Field(description="Months; None = cash never runs out within the search window")
    runway_p50: Number | None
    runway_p90: Number | None
    probability_cash_out_within_horizon: Number
    probability_cash_out_within_12_months: Number
    elapsed_ms: float
    lineage: Lineage


def run_monte_carlo(engine: ScenarioEngine, request: MonteCarloRequest) -> MonteCarloResult:
    unknown = set(request.distributions) - set(ADJUSTMENT_FIELDS)
    if unknown:
        raise MetricError(
            f"unknown variable(s) {', '.join(sorted(unknown))}; choose from {', '.join(ADJUSTMENT_FIELDS)}"
        )
    started = time.perf_counter()
    d, t = engine.drivers(request.as_of)
    rng = np.random.default_rng(request.seed)
    n = request.runs
    overrides = {}
    for name in sorted(request.distributions):  # sorted: the draw order (and so the result) is stable
        fixed = float(getattr(request.adjustments, name))
        overrides[name] = fixed + request.distributions[name].sample(rng, n)
    # Keep draws inside the physically meaningful range (e.g. CAC cannot fall by more than 90%).
    for name, (low, high) in _BOUNDS.items():
        if name in overrides:
            overrides[name] = np.clip(overrides[name], low, high)
    arrays = adjustment_arrays(n, request.adjustments, overrides)
    months = max(request.horizon, RUNWAY_SEARCH_MONTHS)
    cash, _ = project(d, arrays, request.adjustments.start_month, months, request.adjustments.cost_per_hire_monthly)
    p10, p50, p90 = np.percentile(cash[:, : request.horizon], [10, 50, 90], axis=0)
    runway = runway_months(d.cash, cash)
    # "Never runs out" (NaN) becomes a sentinel past the search window, which `_months` maps back to None.
    never = float(months + 1)
    r10, r50, r90 = np.percentile(np.where(np.isnan(runway), never, runway), [10, 50, 90])
    within = (cash[:, : request.horizon] < 0).any(axis=1).mean()
    within_12 = (cash[:, :12] < 0).any(axis=1).mean()
    lineage = engine._lineage(
        "monte_carlo",
        d,
        t,
        f"{n} seeded runs (seed {request.seed}) of the scenario recurrence; distributions on "
        f"{', '.join(sorted(request.distributions)) or 'nothing'}; percentiles per month",
    )
    return MonteCarloResult(
        as_of=d.as_of,
        currency=engine.currency,
        runs=n,
        seed=request.seed,
        points=[
            FanPoint(month=shift_month(d.as_of, k + 1), p10=_money(p10[k]), p50=_money(p50[k]), p90=_money(p90[k]))
            for k in range(request.horizon)
        ],
        runway_p10=_months(r10, never),
        runway_p50=_months(r50, never),
        runway_p90=_months(r90, never),
        probability_cash_out_within_horizon=Decimal(str(round(float(within), 4))),
        probability_cash_out_within_12_months=Decimal(str(round(float(within_12), 4))),
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        lineage=lineage,
    )


_SCHEMA = Adjustments.model_json_schema()["properties"]
_BOUNDS = {
    name: (float(_SCHEMA[name].get("minimum", -np.inf)), float(_SCHEMA[name].get("maximum", np.inf)))
    for name in ADJUSTMENT_FIELDS
}


def _money(value: float) -> Decimal:
    return Decimal(str(round(float(value), 2)))


def _months(value: float, never: float) -> Decimal | None:
    return None if value > never - 1 else Decimal(str(round(float(value), 2)))
