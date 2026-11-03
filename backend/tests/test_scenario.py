"""Scenario engine, sensitivity and Monte Carlo."""

from __future__ import annotations

import itertools
import time
from decimal import Decimal

import numpy as np
import pytest
from pydantic import ValidationError

from app.engine.duckdb_engine import FinanceDB
from app.engine.lineage import compact_ranges
from app.engine.metrics import MetricError
from app.engine.montecarlo import Distribution, MonteCarloRequest, run_monte_carlo
from app.engine.scenario import ASSUMPTIONS, Adjustments, ScenarioEngine, ScenarioResult
from tests import golden as g

LATEST = "2026-10"


@pytest.fixture(scope="module")
def engine(loaded_db: FinanceDB) -> ScenarioEngine:
    e = ScenarioEngine(loaded_db, "USD")
    e.drivers()  # warm the driver cache (as the first slider move would)
    return e


def test_drivers_match_independent_calculation(engine: ScenarioEngine) -> None:
    d, trace = engine.drivers()
    months = g.window(LATEST, 3)
    assert d.as_of == LATEST
    assert d.cash == float(g.bank(LATEST)["closing_balance"])
    mrr, customers = g.mrr(LATEST)
    assert (d.mrr, d.customers) == (float(mrr), customers)
    start, lost, _, _ = g.churn_parts(LATEST, 3)
    assert d.churn == pytest.approx(lost / start)
    marketing = sum(Decimal(r["spend"]) for r in g.rows("marketing_spend") if r["month"] in months) / 3
    assert d.marketing == pytest.approx(float(marketing))
    assert d.paid_cac == pytest.approx(float(marketing) / (g.new_customers(months) / 3))
    avg_mrr = sum(g.mrr(m)[0] for m in months) / 3
    assert d.other_revenue == pytest.approx(float(g.revenue(months) / 3 - avg_mrr))
    commissions = g.pnl_total(months, lambda r: r["account"] == "Sales commissions") / 3
    assert d.commission_ratio == pytest.approx(float(commissions / avg_mrr))
    assert d.cost_per_hire == pytest.approx(float(g.payroll(LATEST, 1)) / g.active_headcount(LATEST), rel=1e-6)
    assert trace.sql and trace.sources


def test_base_month_one_reconciles_with_drivers(engine: ScenarioEngine) -> None:
    """Hand-roll the recurrence for month 1 from the drivers."""
    d, _ = engine.drivers()
    result = engine.run(Adjustments())
    mrr1 = d.mrr * (1 - d.churn) + (d.marketing / d.paid_cac) * d.new_customer_arpa
    costs = (d.variable_cogs_ratio + d.commission_ratio) * mrr1 + d.fixed_costs + d.marketing
    cash1 = d.cash + mrr1 + d.other_revenue - costs
    first = result.points[0]
    assert first.month == "2026-11"
    assert float(first.base_cash) == pytest.approx(cash1, abs=0.01)
    assert float(first.base_mrr) == pytest.approx(mrr1, abs=0.01)
    # Month-1 net burn is close to the measured trailing net burn (sanity: same cost structure).
    assert d.cash - cash1 == pytest.approx(float(g.net_burn(LATEST, 3)), rel=0.05)


def test_no_change_scenario_equals_base(engine: ScenarioEngine) -> None:
    result = engine.run(Adjustments())
    assert len(result.points) == 12
    assert all(p.delta == 0 and p.base_cash == p.scenario_cash for p in result.points)
    assert result.base_runway_months == result.scenario_runway_months
    assert result.base_zero_cash_month == result.scenario_zero_cash_month == "2027-10"
    assert result.base_runway_months == Decimal("11.23")


def test_hires_cost_is_exactly_linear(engine: ScenarioEngine) -> None:
    result = engine.run(Adjustments(new_hires=2, cost_per_hire_monthly=10_000))
    for k, point in enumerate(result.points, start=1):
        assert point.delta == Decimal(-20_000 * k)


def test_start_month_delays_the_change(engine: ScenarioEngine) -> None:
    result = engine.run(Adjustments(spend_change_monthly=5_000, start_month=4))
    assert [p.delta for p in result.points[:3]] == [0, 0, 0]
    assert result.points[3].delta == Decimal(-5000)
    assert result.points[11].delta == Decimal(-45000)


@pytest.mark.parametrize(
    ("adjustment", "direction"),
    [
        ({"price_change_pct": 10}, 1),
        ({"churn_change_pts": 2}, -1),
        ({"cac_change_pct": 50}, -1),
        ({"acquisition_change_pct": 30}, 1),
        ({"new_hires": 3}, -1),
    ],
)
def test_directions(engine: ScenarioEngine, adjustment: dict[str, float], direction: int) -> None:
    final = engine.run(Adjustments(**adjustment)).points[-1].delta
    assert (final > 0) if direction > 0 else (final < 0)


def test_price_and_churn_example_from_demo_script(engine: ScenarioEngine) -> None:
    """PRD acceptance step 3: +10% price and +2 points churn."""
    result = engine.run(Adjustments(price_change_pct=10, churn_change_pts=2))
    assert result.scenario_runway_months is not None and result.base_runway_months is not None
    assert result.scenario_runway_months < result.base_runway_months
    assert "mrr_k" in result.lineage.formula
    assert result.lineage.inputs["cash"] == Decimal("1835125.06")


def test_scenario_is_fast(engine: ScenarioEngine) -> None:
    started = time.perf_counter()
    for pct in range(-20, 21, 5):
        engine.run(Adjustments(price_change_pct=pct, churn_change_pts=1))
    assert (time.perf_counter() - started) / 9 < 0.2  # PRD: < 200 ms per slider move


def test_cache_invalidates_on_new_data(tmp_path, engine: ScenarioEngine) -> None:  # type: ignore[no-untyped-def]
    from app.engine.ingest import ingest_directory

    db = FinanceDB(tmp_path / "ws")
    ingest_directory(db, g.SAMPLE)
    e = ScenarioEngine(db)
    first, _ = e.drivers()
    assert e.drivers()[0] is first
    ingest_directory(db, g.SAMPLE)  # reload bumps the version
    assert e.drivers()[0] is not first


def test_adjustment_validation() -> None:
    with pytest.raises(ValidationError):
        Adjustments(price_change_pct=-95)
    with pytest.raises(ValidationError):
        Adjustments(start_month=0)


def test_horizon_and_as_of(engine: ScenarioEngine) -> None:
    result = engine.run(Adjustments(), as_of="2025-12", horizon=24)
    assert result.as_of == "2025-12" and len(result.points) == 24 and result.points[0].month == "2026-01"
    with pytest.raises(MetricError):
        engine.run(Adjustments(), horizon=99)
    with pytest.raises(MetricError):
        engine.run(Adjustments(), as_of="2031-01")


def test_sensitivity_grid(engine: ScenarioEngine) -> None:
    prices, churns = [-10.0, 0.0, 10.0], [0.0, 1.0, 2.0]
    result = engine.sensitivity("price_change_pct", prices, "churn_change_pts", churns, output="cash_at_horizon")
    assert len(result.table) == 3 and all(len(row) == 3 for row in result.table)
    assert result.table[1][0] == result.base_value
    single = engine.run(Adjustments(price_change_pct=10, churn_change_pts=2))
    assert result.table[2][2] == single.points[-1].scenario_cash
    for row in result.table:  # more churn -> less cash
        assert row[0] > row[1] > row[2]  # type: ignore[operator]
    for j in range(3):  # higher price -> more cash
        assert result.table[0][j] < result.table[1][j] < result.table[2][j]  # type: ignore[operator]


def test_sensitivity_runway_output(engine: ScenarioEngine) -> None:
    result = engine.sensitivity("price_change_pct", [0.0], "new_hires", [0.0, 5.0], output="runway_months")
    assert result.table[0][0] == engine.run(Adjustments()).base_runway_months
    assert result.table[0][1] < result.table[0][0]  # type: ignore[operator]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"row_variable": "bogus"}, "unknown variable"),
        ({"column_variable": "price_change_pct"}, "must differ"),
        ({"output": "profit"}, "output"),
        ({"row_values": []}, "1 to 11"),
        ({"row_values": [-95.0]}, "not allowed"),  # review finding: was a pydantic ValidationError (HTTP 500)
    ],
)
def test_sensitivity_validation(engine: ScenarioEngine, kwargs: dict[str, object], message: str) -> None:
    args: dict[str, object] = {
        "row_variable": "price_change_pct",
        "row_values": [0.0],
        "column_variable": "churn_change_pts",
        "column_values": [0.0],
    }
    args.update(kwargs)
    with pytest.raises(MetricError, match=message):
        engine.sensitivity(**args)  # type: ignore[arg-type]


# --- growth modes, assumptions and reconciliation (founder feedback: projected runway 11.23 vs metric 10.65) -----
def test_growth_mode_none_adds_no_new_customers(engine: ScenarioEngine) -> None:
    d, _ = engine.drivers()
    result = engine.run(Adjustments(growth_mode="none"))
    mrr1 = d.mrr * (1 - d.churn)  # churn continues, nothing new arrives
    cash1 = d.cash + mrr1 + d.other_revenue - (d.variable_cogs_ratio + d.commission_ratio) * mrr1
    cash1 -= d.fixed_costs + d.marketing  # marketing programmes are still spent
    assert float(result.points[0].base_mrr) == pytest.approx(mrr1, abs=0.01)
    assert float(result.points[0].base_cash) == pytest.approx(cash1, abs=0.01)
    mrrs = [p.base_mrr for p in result.points]
    assert all(a > b for a, b in itertools.pairwise(mrrs))  # only churn: MRR falls every month
    assert result.base_runway_months == Decimal("9.69") and result.base_zero_cash_month == "2027-08"
    # The documented equivalent: acquisition_change_pct = -100 with the default trend mode.
    same = engine.run(Adjustments(acquisition_change_pct=-100))
    assert same.scenario_runway_months == result.base_runway_months
    assert result.growth_mode == "none" and "No new customers" in result.growth_assumption


def test_growth_mode_flat_holds_todays_run_rate(engine: ScenarioEngine) -> None:
    d, _ = engine.drivers()
    result = engine.run(Adjustments(growth_mode="flat"))
    assert {p.base_mrr for p in result.points} == {Decimal(str(d.mrr))}
    burn = d.cash - float(result.points[0].base_cash)
    deltas = [float(a.base_cash - b.base_cash) for a, b in itertools.pairwise(result.points)]
    assert deltas == pytest.approx([burn] * 11, abs=0.02)  # constant burn (points are rounded to cents)
    assert float(result.base_runway_months or 0) == pytest.approx(d.cash / burn, abs=0.005)


@pytest.mark.parametrize(
    ("month", "tolerance", "gap"),
    [(LATEST, "0.53", "0.06"), ("2025-12", "1.11", "0.86")],  # Dec 2025: receipts lag the Nov price uplift
)
def test_run_rate_projection_reconciles_with_runway_metric(
    engine: ScenarioEngine, month: str, tolerance: str, gap: str
) -> None:
    """With no growth the projection agrees with the runway metric (actual burn) within the stated tolerance."""
    rec = engine.run(Adjustments(growth_mode="flat"), as_of=month).reconciliation
    expected, _ = g.runway(month, 3)  # independent Decimal re-computation from the CSVs
    assert rec.runway_actual_burn_months == expected
    assert rec.actual_net_burn == g.net_burn(month, 3)
    assert rec.tolerance_months == g.q(expected * Decimal("0.05")) == Decimal(tolerance)  # 5 % of the metric
    assert rec.run_rate_runway_months is not None
    assert rec.basis_gap_months == rec.run_rate_runway_months - expected == Decimal(gap)
    assert abs(rec.basis_gap_months) <= rec.tolerance_months and rec.within_tolerance is True
    # The gap is explained by the burn on the two bases (bank cash vs P&L), which differ by under 5 %.
    assert rec.basis_gap_net_burn == g.net_burn(month, 3) - rec.run_rate_net_burn
    assert abs(rec.basis_gap_net_burn) / g.net_burn(month, 3) < Decimal("0.05")
    assert f"{abs(rec.basis_gap_net_burn):,.2f}/month" in rec.explanation


def test_reconciliation_walks_from_metric_to_projection(engine: ScenarioEngine) -> None:
    expected = {"trend": "11.23", "none": "9.69", "flat": "10.71"}
    for mode, projected in expected.items():
        result = engine.run(Adjustments(growth_mode=mode))  # type: ignore[arg-type]
        rec = result.reconciliation
        assert rec.growth_mode == mode
        assert rec.projected_runway_months == result.base_runway_months == Decimal(projected)
        assert rec.runway_actual_burn_months == Decimal("10.65")
        assert rec.basis_gap_months == Decimal("0.06")
        assert rec.runway_actual_burn_months + rec.basis_gap_months + rec.growth_gap_months == Decimal(projected)  # type: ignore[operator]
        assert "Runway (actual burn) is 10.65 months" in rec.explanation
        assert "172,280.47" in rec.explanation and "971.45/month (0.6%) of cash timing" in rec.explanation
        assert "within the 5% tolerance (0.53 months)" in rec.explanation
    trend = engine.run(Adjustments()).reconciliation
    assert trend.growth_gap_months == Decimal("0.52")
    assert "new customers keep arriving (5.33/month at 1,111.88 MRR each)" in trend.explanation
    assert "1.67% of customers churn" in trend.explanation


def test_reconciliation_when_runway_metric_is_undefined(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Not enough bank history for the 3-month metric: the gap is explained instead of compared."""
    from app.engine.ingest import ingest_directory

    db = FinanceDB(tmp_path / "ws")
    ingest_directory(db, g.SAMPLE)
    with db.connect(read_only=False) as con:
        con.execute("DELETE FROM bank_balance WHERE month < '2026-10'")
    rec = ScenarioEngine(db).run(Adjustments()).reconciliation
    assert rec.runway_actual_burn_months is None and rec.basis_gap_months is None and rec.within_tolerance is None
    assert "could not be computed" in rec.explanation
    assert rec.projected_runway_months is not None


def test_runway_labels_name_the_two_runways(engine: ScenarioEngine) -> None:
    result = engine.run(Adjustments())
    assert result.labels["runway_actual_burn_months"] == "Runway (actual burn)"
    assert result.labels["base_runway_months"] == "Projected runway (with growth assumptions)"
    schema = ScenarioResult.model_json_schema()["properties"]
    assert "with growth assumptions" in schema["base_runway_months"]["description"]


def test_assumptions_cover_every_driver_with_lineage(engine: ScenarioEngine) -> None:
    d, _ = engine.drivers()
    assumptions = {a.name: a for a in engine.run(Adjustments()).assumptions}
    assert list(assumptions) == list(ASSUMPTIONS)
    months = g.window(LATEST, 3)
    for name, a in assumptions.items():
        assert a.label and a.used and a.note is None
        assert a.lineage.metric == f"assumption.{name}"
        assert a.lineage.sql and a.lineage.source_rows and all(r.row_count for r in a.lineage.source_rows), name
        assert float(a.value) == pytest.approx(getattr(d, name), abs=0.0051 if a.unit != "ratio" else 0.000051)
        assert a.window == (LATEST if name in ("cash", "mrr", "cost_per_hire") else "2026-08..2026-10")
    assert assumptions["cash"].value == Decimal("1835125.06") and assumptions["cash"].unit == "USD"
    (bank,) = assumptions["cash"].lineage.source_rows
    assert (bank.table, bank.rows) == (
        "bank_balance",
        compact_ranges(g.csv_line("bank_balance", lambda r: r["month"] == LATEST)),
    )
    assert assumptions["new_customers"].value == g.q(Decimal(g.new_customers(months)) / 3)
    assert assumptions["new_customers"].unit == "count"
    assert assumptions["churn"].value == Decimal("0.0167") and assumptions["churn"].unit == "ratio"
    (spend,) = assumptions["marketing"].lineage.source_rows
    assert spend.rows == compact_ranges(g.csv_line("marketing_spend", lambda r: r["month"] in months))
    assert {r.table for r in assumptions["paid_cac"].lineage.source_rows} == {"marketing_spend", "customers"}


def test_assumption_sql_reruns_to_the_value(engine: ScenarioEngine, loaded_db: FinanceDB) -> None:
    assumptions = {a.name: a for a in engine.run(Adjustments()).assumptions}
    with loaded_db.connect() as con:
        (cash,) = con.execute(assumptions["cash"].lineage.sql[0]).fetchone()  # type: ignore[misc]
        (count,) = con.execute(assumptions["new_customers"].lineage.sql[0]).fetchone()  # type: ignore[misc]
    assert cash == assumptions["cash"].value
    assert g.q(Decimal(count) / 3) == assumptions["new_customers"].value


@pytest.mark.parametrize(
    ("mode", "unused"),
    [
        ("trend", set()),
        ("none", {"new_customers", "new_customer_arpa", "paid_cac"}),
        ("flat", {"new_customers", "new_customer_arpa", "paid_cac", "churn"}),
    ],
)
def test_assumptions_flag_drivers_the_growth_mode_replaces(engine: ScenarioEngine, mode: str, unused: set[str]) -> None:
    assumptions = engine.run(Adjustments(growth_mode=mode)).assumptions  # type: ignore[arg-type]
    assert {a.name for a in assumptions if not a.used} == unused
    assert all(a.note and mode in a.note for a in assumptions if not a.used)


def test_growth_mode_reaches_sensitivity_and_monte_carlo(engine: ScenarioEngine) -> None:
    flat = engine.sensitivity(
        "price_change_pct",
        [0.0],
        "churn_change_pts",
        [0.0],
        output="runway_months",
        base=Adjustments(growth_mode="flat"),
    )
    assert flat.base_value == flat.table[0][0] == Decimal("10.71")
    request = MonteCarloRequest(adjustments=Adjustments(growth_mode="none"), distributions={}, runs=20)
    result = run_monte_carlo(engine, request)
    assert result.growth_mode == "none" and result.runway_p50 == Decimal("9.69")
    assert result.runway_label == "Projected runway (with growth assumptions)"
    assert [a.name for a in result.assumptions] == list(ASSUMPTIONS)
    assert not {a.name: a for a in result.assumptions}["new_customers"].used
    with pytest.raises(ValidationError):
        Adjustments(growth_mode="hockey-stick")  # type: ignore[arg-type]


# --- Monte Carlo -----------------------------------------------------------------------------------------------
def test_monte_carlo_is_seeded_and_fast(engine: ScenarioEngine) -> None:
    run_monte_carlo(engine, MonteCarloRequest(runs=10))  # warm-up (lazy NumPy imports)
    started = time.perf_counter()
    first = run_monte_carlo(engine, MonteCarloRequest(runs=1000, seed=7))
    assert time.perf_counter() - started < 1.0  # PRD: 1,000 runs in under 1 s
    again = run_monte_carlo(engine, MonteCarloRequest(runs=1000, seed=7))
    other = run_monte_carlo(engine, MonteCarloRequest(runs=1000, seed=8))
    assert first.points == again.points and first.runway_p50 == again.runway_p50
    assert first.points != other.points


def test_monte_carlo_fan_is_ordered(engine: ScenarioEngine) -> None:
    result = run_monte_carlo(engine, MonteCarloRequest())
    assert len(result.points) == 12
    for p in result.points:
        assert p.p10 <= p.p50 <= p.p90
    assert result.runway_p10 <= result.runway_p50 <= result.runway_p90  # type: ignore[operator]
    assert 0 <= result.probability_cash_out_within_12_months <= 1
    assert "1000 seeded runs" in result.lineage.formula


def test_monte_carlo_without_uncertainty_equals_base(engine: ScenarioEngine) -> None:
    fixed = Adjustments(price_change_pct=5)
    result = run_monte_carlo(engine, MonteCarloRequest(adjustments=fixed, distributions={}, runs=50))
    scenario = engine.run(fixed)
    for fan, point in zip(result.points, scenario.points, strict=True):
        assert fan.p10 == fan.p50 == fan.p90 == point.scenario_cash
    assert result.runway_p50 == scenario.scenario_runway_months


def test_monte_carlo_probability_of_running_out(engine: ScenarioEngine) -> None:
    # Base runway is ~11.2 months: certain to run out within 12 months only if burn rises sharply.
    sure = run_monte_carlo(
        engine,
        MonteCarloRequest(adjustments=Adjustments(spend_change_monthly=200_000), distributions={}, runs=20),
    )
    assert sure.probability_cash_out_within_12_months == 1
    safe = run_monte_carlo(
        engine,
        MonteCarloRequest(adjustments=Adjustments(spend_change_monthly=-300_000), distributions={}, runs=20),
    )
    assert safe.probability_cash_out_within_12_months == 0
    assert safe.runway_p50 is None  # never runs out within the search window


def test_monte_carlo_distribution_kinds(engine: ScenarioEngine) -> None:
    request = MonteCarloRequest(
        distributions={
            "churn_change_pts": Distribution(kind="uniform", low=0, high=1),
            "cac_change_pct": Distribution(kind="triangular", low=-10, mode=0, high=40),
        },
        runs=200,
    )
    result = run_monte_carlo(engine, request)
    base = engine.run(Adjustments()).points[-1].base_cash
    assert result.points[-1].p90 <= base  # both distributions only make things worse


def test_monte_carlo_validation(engine: ScenarioEngine) -> None:
    with pytest.raises(MetricError, match="unknown variable"):
        run_monte_carlo(engine, MonteCarloRequest(distributions={"mood": Distribution(kind="normal", mean=0, sd=1)}))
    with pytest.raises(ValidationError):
        Distribution(kind="normal", mean=0)
    with pytest.raises(ValidationError):
        Distribution(kind="triangular", low=1, mode=0, high=2)
    with pytest.raises(ValidationError):
        MonteCarloRequest(runs=5)


def test_monte_carlo_runway_percentiles_are_simulated_values(engine: ScenarioEngine) -> None:
    """Review finding: interpolating towards the "never runs out" sentinel invented runways no run produced."""
    from app.engine.scenario import adjustment_arrays, project, runway_months

    request = MonteCarloRequest(
        distributions={"spend_change_monthly": Distribution(kind="uniform", low=-260_000, high=-150_000)},
        runs=400,
        seed=3,
    )
    result = run_monte_carlo(engine, request)
    d, _ = engine.drivers()
    rng = np.random.default_rng(3)
    draws = rng.uniform(-260_000, -150_000, 400)
    cash, _ = project(d, adjustment_arrays(400, Adjustments(), {"spend_change_monthly": draws}), 1, 120)
    simulated = {Decimal(str(round(float(r), 2))) for r in runway_months(d.cash, cash) if not np.isnan(r)}
    for p in (result.runway_p10, result.runway_p50, result.runway_p90):
        assert p is None or p in simulated


def test_monte_carlo_draws_are_clipped_to_valid_range(engine: ScenarioEngine) -> None:
    wild = MonteCarloRequest(distributions={"cac_change_pct": Distribution(kind="normal", mean=-80, sd=200)}, runs=500)
    result = run_monte_carlo(engine, wild)
    assert all(np.isfinite(float(p.p50)) for p in result.points)
