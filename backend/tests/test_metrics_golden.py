"""Golden tests: every metric routine against an independent Decimal re-computation from the sample CSVs."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.duckdb_engine import FinanceDB, NoDataError
from app.engine.lineage import compact_ranges
from app.engine.metrics import METRICS, MetricError, MetricsEngine
from tests import golden as g

LATEST = "2026-10"
# A second as-of month mid-window, after the price uplift (2025-11) and the funding round (2025-08).
MID = "2025-12"


@pytest.fixture(scope="module")
def engine(loaded_db: FinanceDB) -> MetricsEngine:
    return MetricsEngine(loaded_db, "USD")


def value(engine: MetricsEngine, name: str, month: str | None = None, window: int | None = None) -> Decimal | None:
    return engine.compute(name, month, window).value


@pytest.mark.parametrize("month", [LATEST, MID])
@pytest.mark.parametrize("window", [1, 3, 6])
def test_burn(engine: MetricsEngine, month: str, window: int) -> None:
    assert value(engine, "gross_burn", month, window) == g.gross_burn(month, window)
    assert value(engine, "net_burn", month, window) == g.net_burn(month, window)


@pytest.mark.parametrize("month", [LATEST, MID])
def test_runway(engine: MetricsEngine, month: str) -> None:
    result = engine.compute("runway", month)
    expected, zero_month = g.runway(month, 3)
    assert result.value == expected
    assert result.detail["zero_cash_month"] == zero_month


def test_headline_numbers_match_handover() -> None:
    """The numbers quoted in HANDOVER.md's Windows checklist (the founder checks these in Excel)."""
    assert g.net_burn(LATEST, 3) == Decimal("172280.47")
    assert g.gross_burn(LATEST, 3) == Decimal("428612.47")
    assert g.runway(LATEST, 3) == (Decimal("10.65"), "2027-09")
    assert g.mrr(LATEST) == (Decimal("255344.27"), 142)
    assert g.gross_margin_raw([LATEST]) == Decimal("0.7213")


def test_runway_lineage_points_at_bank_rows(engine: MetricsEngine) -> None:
    lineage = engine.compute("runway").lineage
    assert lineage.source_files == ["bank_balance.csv"]
    (ref,) = lineage.source_rows
    expected = g.csv_line("bank_balance", lambda r: r["month"] in g.window(LATEST, 3))
    assert ref.rows == compact_ranges(expected) == "23-25"
    assert ref.row_count == 3
    assert any("closing_balance" in sql for sql in lineage.sql)
    assert lineage.inputs["closing_cash"] == Decimal("1835125.06")
    assert lineage.period == "2026-08..2026-10"


def test_runway_undefined_when_cash_positive(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.engine.ingest import ingest_file

    db = FinanceDB(tmp_path / "ws")
    path = tmp_path / "bank_balance.csv"
    path.write_text(
        "month,opening_balance,customer_receipts,cash_in,cash_out,closing_balance\n"
        "2026-01,100.00,50.00,50.00,40.00,110.00\n"
        "2026-02,110.00,50.00,50.00,40.00,120.00\n"
        "2026-03,120.00,50.00,50.00,40.00,130.00\n",
        encoding="utf-8",
    )
    ingest_file(db, path)
    result = MetricsEngine(db).compute("runway")
    assert result.value is None
    assert "Not burning" in (result.note or "")
    assert MetricsEngine(db).compute("net_burn").value == Decimal("-10.00")


@pytest.mark.parametrize("month", [LATEST, MID, "2024-11"])
def test_mrr_arr_arpa(engine: MetricsEngine, month: str) -> None:
    total, customers = g.mrr(month)
    assert value(engine, "mrr", month) == g.q(total)
    assert value(engine, "arr", month) == g.q(total * 12)
    assert value(engine, "arpa", month) == g.q(total / customers)
    assert engine.compute("mrr", month).detail["active_customers"] == customers


def test_subscription_revenue_reconciles_with_pnl() -> None:
    """Identity from sample_data/README.md that makes MRR checkable against the P&L sheet."""
    pnl = g.pnl_total([LATEST], lambda r: r["account"] == "Subscription revenue")
    assert pnl == g.mrr(LATEST)[0]


@pytest.mark.parametrize(("month", "window"), [(LATEST, 1), (LATEST, 3), (MID, 1), (MID, 12)])
def test_growth(engine: MetricsEngine, month: str, window: int) -> None:
    start = g.shift(month, -window)
    rev = float(g.revenue([month]) / g.revenue([start])) ** (1 / window) - 1
    mrr_growth = float(g.mrr(month)[0] / g.mrr(start)[0]) ** (1 / window) - 1
    assert abs(float(value(engine, "revenue_growth", month, window) or 0) - rev) <= 0.00006
    assert abs(float(value(engine, "mrr_growth", month, window) or 0) - mrr_growth) <= 0.00006


def test_growth_needs_the_earlier_month(engine: MetricsEngine) -> None:
    with pytest.raises(MetricError, match="does not cover"):
        engine.compute("revenue_growth", "2024-11", 1)


@pytest.mark.parametrize(("month", "window"), [(LATEST, 1), (LATEST, 3), (MID, 1)])
def test_gross_margin(engine: MetricsEngine, month: str, window: int) -> None:
    assert value(engine, "gross_margin", month, window) == g.gross_margin_raw(g.window(month, window))


@pytest.mark.parametrize(("month", "window"), [(LATEST, 3), (MID, 3), (LATEST, 6)])
def test_cac(engine: MetricsEngine, month: str, window: int) -> None:
    assert value(engine, "cac", month, window) == g.cac(month, window)


def test_cac_counts_exactly_the_sales_and_marketing_accounts(engine: MetricsEngine) -> None:
    sm = engine.compute("cac").lineage.inputs["sales_marketing_cost"]
    assert sm == g.pnl_total(g.window(LATEST, 3), lambda r: r["account"] in g.SM_ACCOUNTS)


def test_cac_by_channel(engine: MetricsEngine) -> None:
    result = engine.compute("cac_by_channel")
    months = g.window(LATEST, 3)
    for channel in ("Paid Search", "Content & SEO", "Outbound"):
        spend = sum(
            Decimal(r["spend"]) for r in g.rows("marketing_spend") if r["month"] in months and r["channel"] == channel
        )
        assert result.detail[channel] == g.q(spend / g.new_customers(months, channel))
    total_spend = sum(Decimal(r["spend"]) for r in g.rows("marketing_spend") if r["month"] in months)
    assert result.value == g.q(total_spend / g.new_customers(months))


@pytest.mark.parametrize(("month", "window"), [(LATEST, 3), (MID, 3), (LATEST, 12)])
def test_churn(engine: MetricsEngine, month: str, window: int) -> None:
    start, lost, start_mrr, lost_mrr = g.churn_parts(month, window)
    assert value(engine, "logo_churn", month, window) == g.q(Decimal(lost) / Decimal(start), g.RATIO)
    assert value(engine, "revenue_churn", month, window) == g.q(lost_mrr / start_mrr, g.RATIO)


def test_logo_churn_agrees_with_customer_table() -> None:
    """Customers lost per subscriptions = customers whose churn_month falls in the window."""
    months = g.window(LATEST, 3)
    _, lost, _, _ = g.churn_parts(LATEST, 3)
    assert lost == sum(1 for c in g.rows("customers") if c["churn_month"] in months)


@pytest.mark.parametrize(("month", "lookback"), [(LATEST, 12), (LATEST, 6), (MID, 12)])
def test_nrr(engine: MetricsEngine, month: str, lookback: int) -> None:
    assert value(engine, "nrr", month, lookback) == g.nrr(month, lookback)


@pytest.mark.parametrize("month", [LATEST, MID])
def test_unit_economics(engine: MetricsEngine, month: str) -> None:
    expected = g.unit_economics(month, 3)
    assert value(engine, "ltv", month) == expected["ltv"]
    assert value(engine, "ltv_cac", month) == expected["ltv_cac"]
    assert value(engine, "cac_payback", month) == expected["cac_payback"]


@pytest.mark.parametrize(("month", "window"), [(LATEST, 1), (LATEST, 3), (MID, 1)])
def test_headcount_cost(engine: MetricsEngine, month: str, window: int) -> None:
    result = engine.compute("headcount_cost", month, window)
    assert result.value == g.payroll(month, window)
    assert result.detail["active_headcount"] == g.active_headcount(month)


def test_every_metric_has_lineage_with_sql_and_rows(engine: MetricsEngine) -> None:
    for name in METRICS:
        result = engine.compute(name)
        assert result.lineage.metric == name
        assert result.lineage.sql, name
        assert result.lineage.source_rows, name
        assert all(ref.row_count > 0 for ref in result.lineage.source_rows), name
        assert result.lineage.formula, name


def test_lineage_sql_reruns_to_the_same_numbers(engine: MetricsEngine, loaded_db: FinanceDB) -> None:
    """The SQL in the lineage is what was executed: re-running it gives the same intermediate values."""
    lineage = engine.compute("gross_burn").lineage
    with loaded_db.connect() as con:
        (total,) = con.execute(lineage.sql[-1]).fetchone()  # type: ignore[misc]
    assert total == lineage.inputs["total_cash_out"]


def test_summary_matches_compute(engine: MetricsEngine) -> None:
    results, unavailable = engine.summary(["mrr", "runway"])
    assert [r.value for r in results] == [value(engine, "mrr"), value(engine, "runway")]
    assert unavailable == {}


def test_summary_reports_metrics_it_cannot_compute(engine: MetricsEngine) -> None:
    """Review finding: one metric without enough history must not fail the whole dashboard."""
    results, unavailable = engine.summary(["mrr", "net_burn", "gross_margin"], "2024-11")
    assert [r.metric for r in results] == ["mrr", "gross_margin"]
    assert "does not cover" in unavailable["net_burn"]


@pytest.mark.parametrize(
    ("name", "month", "window", "message"),
    [
        ("nope", None, None, "Unknown metric"),
        ("mrr", "2030-01", None, "outside the data"),
        ("mrr", "2026-13", None, "YYYY-MM"),
        ("net_burn", "2024-12", 3, "does not cover"),
        ("net_burn", None, 0, "window"),
    ],
)
def test_bad_inputs(engine: MetricsEngine, name: str, month: str | None, window: int | None, message: str) -> None:
    with pytest.raises(MetricError, match=message):
        engine.compute(name, month, window)


def test_no_data(empty_db: FinanceDB) -> None:
    with pytest.raises(NoDataError):
        MetricsEngine(empty_db).compute("mrr")


def test_json_numbers_are_plain_numbers(engine: MetricsEngine) -> None:
    payload = engine.compute("runway").model_dump(mode="json")
    assert payload["value"] == 10.65
    assert payload["lineage"]["inputs"]["net_burn"] == 172280.47
