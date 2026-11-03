"""`/api/scenario*`: what-if projection (slider path), sensitivity grid and Monte Carlo."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.deps import FinanceDep
from app.engine.montecarlo import MonteCarloRequest, MonteCarloResult, run_monte_carlo
from app.engine.scenario import DEFAULT_HORIZON, MAX_HORIZON, Adjustments, ScenarioResult, SensitivityResult

router = APIRouter(prefix="/scenario", tags=["scenario"])

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class ScenarioRequest(Adjustments):
    """The adjustments, flat (one field per slider), plus the as-of month and horizon."""

    as_of: str | None = Field(None, pattern=MONTH_PATTERN)
    horizon: int = Field(DEFAULT_HORIZON, ge=1, le=MAX_HORIZON)


class SensitivityRequest(BaseModel):
    row_variable: str = "price_change_pct"
    row_values: list[float] = Field(default_factory=lambda: [-20.0, -10.0, 0.0, 10.0, 20.0])
    column_variable: str = "churn_change_pts"
    column_values: list[float] = Field(default_factory=lambda: [-1.0, 0.0, 1.0, 2.0, 3.0])
    output: str = "runway_months"
    base: Adjustments = Field(default_factory=Adjustments)
    as_of: str | None = Field(None, pattern=MONTH_PATTERN)
    horizon: int = Field(DEFAULT_HORIZON, ge=1, le=MAX_HORIZON)


@router.post("", response_model=ScenarioResult)
def scenario(body: ScenarioRequest, finance: FinanceDep) -> ScenarioResult:
    adjustments = Adjustments(**body.model_dump(include=set(Adjustments.model_fields)))
    return finance.scenario.run(adjustments, body.as_of, body.horizon)


@router.post("/sensitivity", response_model=SensitivityResult)
def sensitivity(body: SensitivityRequest, finance: FinanceDep) -> SensitivityResult:
    return finance.scenario.sensitivity(
        body.row_variable,
        body.row_values,
        body.column_variable,
        body.column_values,
        output=body.output,
        base=body.base,
        as_of=body.as_of,
        horizon=body.horizon,
    )


@router.post("/montecarlo", response_model=MonteCarloResult)
def montecarlo(body: MonteCarloRequest, finance: FinanceDep) -> MonteCarloResult:
    return run_monte_carlo(finance.scenario, body)
