"""Scenario engine: 12-month cash projection, what-if adjustments and sensitivity tables (PRD §F1).

The baseline *drivers* (cash, MRR, churn, acquisition cost, cost structure) are measured from the workspace data
with DuckDB over the trailing three months and carry lineage. The projection itself is a small deterministic
recurrence, vectorised with NumPy so that the same code runs one scenario (sliders, < 200 ms) or thousands
(Monte Carlo). Drivers are cached per database version, so a slider move only re-runs the recurrence.

The monthly recurrence is spelled out in `RECURRENCE` below (it is also shown in the lineage).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from app.engine.duckdb_engine import FinanceDB, NoDataError
from app.engine.lineage import Lineage, Number
from app.engine.metrics import (
    PAYROLL_FILTER,
    MetricError,
    MetricsEngine,
    _in,
    _Trace,
    month_window,
    shift_month,
)

RECURRENCE = """Monthly recurrence for projection month k = 1..H (changes apply from `start_month`):
    price_k     = 1 + price_change_pct/100                     (a one-off step at the start month)
    churn_k     = max(0, base_churn + churn_change_pts/100)
    marketing_k = base_marketing x (1 + marketing_spend_change_pct/100)
    new_k       = marketing_k / (base_paid_cac x (1 + cac_change_pct/100)) x (1 + acquisition_change_pct/100)
    mrr_k       = mrr_{k-1} x (1 - churn_k) x price_step_k + new_k x new_customer_arpa x price_k
    revenue_k   = mrr_k + other_revenue
    costs_k     = (variable_cogs_ratio + commission_ratio) x mrr_k + fixed_costs + marketing_k
                  + new_hires x cost_per_hire + spend_change
    cash_k      = cash_{k-1} + revenue_k - costs_k
"""
DRIVER_WINDOW = 3
DEFAULT_HORIZON = 12
MAX_HORIZON = 36
RUNWAY_SEARCH_MONTHS = 120  # the runway is searched beyond the chart horizon so it is comparable to the metric


class Adjustments(BaseModel):
    """What-if inputs. Every field defaults to "no change"."""

    price_change_pct: float = Field(0.0, ge=-90, le=500, description="Price change for all customers, in %")
    churn_change_pts: float = Field(0.0, ge=-100, le=100, description="Change in monthly logo churn, in % points")
    cac_change_pct: float = Field(0.0, ge=-90, le=500, description="Change in paid CAC, in %")
    acquisition_change_pct: float = Field(0.0, ge=-100, le=500, description="Change in new customers (win rate), %")
    marketing_spend_change_pct: float = Field(0.0, ge=-100, le=500, description="Change in marketing programmes, %")
    new_hires: int = Field(0, ge=-200, le=500, description="Net new hires (negative = reductions)")
    cost_per_hire_monthly: float | None = Field(None, ge=0, description="Loaded monthly cost per hire (default: data)")
    spend_change_monthly: float = Field(0.0, ge=-1e9, le=1e9, description="Other monthly operating spend change")
    start_month: int = Field(1, ge=1, le=MAX_HORIZON, description="Projection month the changes start (1 = next)")


ADJUSTMENT_FIELDS = tuple(
    name for name in Adjustments.model_fields if name not in ("start_month", "cost_per_hire_monthly")
)


@dataclass(frozen=True)
class Drivers:
    as_of: str
    cash: float
    mrr: float
    customers: int
    churn: float
    new_customer_arpa: float
    paid_cac: float
    marketing: float
    other_revenue: float
    variable_cogs_ratio: float
    commission_ratio: float
    fixed_costs: float
    cost_per_hire: float


class ProjectionPoint(BaseModel):
    month: str
    base_cash: Number
    scenario_cash: Number
    delta: Number
    base_mrr: Number
    scenario_mrr: Number


class ScenarioResult(BaseModel):
    as_of: str
    currency: str
    adjustments: Adjustments
    points: list[ProjectionPoint]
    base_zero_cash_month: str | None
    scenario_zero_cash_month: str | None
    base_runway_months: Number | None
    scenario_runway_months: Number | None
    drivers: dict[str, float]
    elapsed_ms: float
    lineage: Lineage


class SensitivityResult(BaseModel):
    as_of: str
    output: str
    row_variable: str
    row_values: list[float]
    column_variable: str
    column_values: list[float]
    table: list[list[Number | None]] = Field(description="table[i][j] = output at row_values[i], column_values[j]")
    base_value: Number | None
    lineage: Lineage


# --- the recurrence ------------------------------------------------------------------------------------------------
def adjustment_arrays(
    n: int, adjustments: Adjustments, overrides: dict[str, np.ndarray] | None = None
) -> dict[str, np.ndarray]:
    arrays = {name: np.full(n, float(getattr(adjustments, name))) for name in ADJUSTMENT_FIELDS}
    for name, values in (overrides or {}).items():
        if name not in arrays:
            raise ValueError(f"unknown adjustment {name!r}")
        arrays[name] = np.asarray(values, dtype=float)
    return arrays


def _effective(d: Drivers, adj: dict[str, np.ndarray], cost_per_hire: float | None) -> dict[str, np.ndarray | float]:
    price = 1 + adj["price_change_pct"] / 100
    marketing = d.marketing * (1 + adj["marketing_spend_change_pct"] / 100)
    cac = d.paid_cac * (1 + adj["cac_change_pct"] / 100)
    safe_cac = np.where(cac > 0, cac, 1.0)
    new = np.where(cac > 0, marketing / safe_cac, 0.0) * (1 + adj["acquisition_change_pct"] / 100)
    hire_cost = d.cost_per_hire if cost_per_hire is None else cost_per_hire
    return {
        "price": price,
        "churn": np.maximum(0.0, d.churn + adj["churn_change_pts"] / 100),
        "marketing": marketing,
        "new": new,
        "extra": adj["new_hires"] * hire_cost + adj["spend_change_monthly"],
    }


def project(
    d: Drivers, adj: dict[str, np.ndarray], start_month: int, months: int, cost_per_hire: float | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Cash and MRR paths, each shaped (runs, months). `adj` holds one array of length `runs` per adjustment."""
    n = len(next(iter(adj.values())))
    base = _effective(d, adjustment_arrays(n, Adjustments()), None)
    scenario = _effective(d, adj, cost_per_hire)
    variable = d.variable_cogs_ratio + d.commission_ratio
    cash = np.empty((n, months))
    mrr_path = np.empty((n, months))
    mrr = np.full(n, d.mrr)
    balance = np.full(n, d.cash)
    for k in range(1, months + 1):
        e = scenario if k >= start_month else base
        step = scenario["price"] if k == start_month else 1.0
        mrr = mrr * (1 - e["churn"]) * step + e["new"] * d.new_customer_arpa * e["price"]
        costs = variable * mrr + d.fixed_costs + e["marketing"] + e["extra"]
        balance = balance + (mrr + d.other_revenue) - costs
        cash[:, k - 1] = balance
        mrr_path[:, k - 1] = mrr
    return cash, mrr_path


def runway_months(cash0: float, cash: np.ndarray) -> np.ndarray:
    """Months until cash first drops below zero, linearly interpolated within the month; NaN if never."""
    n = cash.shape[0]
    prev = np.concatenate([np.full((n, 1), cash0), cash[:, :-1]], axis=1)
    below = cash < 0
    first = np.where(below.any(axis=1), below.argmax(axis=1), -1)
    result = np.full(n, np.nan)
    hit = first >= 0
    idx = first[hit]
    rows = np.nonzero(hit)[0]
    before = prev[rows, idx]
    after = cash[rows, idx]
    fraction = np.where(before > after, before / (before - after), 0.0)
    result[hit] = idx + np.clip(fraction, 0.0, 1.0)
    if cash0 < 0:
        result[:] = 0.0
    return result


# --- engine --------------------------------------------------------------------------------------------------------
class ScenarioEngine:
    def __init__(self, db: FinanceDB, currency: str = "USD") -> None:
        self.db = db
        self.currency = currency
        self._cache: dict[tuple[int, str | None], tuple[Drivers, _Trace]] = {}
        self._lock = threading.Lock()

    def drivers(self, as_of: str | None = None) -> tuple[Drivers, _Trace]:
        key = (self.db.version, as_of)
        with self._lock:
            cached = self._cache.get(key)
        if cached:
            return cached
        result = self._measure_drivers(as_of)
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if k[0] == self.db.version}
            self._cache[key] = result
        return result

    def _measure_drivers(self, as_of: str | None) -> tuple[Drivers, _Trace]:
        metrics = MetricsEngine(self.db, self.currency)
        with self.db.connect() as con:
            metrics._require(con, "bank_balance", "pnl", "subscriptions", "customers", "marketing_spend")
            months_available = metrics._months(con)
            m = as_of or months_available[-1]
            if m not in months_available:
                raise MetricError(f"{m} is outside the data ({months_available[0]}..{months_available[-1]})")
            window = month_window(m, DRIVER_WINDOW)
            t = _Trace(con)
            w = _in(window)
            t.source("bank_balance", f"month = '{m}'")
            closing = f"SELECT closing_balance FROM bank_balance WHERE month = '{m}' ORDER BY _source_row DESC"
            cash = float(t.scalar(closing) or 0)
            mrr, customers = metrics._mrr_at(t, m)
            start, lost, _, _ = metrics._churn_parts(t, window)
            churn = lost / start if start else 0.0
            new = metrics._new_customers(t, window)["all"]
            t.source("subscriptions", f"month IN {w}")
            new_arpa_row = t.rows(
                "SELECT avg(s.mrr) FROM subscriptions s JOIN customers c USING (customer_id) "
                f"WHERE c.signup_month IN {w} AND s.month = c.signup_month"
            )[0]
            arpa = float(mrr) / customers if customers else 0.0
            new_customer_arpa = float(new_arpa_row[0]) if new_arpa_row[0] is not None else arpa
            t.source("marketing_spend", f"month IN {w}")
            marketing = (
                float(t.scalar(f"SELECT sum(spend) FROM marketing_spend WHERE month IN {w}") or 0) / DRIVER_WINDOW
            )
            avg_mrr = float(t.scalar(f"SELECT sum(mrr) FROM subscriptions WHERE month IN {w}") or 0) / DRIVER_WINDOW
            t.source("pnl", f"month IN {w}")
            totals = dict(
                t.rows(
                    f"""SELECT bucket, sum(amount) / {DRIVER_WINDOW} FROM (
  SELECT amount, CASE
    WHEN category = 'Revenue' THEN 'revenue'
    WHEN category = 'COGS' AND NOT ({PAYROLL_FILTER}) THEN 'variable_cogs'
    WHEN category = 'Operating expense' AND lower(account) LIKE '%commission%' THEN 'commissions'
    ELSE 'other_costs' END AS bucket
  FROM pnl WHERE month IN {w}
) GROUP BY bucket ORDER BY bucket"""
                )
            )
            payroll = float(t.scalar(f"SELECT sum(amount) FROM pnl WHERE {PAYROLL_FILTER} AND month = '{m}'") or 0)
            try:
                metrics._require(con, "headcount")
                active = f"start_month <= '{m}' AND (end_month IS NULL OR end_month > '{m}')"
                t.source("headcount", active)
                headcount = int(t.scalar(f"SELECT count(*) FROM headcount WHERE {active}") or 0)
            except NoDataError:
                headcount = 0
        revenue = float(totals.get("revenue", 0))
        variable_cogs = float(totals.get("variable_cogs", 0))
        commissions = float(totals.get("commissions", 0))
        other_costs = float(totals.get("other_costs", 0))
        paid_cac = marketing / (new / DRIVER_WINDOW) if new else 0.0
        drivers = Drivers(
            as_of=m,
            cash=cash,
            mrr=float(mrr),
            customers=customers,
            churn=churn,
            new_customer_arpa=new_customer_arpa,
            paid_cac=paid_cac,
            marketing=marketing,
            other_revenue=max(0.0, revenue - avg_mrr),
            variable_cogs_ratio=variable_cogs / avg_mrr if avg_mrr else 0.0,
            commission_ratio=commissions / avg_mrr if avg_mrr else 0.0,
            # Marketing programmes are modelled separately (they drive acquisition), so remove them here.
            fixed_costs=other_costs - marketing,
            cost_per_hire=payroll / headcount if headcount else 0.0,
        )
        return drivers, t

    def _lineage(self, metric: str, d: Drivers, t: _Trace, formula: str) -> Lineage:
        inputs = {
            f.name: Decimal(str(round(getattr(d, f.name), 6)))
            for f in fields(d)
            if isinstance(getattr(d, f.name), int | float)
        }
        lineage = t.lineage(metric, formula, inputs, f"{month_window(d.as_of, DRIVER_WINDOW)[0]}..{d.as_of}")
        return lineage

    def run(self, adjustments: Adjustments, as_of: str | None = None, horizon: int = DEFAULT_HORIZON) -> ScenarioResult:
        if not 1 <= horizon <= MAX_HORIZON:
            raise MetricError(f"horizon must be between 1 and {MAX_HORIZON} months")
        started = time.perf_counter()
        d, t = self.drivers(as_of)
        search = max(horizon, RUNWAY_SEARCH_MONTHS)
        base_adj = adjustment_arrays(1, Adjustments())
        scen_adj = adjustment_arrays(1, adjustments)
        base_cash, base_mrr = project(d, base_adj, 1, search)
        scen_cash, scen_mrr = project(d, scen_adj, adjustments.start_month, search, adjustments.cost_per_hire_monthly)
        base_runway = runway_months(d.cash, base_cash)[0]
        scen_runway = runway_months(d.cash, scen_cash)[0]
        points = [
            ProjectionPoint(
                month=shift_month(d.as_of, k + 1),
                base_cash=_money(base_cash[0, k]),
                scenario_cash=_money(scen_cash[0, k]),
                delta=_money(scen_cash[0, k] - base_cash[0, k]),
                base_mrr=_money(base_mrr[0, k]),
                scenario_mrr=_money(scen_mrr[0, k]),
            )
            for k in range(horizon)
        ]
        return ScenarioResult(
            as_of=d.as_of,
            currency=self.currency,
            adjustments=adjustments,
            points=points,
            base_zero_cash_month=_zero_month(d.as_of, base_runway),
            scenario_zero_cash_month=_zero_month(d.as_of, scen_runway),
            base_runway_months=_months_or_none(base_runway),
            scenario_runway_months=_months_or_none(scen_runway),
            drivers={f.name: float(getattr(d, f.name)) for f in fields(d) if f.name != "as_of"},
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            lineage=self._lineage("scenario", d, t, RECURRENCE.strip()),
        )

    def sensitivity(
        self,
        row_variable: str,
        row_values: list[float],
        column_variable: str,
        column_values: list[float],
        *,
        output: str = "cash_at_horizon",
        base: Adjustments | None = None,
        as_of: str | None = None,
        horizon: int = DEFAULT_HORIZON,
    ) -> SensitivityResult:
        """2-variable grid (e.g. price x churn) of cash at the horizon or runway months."""
        for name in (row_variable, column_variable):
            if name not in ADJUSTMENT_FIELDS:
                raise MetricError(f"unknown variable {name!r}; choose from {', '.join(ADJUSTMENT_FIELDS)}")
        if row_variable == column_variable:
            raise MetricError("row and column variables must differ")
        if output not in ("cash_at_horizon", "runway_months"):
            raise MetricError("output must be 'cash_at_horizon' or 'runway_months'")
        if not (1 <= len(row_values) <= 11 and 1 <= len(column_values) <= 11):
            raise MetricError("use 1 to 11 values per variable")
        base = base or Adjustments()
        for name, values in ((row_variable, row_values), (column_variable, column_values)):
            for v in values:  # reuse the Adjustments bounds for validation
                Adjustments(**{**base.model_dump(), name: v})
        d, t = self.drivers(as_of)
        grid_r, grid_c = np.meshgrid(np.asarray(row_values, float), np.asarray(column_values, float), indexing="ij")
        n = grid_r.size
        arrays = adjustment_arrays(n, base, {row_variable: grid_r.ravel(), column_variable: grid_c.ravel()})
        months = max(horizon, RUNWAY_SEARCH_MONTHS) if output == "runway_months" else horizon
        cash, _ = project(d, arrays, base.start_month, months, base.cost_per_hire_monthly)
        base_cash, _ = project(d, adjustment_arrays(1, base), base.start_month, months, base.cost_per_hire_monthly)
        if output == "runway_months":
            values = runway_months(d.cash, cash)
            base_value = _months_or_none(runway_months(d.cash, base_cash)[0])
            cells = [_months_or_none(v) for v in values]
        else:
            values = cash[:, horizon - 1]
            base_value = _money(base_cash[0, horizon - 1])
            cells = [_money(v) for v in values]
        table = [cells[i * len(column_values) : (i + 1) * len(column_values)] for i in range(len(row_values))]
        return SensitivityResult(
            as_of=d.as_of,
            output=output,
            row_variable=row_variable,
            row_values=list(row_values),
            column_variable=column_variable,
            column_values=list(column_values),
            table=table,
            base_value=base_value,
            lineage=self._lineage("sensitivity", d, t, f"{output} of the scenario projection for each grid cell"),
        )


def _money(value: Any) -> Decimal:
    return Decimal(str(round(float(value), 2)))


def _months_or_none(value: float) -> Decimal | None:
    return None if np.isnan(value) else Decimal(str(round(float(value), 2)))


def _zero_month(as_of: str, runway: float) -> str | None:
    if np.isnan(runway):
        return None
    return shift_month(as_of, int(np.floor(runway)) + 1)
