"""`/api/metrics/*`: the pre-built metric routines, each answer with its lineage."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.deps import FinanceDep
from app.engine.decision_science import KillCheck, KillCriterion, evaluate_kill_criteria
from app.engine.lineage import MetricResult
from app.engine.metrics import METRICS, SUMMARY_METRICS
from app.engine.scenario import DEFAULT_HORIZON, MAX_HORIZON, Adjustments, ScenarioResult

router = APIRouter(prefix="/metrics", tags=["metrics"])

MonthQuery = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="As-of month YYYY-MM (default: latest)")


class MetricInfo(BaseModel):
    name: str
    label: str
    default_window: int | None
    description: str


class MetricsIndex(BaseModel):
    metrics: list[MetricInfo]
    months: list[str]


class KillCriteriaRequest(BaseModel):
    criteria: list[KillCriterion] = Field(min_length=1, max_length=50)
    month: str | None = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("", response_model=MetricsIndex)
def index(finance: FinanceDep) -> MetricsIndex:
    return MetricsIndex(
        metrics=[MetricInfo(**d.__dict__) for d in METRICS.values()],
        months=finance.metrics.available_months(),
    )


@router.get("/summary", response_model=list[MetricResult])
def summary(finance: FinanceDep, month: str | None = MonthQuery) -> list[MetricResult]:
    """The headline numbers for the dashboard, computed on one connection."""
    return finance.metrics.compute_many(list(SUMMARY_METRICS), month)


@router.get("/cash-projection", response_model=ScenarioResult)
def cash_projection(
    finance: FinanceDep,
    month: str | None = MonthQuery,
    horizon: int = Query(DEFAULT_HORIZON, ge=1, le=MAX_HORIZON),
) -> ScenarioResult:
    """The base-case cash-flow projection (no adjustments): `points[].base_cash`, runway and zero-cash month."""
    return finance.scenario.run(Adjustments(), month, horizon)


@router.post("/kill-criteria", response_model=list[KillCheck])
def kill_criteria(body: KillCriteriaRequest, finance: FinanceDep) -> list[KillCheck]:
    return evaluate_kill_criteria(finance.metrics, body.criteria, body.month)


@router.get("/{name}", response_model=MetricResult)
def metric(
    name: str,
    finance: FinanceDep,
    month: str | None = MonthQuery,
    window: int | None = Query(None, ge=1, le=36, description="Trailing months (default per metric)"),
) -> MetricResult:
    return finance.metrics.compute(name, month, window)
