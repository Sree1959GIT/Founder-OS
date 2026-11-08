"""Scenario engine: 12-month cash projection, what-if adjustments and sensitivity tables (PRD §F1).

The baseline *drivers* (cash, MRR, churn, acquisition cost, cost structure) are measured from the workspace data
with DuckDB over the trailing three months and carry lineage. The projection itself is a small deterministic
recurrence, vectorised with NumPy so that the same code runs one scenario (sliders, < 200 ms) or thousands
(Monte Carlo). Drivers are cached per database version, so a slider move only re-runs the recurrence.

The monthly recurrence is spelled out in `RECURRENCE` below (it is also shown in the lineage).

Two runways, named apart everywhere (API labels in `RUNWAY_LABELS`):
- **Runway (actual burn)** is the `runway` metric: closing cash / the trailing average net burn from the bank sheet.
- **Projected runway (with growth assumptions)** comes from this recurrence. `growth_mode` sets the growth assumption:
  "trend" (default) keeps acquiring customers at the measured CAC while churn continues; "none" stops new customers
  (churn continues, marketing programmes are still spent); "flat" holds today's MRR (no new customers, no churn), i.e.
  today's run-rate, which reconciles with the runway metric (see `RunwayReconciliation`).
Every driver is returned as an `Assumption` with a plain-English label, its window and its own lineage.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, ValidationError

from app.engine.duckdb_engine import FinanceDB, NoDataError
from app.engine.lineage import Lineage, MetricResult, Number
from app.engine.metrics import (
    PAYROLL_FILTER,
    Capture,
    MetricError,
    MetricsEngine,
    _in,
    _Trace,
    month_window,
    shift_month,
)

RECURRENCE = """Monthly recurrence for projection month k = 1..H (changes apply from `start_month`):
    price_k     = 1 + price_change_pct/100                     (a one-off step at the start month)
    churn_k     = max(0, base_churn + churn_change_pts/100)                (base_churn = 0 when growth_mode = flat)
    marketing_k = base_marketing x (1 + marketing_spend_change_pct/100)
    new_k       = marketing_k / (base_paid_cac x (1 + cac_change_pct/100)) x (1 + acquisition_change_pct/100)
                  (new_k = 0 when growth_mode = none or flat)
    mrr_k       = mrr_{k-1} x (1 - churn_k) x price_step_k + new_k x new_customer_arpa x price_k
    revenue_k   = mrr_k + other_revenue
    costs_k     = (variable_cogs_ratio + commission_ratio) x mrr_k + fixed_costs + marketing_k
                  + new_hires x cost_per_hire + spend_change
                  + one_off_cost                                           (at the start month only)
    cash_k      = cash_{k-1} + revenue_k - costs_k
"""
DRIVER_WINDOW = 3
DEFAULT_HORIZON = 12
MAX_HORIZON = 36
RUNWAY_SEARCH_MONTHS = 120  # the runway is searched beyond the chart horizon so it is comparable to the metric
# The run-rate projection and the runway metric measure the same burn on different bases (P&L vs bank cash). A gap
# within this share of the runway metric is cash timing; a larger one means the drivers no longer describe the bank.
RECONCILIATION_TOLERANCE = Decimal("0.05")

GrowthMode = Literal["trend", "none", "flat"]
GROWTH_MODES: dict[str, str] = {
    "trend": "New customers keep arriving at the measured CAC (marketing programmes / paid CAC); churn continues",
    "none": "No new customers; churn continues and marketing programmes are still spent",
    "flat": "Today's run-rate: MRR held at today's level (no new customers, no churn)",
}
RUNWAY_LABELS: dict[str, str] = {
    "runway_actual_burn_months": "Runway (actual burn)",
    "run_rate_runway_months": "Runway at today's run-rate (projection, no growth)",
    "base_runway_months": "Projected runway (with growth assumptions)",
    "scenario_runway_months": "Projected runway (scenario, with growth assumptions)",
}


class Adjustments(BaseModel):
    """What-if inputs. Every field defaults to "no change"."""

    price_change_pct: float = Field(0.0, ge=-90, le=500, description="Price change for all customers, in %")
    price_applies_to_existing: float = Field(
        1.0, ge=0, le=1, description="Share of existing customers the price change reaches (0: new customers only)"
    )
    churn_change_pts: float = Field(0.0, ge=-100, le=100, description="Change in monthly logo churn, in % points")
    cac_change_pct: float = Field(0.0, ge=-90, le=500, description="Change in paid CAC, in %")
    acquisition_change_pct: float = Field(0.0, ge=-100, le=500, description="Change in new customers (win rate), %")
    marketing_spend_change_pct: float = Field(0.0, ge=-100, le=500, description="Change in marketing programmes, %")
    new_hires: int = Field(0, ge=-200, le=500, description="Net new hires (negative = reductions)")
    cost_per_hire_monthly: float | None = Field(None, ge=0, description="Loaded monthly cost per hire (default: data)")
    spend_change_monthly: float = Field(0.0, ge=-1e9, le=1e9, description="Other monthly operating spend change")
    one_off_cost: float = Field(
        0.0, ge=-1e9, le=1e9, description="Cost paid once, in the start month (negative: cash in)"
    )
    start_month: int = Field(1, ge=1, le=MAX_HORIZON, description="Projection month the changes start (1 = next)")
    growth_mode: GrowthMode = Field(
        "trend",
        description="Growth assumption for the base and the scenario: 'trend' (keep acquiring customers), "
        "'none' (no new customers) or 'flat' (today's run-rate: no new customers, no churn)",
    )


ADJUSTMENT_FIELDS = tuple(
    name for name in Adjustments.model_fields if name not in ("start_month", "cost_per_hire_monthly", "growth_mode")
)


@dataclass(frozen=True)
class Drivers:
    as_of: str
    cash: float
    mrr: float
    customers: int
    churn: float
    new_customers: float
    new_customer_arpa: float
    paid_cac: float
    marketing: float
    other_revenue: float
    variable_cogs_ratio: float
    commission_ratio: float
    fixed_costs: float
    cost_per_hire: float


# name -> (label, unit, how it is derived). `{m}` = as-of month, `{w}` = driver window.
ASSUMPTIONS: dict[str, tuple[str, str, str]] = {
    "cash": ("Starting cash", "currency", "bank_balance.closing_balance in {m}"),
    "mrr": ("Starting MRR", "currency", "sum of subscriptions.mrr in {m}"),
    "churn": (
        "Monthly logo churn",
        "ratio",
        "customers lost / customers active at the start of each month, summed over {w}",
    ),
    "new_customers": ("New customers per month", "count", "customers with signup_month in {w}, divided by 3"),
    "new_customer_arpa": (
        "MRR per new customer",
        "currency",
        "average first-month subscriptions.mrr of customers who signed up in {w}",
    ),
    "paid_cac": (
        "Acquisition cost per new customer (marketing programmes)",
        "currency",
        "marketing programmes per month / new customers per month, over {w}",
    ),
    "marketing": ("Marketing programmes per month", "currency", "sum of marketing_spend.spend over {w}, divided by 3"),
    "other_revenue": (
        "Non-subscription revenue per month",
        "currency",
        "average P&L Revenue over {w} minus average subscription MRR over {w}",
    ),
    "variable_cogs_ratio": (
        "Variable cost of revenue (share of MRR)",
        "ratio",
        "P&L COGS excluding payroll over {w} / subscription MRR over {w}",
    ),
    "commission_ratio": (
        "Sales commissions (share of MRR)",
        "ratio",
        "P&L operating expenses named 'commission' over {w} / subscription MRR over {w}",
    ),
    "fixed_costs": (
        "Fixed costs per month (payroll, opex; excludes marketing programmes)",
        "currency",
        "average monthly P&L costs over {w} other than variable COGS and commissions, minus marketing programmes",
    ),
    "cost_per_hire": (
        "Loaded monthly cost per hire",
        "currency",
        "P&L payroll in {m} / active headcount in {m}",
    ),
}


class Assumption(BaseModel):
    """One projection driver, measured from the workspace data."""

    name: str
    label: str
    value: Number
    unit: str = Field(description="currency code, 'ratio' (0.0167 = 1.67 %/month) or 'count'")
    window: str = Field(description='Months the value was measured over, e.g. "2026-08..2026-10"')
    used: bool = Field(description="False when the growth_mode replaces this driver (see note)")
    note: str | None = None
    lineage: Lineage


class RunwayReconciliation(BaseModel):
    """How the projected runway relates to the runway metric (actual burn), step by step."""

    runway_actual_burn_months: Number | None = Field(
        description="Runway (actual burn) = GET /api/metrics/runway: closing cash / trailing average net burn"
    )
    actual_net_burn: Number | None = Field(description="Trailing average net burn from the bank sheet (cash basis)")
    run_rate_runway_months: Number | None = Field(
        description="Projection with growth_mode 'flat' (today's MRR and costs held constant)"
    )
    run_rate_net_burn: Number = Field(description="Monthly burn of that projection (P&L basis)")
    basis_gap_net_burn: Number | None = Field(description="actual_net_burn - run_rate_net_burn (cash timing)")
    basis_gap_months: Number | None = Field(description="run_rate_runway_months - runway_actual_burn_months")
    tolerance_months: Number | None = Field(description="5 % of runway_actual_burn_months")
    within_tolerance: bool | None
    growth_mode: GrowthMode
    projected_runway_months: Number | None = Field(description="Base projection with the requested growth_mode")
    growth_gap_months: Number | None = Field(description="projected_runway_months - run_rate_runway_months")
    explanation: str


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
    growth_mode: GrowthMode
    growth_assumption: str = Field(description="Plain-English meaning of growth_mode")
    base_zero_cash_month: str | None
    scenario_zero_cash_month: str | None
    base_runway_months: Number | None = Field(description="Projected runway (with growth assumptions), no adjustments")
    scenario_runway_months: Number | None = Field(description="Projected runway (with growth assumptions), scenario")
    reconciliation: RunwayReconciliation
    assumptions: list[Assumption]
    labels: dict[str, str] = Field(default_factory=lambda: dict(RUNWAY_LABELS), description="UI labels for runways")
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


def _effective(
    d: Drivers, adj: dict[str, np.ndarray], cost_per_hire: float | None, growth_mode: GrowthMode
) -> dict[str, np.ndarray | float]:
    price = 1 + adj["price_change_pct"] / 100
    marketing = d.marketing * (1 + adj["marketing_spend_change_pct"] / 100)
    cac = d.paid_cac * (1 + adj["cac_change_pct"] / 100)
    safe_cac = np.where(cac > 0, cac, 1.0)
    new = np.where(cac > 0, marketing / safe_cac, 0.0) * (1 + adj["acquisition_change_pct"] / 100)
    if growth_mode != "trend":
        new = np.zeros_like(new)
    base_churn = 0.0 if growth_mode == "flat" else d.churn
    hire_cost = d.cost_per_hire if cost_per_hire is None else cost_per_hire
    return {
        "price": price,
        "existing_step": 1 + adj["price_change_pct"] / 100 * adj["price_applies_to_existing"],
        "churn": np.maximum(0.0, base_churn + adj["churn_change_pts"] / 100),
        "marketing": marketing,
        "new": new,
        "extra": adj["new_hires"] * hire_cost + adj["spend_change_monthly"],
        "one_off": adj["one_off_cost"],
    }


def project(
    d: Drivers,
    adj: dict[str, np.ndarray],
    start_month: int,
    months: int,
    cost_per_hire: float | None = None,
    growth_mode: GrowthMode = "trend",
) -> tuple[np.ndarray, np.ndarray]:
    """Cash and MRR paths, each shaped (runs, months). `adj` holds one array of length `runs` per adjustment."""
    n = len(next(iter(adj.values())))
    base = _effective(d, adjustment_arrays(n, Adjustments()), None, growth_mode)
    scenario = _effective(d, adj, cost_per_hire, growth_mode)
    variable = d.variable_cogs_ratio + d.commission_ratio
    cash = np.empty((n, months))
    mrr_path = np.empty((n, months))
    mrr = np.full(n, d.mrr)
    balance = np.full(n, d.cash)
    for k in range(1, months + 1):
        e = scenario if k >= start_month else base
        step = scenario["existing_step"] if k == start_month else 1.0
        mrr = mrr * (1 - e["churn"]) * step + e["new"] * d.new_customer_arpa * e["price"]
        costs = variable * mrr + d.fixed_costs + e["marketing"] + e["extra"]
        if k == start_month:
            costs = costs + scenario["one_off"]
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
@dataclass(frozen=True)
class _Baseline:
    drivers: Drivers
    trace: _Trace
    provenance: dict[str, Capture]  # assumption name -> the SQL and rows it was measured from
    runway_metric: MetricResult | None  # the runway metric (actual burn) at the same month, if defined


class ScenarioEngine:
    def __init__(self, db: FinanceDB, currency: str = "USD") -> None:
        self.db = db
        self.currency = currency
        self._cache: dict[tuple[int, str | None], _Baseline] = {}
        self._lock = threading.Lock()

    def drivers(self, as_of: str | None = None) -> tuple[Drivers, _Trace]:
        baseline = self.baseline(as_of)
        return baseline.drivers, baseline.trace

    def baseline(self, as_of: str | None = None) -> _Baseline:
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

    def _measure_drivers(self, as_of: str | None) -> _Baseline:
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
            with t.capture() as cash_src:
                t.source("bank_balance", f"month = '{m}'")
                closing = f"SELECT closing_balance FROM bank_balance WHERE month = '{m}' ORDER BY _source_row DESC"
                cash = float(t.scalar(closing) or 0)
            with t.capture() as mrr_src:
                mrr, customers = metrics._mrr_at(t, m)
            with t.capture() as churn_src:
                start, lost, _, _ = metrics._churn_parts(t, window)
            churn = lost / start if start else 0.0
            with t.capture() as new_src:
                new = metrics._new_customers(t, window)["all"]
            with t.capture() as arpa_src:
                t.source("customers", f"signup_month IN {w}")
                t.source("subscriptions", f"month IN {w}")
                new_arpa_row = t.rows(
                    "SELECT avg(s.mrr) FROM subscriptions s JOIN customers c USING (customer_id) "
                    f"WHERE c.signup_month IN {w} AND s.month = c.signup_month"
                )[0]
            arpa = float(mrr) / customers if customers else 0.0
            new_customer_arpa = float(new_arpa_row[0]) if new_arpa_row[0] is not None else arpa
            with t.capture() as marketing_src:
                t.source("marketing_spend", f"month IN {w}")
                marketing = (
                    float(t.scalar(f"SELECT sum(spend) FROM marketing_spend WHERE month IN {w}") or 0) / DRIVER_WINDOW
                )
            with t.capture() as avg_mrr_src:
                t.source("subscriptions", f"month IN {w}")
                avg_mrr = float(t.scalar(f"SELECT sum(mrr) FROM subscriptions WHERE month IN {w}") or 0) / DRIVER_WINDOW
            with t.capture() as pnl_src:
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
            with t.capture() as hire_src:
                t.source("pnl", f"{PAYROLL_FILTER} AND month = '{m}'")
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
            new_customers=new / DRIVER_WINDOW,
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
        provenance = {
            "cash": cash_src,
            "mrr": mrr_src,
            "churn": churn_src,
            "new_customers": new_src,
            "new_customer_arpa": arpa_src,
            "paid_cac": marketing_src + new_src,
            "marketing": marketing_src,
            "other_revenue": pnl_src + avg_mrr_src,
            "variable_cogs_ratio": pnl_src + avg_mrr_src,
            "commission_ratio": pnl_src + avg_mrr_src,
            "fixed_costs": pnl_src + marketing_src,
            "cost_per_hire": hire_src,
        }
        try:
            runway_metric: MetricResult | None = metrics.compute("runway", m)
        except (MetricError, NoDataError):
            runway_metric = None
        return _Baseline(drivers, t, provenance, runway_metric)

    def assumptions(self, baseline: _Baseline, growth_mode: GrowthMode) -> list[Assumption]:
        """Every projection driver with its label, window and lineage; flags the ones `growth_mode` replaces."""
        d = baseline.drivers
        window = month_window(d.as_of, DRIVER_WINDOW)
        period = f"{window[0]}..{window[-1]}"
        no_new = ("new_customers", "new_customer_arpa", "paid_cac")
        replaced: dict[str, str] = {}
        if growth_mode != "trend":
            replaced = dict.fromkeys(no_new, f"Not used: growth_mode '{growth_mode}' adds no new customers")
        if growth_mode == "flat":
            replaced["churn"] = "Not used: growth_mode 'flat' holds today's MRR (no churn)"
        result = []
        for name, (label, unit, basis) in ASSUMPTIONS.items():
            value = float(getattr(d, name))
            source = baseline.provenance[name]
            period_of = d.as_of if "{w}" not in basis else period
            rounded = round(value, 4) if unit == "ratio" else round(value, 2)
            result.append(
                Assumption(
                    name=name,
                    label=label,
                    value=Decimal(str(rounded)),
                    unit=self.currency if unit == "currency" else unit,
                    window=period_of,
                    used=name not in replaced,
                    note=replaced.get(name),
                    lineage=Lineage(
                        metric=f"assumption.{name}",
                        sql=list(source.sql),
                        source_files=sorted({s.file for s in source.sources}),
                        source_rows=list(source.sources),
                        formula=basis.format(m=d.as_of, w=period),
                        inputs={name: Decimal(str(round(value, 6)))},
                        period=period_of,
                    ),
                )
            )
        return result

    def reconcile(self, baseline: _Baseline, growth_mode: GrowthMode) -> RunwayReconciliation:
        """Walk from the runway metric (actual burn) to the projected runway: basis gap, then growth assumptions."""
        d = baseline.drivers
        no_change = adjustment_arrays(1, Adjustments())
        flat_cash, _ = project(d, no_change, 1, RUNWAY_SEARCH_MONTHS, growth_mode="flat")
        run_rate = _months_or_none(runway_months(d.cash, flat_cash)[0])
        run_rate_burn = _money(d.cash - flat_cash[0, 0])
        proj_cash, _ = project(d, no_change, 1, RUNWAY_SEARCH_MONTHS, growth_mode=growth_mode)
        projected = _months_or_none(runway_months(d.cash, proj_cash)[0])
        metric = baseline.runway_metric
        actual = metric.value if metric else None
        actual_burn = metric.lineage.inputs.get("net_burn") if metric else None
        basis_gap = run_rate - actual if run_rate is not None and actual is not None else None
        growth_gap = projected - run_rate if projected is not None and run_rate is not None else None
        burn_gap = actual_burn - run_rate_burn if actual_burn is not None else None
        tol = _months_or_none(float(actual * RECONCILIATION_TOLERANCE)) if actual is not None else None
        within = abs(basis_gap) <= tol if basis_gap is not None and tol is not None else None

        parts = []
        if actual is not None:
            parts.append(
                f"Runway (actual burn) is {actual} months: closing cash {d.cash:,.2f} / the trailing "
                f"{DRIVER_WINDOW}-month average net burn from the bank sheet ({actual_burn:,.2f}/month, cash basis)."
            )
        elif metric is not None:
            parts.append("Runway (actual burn) is undefined: the trailing average net burn is not positive.")
        else:
            parts.append("Runway (actual burn) could not be computed for this month (not enough bank history).")
        if run_rate is None:
            parts.append(
                f"At today's run-rate the projection does not run out of cash within {RUNWAY_SEARCH_MONTHS} months."
            )
        else:
            parts.append(
                f"At today's run-rate (growth_mode 'flat': no new customers, no churn) the projection burns "
                f"{run_rate_burn:,.2f}/month on a P&L basis (revenue minus costs) and lasts {run_rate} months."
            )
        if basis_gap is not None and burn_gap is not None:
            parts.append(
                f"The {abs(basis_gap)}-month difference comes from the burn: {abs(burn_gap):,.2f}/month "
                f"({abs(burn_gap) / actual_burn:.1%}) of cash timing (customer receipts vs invoiced revenue, "
                f"payments vs booked costs). That is {'within' if within else 'OUTSIDE'} the "
                f"{RECONCILIATION_TOLERANCE:.0%} tolerance ({tol} months)."
            )
        if growth_mode != "flat":
            if growth_mode == "trend":
                how = (
                    f"new customers keep arriving ({d.new_customers:.2f}/month at {d.new_customer_arpa:,.2f} MRR "
                    f"each) while {d.churn:.2%} of customers churn each month"
                )
            else:
                how = (
                    f"no new customers arrive while {d.churn:.2%} of customers churn each month and marketing "
                    f"programmes ({d.marketing:,.2f}/month) are still spent"
                )
            if projected is None:
                parts.append(
                    f"Projected runway (growth_mode '{growth_mode}': {how}) does not run out within "
                    f"{RUNWAY_SEARCH_MONTHS} months."
                )
            elif growth_gap is not None:
                parts.append(
                    f"Projected runway (growth_mode '{growth_mode}') is {projected} months, {growth_gap:+} months vs "
                    f"the run-rate, because {how}."
                )
        return RunwayReconciliation(
            runway_actual_burn_months=actual,
            actual_net_burn=actual_burn,
            run_rate_runway_months=run_rate,
            run_rate_net_burn=run_rate_burn,
            basis_gap_net_burn=burn_gap,
            basis_gap_months=basis_gap,
            tolerance_months=tol,
            within_tolerance=within,
            growth_mode=growth_mode,
            projected_runway_months=projected,
            growth_gap_months=growth_gap,
            explanation=" ".join(parts),
        )

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
        baseline = self.baseline(as_of)
        d, t = baseline.drivers, baseline.trace
        mode = adjustments.growth_mode
        search = max(horizon, RUNWAY_SEARCH_MONTHS)
        base_adj = adjustment_arrays(1, Adjustments())
        scen_adj = adjustment_arrays(1, adjustments)
        base_cash, base_mrr = project(d, base_adj, 1, search, growth_mode=mode)
        scen_cash, scen_mrr = project(
            d, scen_adj, adjustments.start_month, search, adjustments.cost_per_hire_monthly, mode
        )
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
            growth_mode=mode,
            growth_assumption=GROWTH_MODES[mode],
            base_zero_cash_month=_zero_month(d.as_of, base_runway),
            scenario_zero_cash_month=_zero_month(d.as_of, scen_runway),
            base_runway_months=_months_or_none(base_runway),
            scenario_runway_months=_months_or_none(scen_runway),
            reconciliation=self.reconcile(baseline, mode),
            assumptions=self.assumptions(baseline, mode),
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
                try:
                    Adjustments(**{**base.model_dump(), name: v})
                except ValidationError as exc:
                    raise MetricError(f"{name}={v:g} is not allowed: {exc.errors()[0]['msg']}") from exc
        d, t = self.drivers(as_of)
        grid_r, grid_c = np.meshgrid(np.asarray(row_values, float), np.asarray(column_values, float), indexing="ij")
        n = grid_r.size
        arrays = adjustment_arrays(n, base, {row_variable: grid_r.ravel(), column_variable: grid_c.ravel()})
        months = max(horizon, RUNWAY_SEARCH_MONTHS) if output == "runway_months" else horizon
        cash, _ = project(d, arrays, base.start_month, months, base.cost_per_hire_monthly, base.growth_mode)
        base_cash, _ = project(
            d, adjustment_arrays(1, base), base.start_month, months, base.cost_per_hire_monthly, base.growth_mode
        )
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
