"""Pre-built financial metric routines (PRD §F1). Every routine returns a `MetricResult` with full `Lineage`.

All arithmetic on money happens in DuckDB (exact DECIMAL sums) or in Python `Decimal`, never in an LLM. Each
routine takes the month the metric is "as of" (default: the latest month in the bank data) and, for flow metrics, a
trailing `window` of months. Defaults are listed in `METRICS`; a founder can re-run any number by hand from the SQL
and source rows in its lineage.

Definitions (window W = the W months ending at the as-of month m):
- gross_burn: average monthly `bank_balance.cash_out` over W.
- net_burn: average monthly (cash_out - customer_receipts) over W. Operating burn, so financing inflows are excluded.
- runway: closing cash at m / net_burn(W). Zero-cash month = m + ceil(runway). Undefined when not burning.
- mrr / arr: sum of `subscriptions.mrr` in m (ARR = 12 x MRR). arpa: MRR / active customers.
- revenue_growth / mrr_growth: compound monthly growth over W: (x_m / x_{m-W})^(1/W) - 1 (W=1 is month on month).
- gross_margin: (Revenue - COGS) / Revenue from the P&L, summed over W.
- cac: sales & marketing cost over W / new customers over W. S&M cost = P&L operating-expense accounts whose name
  contains "sales", "marketing" or "commission". New customers = `customers.signup_month` in W.
- cac_by_channel: paid acquisition cost per channel = `marketing_spend.spend` / new customers from that channel.
- logo_churn: customers lost / customers active at the start of each month, summed over W (from subscriptions).
- revenue_churn: gross MRR churn = (MRR lost from churned customers + contraction) / starting MRR, summed over W.
- nrr: MRR at m from customers active at m-L / their MRR at m-L (L = lookback, default 12).
- ltv: ARPA x gross_margin(W) / logo_churn(W). ltv_cac: LTV / CAC. cac_payback: CAC / (ARPA x gross_margin) months.
- headcount_cost: average monthly payroll (P&L accounts containing "payroll") over W, plus active headcount at m.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

import duckdb

from app.engine.duckdb_engine import FinanceDB, NoDataError
from app.engine.lineage import Lineage, MetricResult, SourceRef, compact_ranges

CENT = Decimal("0.01")
RATIO = Decimal("0.0001")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SM_ACCOUNT_FILTER = (
    "category = 'Operating expense' AND (lower(account) LIKE '%sales%' OR lower(account) LIKE '%marketing%' "
    "OR lower(account) LIKE '%commission%')"
)
PAYROLL_FILTER = "lower(account) LIKE '%payroll%'"
RECEIPTS = "coalesce(customer_receipts, cash_in - coalesce(financing_inflows, 0))"


class MetricError(ValueError):
    """Bad input to a metric routine (unknown metric, month outside the data, window too long)."""


def shift_month(month: str, months: int) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    y, m = divmod(mon - 1 + months, 12)
    return f"{year + y:04d}-{m + 1:02d}"


def month_window(end: str, window: int) -> list[str]:
    return [shift_month(end, -i) for i in range(window - 1, -1, -1)]


def _in(months: list[str]) -> str:
    # Months are validated against MONTH_RE before they reach SQL, so inlining them is safe and keeps the SQL in the
    # lineage exactly re-runnable.
    for m in months:
        if not MONTH_RE.match(m):
            raise MetricError(f"invalid month {m!r}")
    return "(" + ", ".join(f"'{m}'" for m in months) + ")"


def _dec(value: Any) -> Decimal:
    if value is None:
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _q(value: Decimal, step: Decimal = CENT) -> Decimal:
    return value.quantize(step, rounding=ROUND_HALF_UP)


def _div(a: Decimal, b: Decimal, step: Decimal = RATIO) -> Decimal | None:
    return None if b == 0 else _q(a / b, step)


def _period(months: list[str]) -> str:
    return months[0] if len(months) == 1 else f"{months[0]}..{months[-1]}"


class _Trace:
    """Runs SQL on one connection and records every statement and the source rows that fed the result."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con = con
        self.sql: list[str] = []
        self.sources: list[SourceRef] = []
        self._seen: set[tuple[str, str]] = set()

    def scalar(self, sql: str) -> Any:
        self.sql.append(sql)
        row = self.con.execute(sql).fetchone()
        return row[0] if row else None

    def rows(self, sql: str) -> list[tuple[Any, ...]]:
        self.sql.append(sql)
        return self.con.execute(sql).fetchall()

    def source(self, table: str, where: str) -> None:
        if (table, where) in self._seen:
            return
        self._seen.add((table, where))
        for file, sheet, rows in self.con.execute(
            f'SELECT _source_file, _source_sheet, list(_source_row) FROM "{table}" WHERE {where} GROUP BY ALL '
            "ORDER BY 1, 2"
        ).fetchall():
            self.sources.append(
                SourceRef(table=table, file=file, sheet=sheet, rows=compact_ranges(rows), row_count=len(rows))
            )

    def lineage(self, metric: str, formula: str, inputs: dict[str, Decimal | None], period: str) -> Lineage:
        return Lineage(
            metric=metric,
            sql=list(self.sql),
            source_files=sorted({s.file for s in self.sources}),
            source_rows=list(self.sources),
            formula=formula,
            inputs=inputs,
            period=period,
        )


@dataclass(frozen=True)
class MetricDef:
    name: str
    label: str
    default_window: int | None  # None: point-in-time metric (window does not apply)
    description: str


METRICS: dict[str, MetricDef] = {
    d.name: d
    for d in (
        MetricDef("gross_burn", "Gross burn (monthly)", 3, "Average monthly cash out"),
        MetricDef("net_burn", "Net burn (monthly)", 3, "Average monthly cash out minus customer receipts"),
        MetricDef("runway", "Runway", 3, "Months of cash left at the current net burn, and the zero-cash month"),
        MetricDef("mrr", "MRR", None, "Monthly recurring revenue"),
        MetricDef("arr", "ARR", None, "Annual recurring revenue (12 x MRR)"),
        MetricDef("arpa", "ARPA", None, "Average MRR per active customer"),
        MetricDef("revenue_growth", "Revenue growth (monthly)", 1, "Compound monthly growth of P&L revenue"),
        MetricDef("mrr_growth", "MRR growth (monthly)", 1, "Compound monthly growth of MRR"),
        MetricDef("gross_margin", "Gross margin", 1, "(Revenue - COGS) / Revenue"),
        MetricDef("cac", "CAC (blended)", 3, "Sales & marketing cost per new customer"),
        MetricDef("cac_by_channel", "CAC by channel (paid)", 3, "Marketing programme spend per new customer"),
        MetricDef("logo_churn", "Logo churn (monthly)", 3, "Share of customers lost per month"),
        MetricDef("revenue_churn", "Gross revenue churn (monthly)", 3, "Share of MRR lost per month"),
        MetricDef("nrr", "Net revenue retention", 12, "MRR today from customers of L months ago / their MRR then"),
        MetricDef("ltv", "LTV", 3, "ARPA x gross margin / monthly logo churn"),
        MetricDef("ltv_cac", "LTV:CAC", 3, "Lifetime value / CAC"),
        MetricDef("cac_payback", "CAC payback", 3, "Months of gross profit to recover CAC"),
        MetricDef("headcount_cost", "Headcount cost (monthly)", 1, "Average monthly payroll and active staff"),
    )
}

SUMMARY_METRICS = ("mrr", "arr", "net_burn", "gross_burn", "runway", "gross_margin", "revenue_growth", "cac", "ltv_cac")


class MetricsEngine:
    def __init__(self, db: FinanceDB, currency: str = "USD") -> None:
        self.db = db
        self.currency = currency

    # -- public API ---------------------------------------------------------------------------------------------
    def compute(self, name: str, month: str | None = None, window: int | None = None) -> MetricResult:
        with self.db.connect() as con:
            return self._compute(con, name, month, window)

    def summary(self, names: list[str], month: str | None = None) -> tuple[list[MetricResult], dict[str, str]]:
        """Compute each metric independently: one that cannot be computed is reported, not fatal."""
        results: list[MetricResult] = []
        unavailable: dict[str, str] = {}
        with self.db.connect() as con:
            for name in names:
                try:
                    results.append(self._compute(con, name, month, None))
                except (MetricError, NoDataError) as exc:
                    unavailable[name] = str(exc)
        return results, unavailable

    def available_months(self) -> list[str]:
        with self.db.connect() as con:
            self._require(con, "bank_balance")
            return [m for (m,) in con.execute("SELECT DISTINCT month FROM bank_balance ORDER BY month").fetchall()]

    # -- plumbing -----------------------------------------------------------------------------------------------
    def _compute(
        self, con: duckdb.DuckDBPyConnection, name: str, month: str | None, window: int | None
    ) -> MetricResult:
        definition = METRICS.get(name)
        if definition is None:
            raise MetricError(f"Unknown metric {name!r}; available: {', '.join(METRICS)}")
        routine: Callable[[_Trace, str, int], MetricResult] = getattr(self, f"_m_{name}")
        months = self._months(con)
        as_of = month or months[-1]
        if not MONTH_RE.match(as_of):
            raise MetricError(f"month must be YYYY-MM, got {as_of!r}")
        if as_of not in months:
            raise MetricError(f"{as_of} is outside the data ({months[0]}..{months[-1]})")
        w = window if window is not None else (definition.default_window or 1)
        if not 1 <= w <= 36:
            raise MetricError("window must be between 1 and 36 months")
        return routine(_Trace(con), as_of, w)

    def _months(self, con: duckdb.DuckDBPyConnection) -> list[str]:
        self._require(con, "bank_balance")
        months = [m for (m,) in con.execute("SELECT DISTINCT month FROM bank_balance ORDER BY month").fetchall()]
        if not months:
            raise NoDataError("bank_balance has no rows")
        return months

    @staticmethod
    def _require(con: duckdb.DuckDBPyConnection, *tables: str) -> None:
        present = {
            t
            for (t,) in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
        missing = [t for t in tables if t not in present]
        if missing:
            raise NoDataError(f"Missing table(s): {', '.join(missing)}. Load the sample data or upload them.")

    def _window_present(self, t: _Trace, table: str, months: list[str]) -> None:
        months = sorted(set(months))
        found = t.con.execute(f"SELECT count(DISTINCT month) FROM {table} WHERE month IN {_in(months)}").fetchone()
        if not found or found[0] < len(months):
            raise MetricError(f"{table} does not cover every month of {_period(months)}")

    def _result(
        self,
        t: _Trace,
        name: str,
        value: Decimal | None,
        unit: str,
        as_of: str,
        months: list[str],
        formula: str,
        inputs: dict[str, Decimal | None],
        note: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> MetricResult:
        return MetricResult(
            metric=name,
            label=METRICS[name].label,
            value=value,
            unit=unit,
            as_of=as_of,
            note=note,
            detail=detail or {},
            lineage=t.lineage(name, formula, inputs, _period(months)),
        )

    # -- building blocks (each records its SQL and sources on the trace) -----------------------------------------
    def _cash_out(self, t: _Trace, months: list[str]) -> Decimal:
        self._require(t.con, "bank_balance")
        self._window_present(t, "bank_balance", months)
        t.source("bank_balance", f"month IN {_in(months)}")
        return _dec(t.scalar(f"SELECT sum(cash_out) FROM bank_balance WHERE month IN {_in(months)}"))

    def _receipts(self, t: _Trace, months: list[str]) -> Decimal:
        return _dec(t.scalar(f"SELECT sum({RECEIPTS}) FROM bank_balance WHERE month IN {_in(months)}"))

    def _pnl_sum(self, t: _Trace, months: list[str], where: str) -> Decimal:
        self._require(t.con, "pnl")
        self._window_present(t, "pnl", months)
        cond = f"month IN {_in(months)} AND {where}"
        t.source("pnl", cond)
        return _dec(t.scalar(f"SELECT sum(amount) FROM pnl WHERE {cond}"))

    def _mrr_at(self, t: _Trace, month: str) -> tuple[Decimal, int]:
        self._require(t.con, "subscriptions")
        t.source("subscriptions", f"month = '{month}'")
        row = t.rows(f"SELECT sum(mrr), count(DISTINCT customer_id) FROM subscriptions WHERE month = '{month}'")[0]
        return _dec(row[0]), int(row[1] or 0)

    def _new_customers(self, t: _Trace, months: list[str], channel_column: bool = False) -> dict[str, int]:
        self._require(t.con, "customers")
        cond = f"signup_month IN {_in(months)}"
        t.source("customers", cond)
        if channel_column:
            rows = t.rows(
                f"SELECT coalesce(acquisition_channel, '(unknown)'), count(*) FROM customers WHERE {cond} "
                "GROUP BY 1 ORDER BY 1"
            )
            return {str(k): int(v) for k, v in rows}
        return {"all": int(t.scalar(f"SELECT count(*) FROM customers WHERE {cond}") or 0)}

    def _churn_parts(self, t: _Trace, months: list[str]) -> tuple[int, int, Decimal, Decimal]:
        """(customers at start, customers lost, starting MRR, MRR lost incl. contraction), summed over months."""
        self._require(t.con, "subscriptions")
        prev = [shift_month(m, -1) for m in months]
        self._window_present(t, "subscriptions", prev + months)
        t.source("subscriptions", f"month IN {_in(sorted(set(prev + months)))}")
        sql = f"""WITH cur AS (
  SELECT month, customer_id, sum(mrr) AS mrr FROM subscriptions WHERE month IN {_in(months)} GROUP BY ALL
), prev AS (
  SELECT strftime(CAST(month || '-01' AS DATE) + INTERVAL 1 MONTH, '%Y-%m') AS month, customer_id, sum(mrr) AS mrr
  FROM subscriptions WHERE month IN {_in(prev)} GROUP BY ALL
)
SELECT count(*) AS starting_customers,
       count(*) FILTER (WHERE cur.customer_id IS NULL) AS lost_customers,
       sum(prev.mrr) AS starting_mrr,
       sum(greatest(prev.mrr - coalesce(cur.mrr, 0), 0)) AS lost_mrr
FROM prev LEFT JOIN cur USING (month, customer_id)"""
        start, lost, start_mrr, lost_mrr = t.rows(sql)[0]
        return int(start or 0), int(lost or 0), _dec(start_mrr), _dec(lost_mrr)

    # -- routines -----------------------------------------------------------------------------------------------
    def _m_gross_burn(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        out = self._cash_out(t, months)
        value = _q(out / w)
        return self._result(
            t,
            "gross_burn",
            value,
            self.currency,
            m,
            months,
            f"sum(bank_balance.cash_out) / {w}",
            {"total_cash_out": out, "months": Decimal(w)},
        )

    def _net_burn(self, t: _Trace, months: list[str]) -> tuple[Decimal, Decimal, Decimal]:
        out = self._cash_out(t, months)
        receipts = self._receipts(t, months)
        return _q((out - receipts) / len(months)), out, receipts

    def _m_net_burn(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        value, out, receipts = self._net_burn(t, months)
        return self._result(
            t,
            "net_burn",
            value,
            self.currency,
            m,
            months,
            f"(sum(cash_out) - sum(customer_receipts)) / {w}  (financing inflows excluded)",
            {"total_cash_out": out, "total_customer_receipts": receipts, "months": Decimal(w)},
            note="Negative means the business generated cash" if value < 0 else None,
        )

    def _m_runway(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        burn, _, _ = self._net_burn(t, months)
        cash = _dec(t.scalar(f"SELECT closing_balance FROM bank_balance WHERE month = '{m}' ORDER BY _source_row DESC"))
        inputs: dict[str, Decimal | None] = {"closing_cash": cash, "net_burn": burn}
        formula = f"closing_balance[{m}] / net_burn  (net_burn = average over {w} month(s))"
        if burn <= 0:
            return self._result(
                t,
                "runway",
                None,
                "months",
                m,
                months,
                formula,
                inputs,
                note="Not burning cash: runway is unlimited at the current rate",
                detail={"zero_cash_month": None},
            )
        runway = _q(max(cash, Decimal(0)) / burn)  # already out of cash: 0 months
        zero_month = shift_month(m, math.ceil(runway)) if cash > 0 else m
        return self._result(
            t,
            "runway",
            runway,
            "months",
            m,
            months,
            formula,
            inputs,
            detail={"zero_cash_month": zero_month, "closing_cash": cash, "net_burn": burn},
        )

    def _m_mrr(self, t: _Trace, m: str, w: int) -> MetricResult:
        mrr, customers = self._mrr_at(t, m)
        return self._result(
            t,
            "mrr",
            _q(mrr),
            self.currency,
            m,
            [m],
            f"sum(subscriptions.mrr) for {m}",
            {"mrr": mrr, "active_customers": Decimal(customers)},
            detail={"active_customers": customers},
        )

    def _m_arr(self, t: _Trace, m: str, w: int) -> MetricResult:
        mrr, customers = self._mrr_at(t, m)
        return self._result(
            t,
            "arr",
            _q(mrr * 12),
            self.currency,
            m,
            [m],
            f"12 x sum(subscriptions.mrr) for {m}",
            {"mrr": mrr},
            detail={"active_customers": customers},
        )

    def _m_arpa(self, t: _Trace, m: str, w: int) -> MetricResult:
        mrr, customers = self._mrr_at(t, m)
        return self._result(
            t,
            "arpa",
            None if customers == 0 else _q(mrr / customers),
            self.currency,
            m,
            [m],
            "MRR / active customers",
            {"mrr": mrr, "active_customers": Decimal(customers)},
        )

    @staticmethod
    def _cmgr(end: Decimal, start: Decimal, w: int) -> Decimal | None:
        if start <= 0 or end < 0:
            return None
        with localcontext() as ctx:
            ctx.prec = 28
            growth = (end / start) ** (Decimal(1) / Decimal(w)) - 1
        return _q(growth, RATIO)

    def _m_revenue_growth(self, t: _Trace, m: str, w: int) -> MetricResult:
        start_month = shift_month(m, -w)
        end_rev = self._pnl_sum(t, [m], "category = 'Revenue'")
        start_rev = self._pnl_sum(t, [start_month], "category = 'Revenue'")
        return self._result(
            t,
            "revenue_growth",
            self._cmgr(end_rev, start_rev, w),
            "ratio",
            m,
            [start_month, m],
            f"(revenue[{m}] / revenue[{start_month}])^(1/{w}) - 1",
            {"revenue_end": end_rev, "revenue_start": start_rev, "months": Decimal(w)},
        )

    def _m_mrr_growth(self, t: _Trace, m: str, w: int) -> MetricResult:
        start_month = shift_month(m, -w)
        self._window_present(t, "subscriptions", [start_month, m])
        end_mrr, _ = self._mrr_at(t, m)
        start_mrr, _ = self._mrr_at(t, start_month)
        return self._result(
            t,
            "mrr_growth",
            self._cmgr(end_mrr, start_mrr, w),
            "ratio",
            m,
            [start_month, m],
            f"(mrr[{m}] / mrr[{start_month}])^(1/{w}) - 1",
            {"mrr_end": end_mrr, "mrr_start": start_mrr, "months": Decimal(w)},
        )

    def _gross_margin(self, t: _Trace, months: list[str]) -> tuple[Decimal | None, Decimal, Decimal]:
        revenue = self._pnl_sum(t, months, "category = 'Revenue'")
        cogs = self._pnl_sum(t, months, "category = 'COGS'")
        return _div(revenue - cogs, revenue), revenue, cogs

    def _m_gross_margin(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        gm, revenue, cogs = self._gross_margin(t, months)
        return self._result(
            t,
            "gross_margin",
            gm,
            "ratio",
            m,
            months,
            "(sum(Revenue) - sum(COGS)) / sum(Revenue)",
            {"revenue": revenue, "cogs": cogs},
        )

    def _cac(self, t: _Trace, months: list[str]) -> tuple[Decimal | None, Decimal, int]:
        cost = self._pnl_sum(t, months, SM_ACCOUNT_FILTER)
        new = self._new_customers(t, months)["all"]
        return (None if new == 0 else _q(cost / new)), cost, new

    def _m_cac(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        cac, cost, new = self._cac(t, months)
        return self._result(
            t,
            "cac",
            cac,
            self.currency,
            m,
            months,
            "sum(P&L sales & marketing operating expense) / count(customers with signup_month in window)",
            {"sales_marketing_cost": cost, "new_customers": Decimal(new)},
            note="No new customers in the window" if new == 0 else None,
        )

    def _m_cac_by_channel(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        self._require(t.con, "marketing_spend")
        cond = f"month IN {_in(months)}"
        t.source("marketing_spend", cond)
        spend = {
            str(c): _dec(s)
            for c, s in t.rows(f"SELECT channel, sum(spend) FROM marketing_spend WHERE {cond} GROUP BY 1 ORDER BY 1")
        }
        new = self._new_customers(t, months, channel_column=True)
        detail: dict[str, Any] = {}
        inputs: dict[str, Decimal | None] = {}
        for channel in sorted(set(spend) | set(new)):
            n = new.get(channel, 0)
            s = spend.get(channel, Decimal(0))
            detail[channel] = None if n == 0 else _q(s / n)
            inputs[f"{channel} spend"] = s
            inputs[f"{channel} new customers"] = Decimal(n)
        total_spend, total_new = sum(spend.values(), Decimal(0)), sum(new.values())
        return self._result(
            t,
            "cac_by_channel",
            None if total_new == 0 else _q(total_spend / total_new),
            self.currency,
            m,
            months,
            "per channel: sum(marketing_spend.spend) / new customers from that channel; value = all channels",
            inputs,
            detail=detail,
        )

    def _m_logo_churn(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        start, lost, _, _ = self._churn_parts(t, months)
        return self._result(
            t,
            "logo_churn",
            _div(Decimal(lost), Decimal(start)),
            "ratio",
            m,
            months,
            "customers with MRR in the previous month but none this month / customers with MRR in the previous "
            "month, summed over the window",
            {"customers_lost": Decimal(lost), "customers_at_start": Decimal(start)},
        )

    def _m_revenue_churn(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        _, _, start_mrr, lost_mrr = self._churn_parts(t, months)
        return self._result(
            t,
            "revenue_churn",
            _div(lost_mrr, start_mrr),
            "ratio",
            m,
            months,
            "sum(max(previous MRR - current MRR, 0) per customer) / sum(previous MRR), over the window",
            {"mrr_lost": lost_mrr, "mrr_at_start": start_mrr},
        )

    def _m_nrr(self, t: _Trace, m: str, w: int) -> MetricResult:
        base = shift_month(m, -w)
        self._require(t.con, "subscriptions")
        self._window_present(t, "subscriptions", [base, m])
        t.source("subscriptions", f"month IN {_in([base, m])}")
        sql = f"""WITH cohort AS (
  SELECT customer_id, sum(mrr) AS mrr FROM subscriptions WHERE month = '{base}' GROUP BY 1
), now AS (SELECT customer_id, sum(mrr) AS mrr FROM subscriptions WHERE month = '{m}' GROUP BY 1)
SELECT sum(cohort.mrr), coalesce(sum(now.mrr), 0) FROM cohort LEFT JOIN now USING (customer_id)"""
        start_mrr, retained = (_dec(v) for v in t.rows(sql)[0])
        return self._result(
            t,
            "nrr",
            _div(retained, start_mrr),
            "ratio",
            m,
            [base, m],
            f"MRR in {m} of customers active in {base} / their MRR in {base}",
            {"cohort_mrr_then": start_mrr, "cohort_mrr_now": retained, "lookback_months": Decimal(w)},
        )

    def _unit_economics(self, t: _Trace, m: str, w: int) -> dict[str, Decimal | None]:
        months = month_window(m, w)
        mrr, customers = self._mrr_at(t, m)
        arpa = None if customers == 0 else mrr / customers
        gm, _, _ = self._gross_margin(t, months)
        start, lost, _, _ = self._churn_parts(t, months)
        churn = None if start == 0 else Decimal(lost) / Decimal(start)
        cac, _, _ = self._cac(t, months)
        ltv = None if arpa is None or gm is None or not churn else _q(arpa * gm / churn)
        monthly_gp = None if arpa is None or gm is None else arpa * gm
        return {
            "arpa": None if arpa is None else _q(arpa),
            "gross_margin": gm,
            "logo_churn": None if churn is None else _q(churn, RATIO),
            "cac": cac,
            "ltv": ltv,
            "ltv_cac": None if ltv is None or not cac else _q(ltv / cac, CENT),
            "cac_payback": None if cac is None or not monthly_gp else _q(cac / monthly_gp, CENT),
        }

    def _m_ltv(self, t: _Trace, m: str, w: int) -> MetricResult:
        u = self._unit_economics(t, m, w)
        return self._result(
            t,
            "ltv",
            u["ltv"],
            self.currency,
            m,
            month_window(m, w),
            "ARPA x gross_margin / logo_churn",
            {k: u[k] for k in ("arpa", "gross_margin", "logo_churn")},
            note="Undefined: no churn in the window" if u["logo_churn"] == 0 else None,
        )

    def _m_ltv_cac(self, t: _Trace, m: str, w: int) -> MetricResult:
        u = self._unit_economics(t, m, w)
        return self._result(
            t,
            "ltv_cac",
            u["ltv_cac"],
            "ratio",
            m,
            month_window(m, w),
            "LTV / CAC  (LTV = ARPA x GM / logo churn)",
            {k: u[k] for k in ("ltv", "cac", "arpa", "gross_margin", "logo_churn")},
        )

    def _m_cac_payback(self, t: _Trace, m: str, w: int) -> MetricResult:
        u = self._unit_economics(t, m, w)
        return self._result(
            t,
            "cac_payback",
            u["cac_payback"],
            "months",
            m,
            month_window(m, w),
            "CAC / (ARPA x gross_margin)",
            {k: u[k] for k in ("cac", "arpa", "gross_margin")},
        )

    def _m_headcount_cost(self, t: _Trace, m: str, w: int) -> MetricResult:
        months = month_window(m, w)
        payroll = self._pnl_sum(t, months, PAYROLL_FILTER)
        detail: dict[str, Any] = {}
        inputs: dict[str, Decimal | None] = {"total_payroll": payroll, "months": Decimal(w)}
        try:
            self._require(t.con, "headcount")
            has_headcount = True
        except NoDataError:
            has_headcount = False
        if has_headcount:
            cond = f"start_month <= '{m}' AND (end_month IS NULL OR end_month > '{m}')"
            t.source("headcount", cond)
            active = int(t.scalar(f"SELECT count(*) FROM headcount WHERE {cond}") or 0)
            detail["active_headcount"] = active
            inputs["active_headcount"] = Decimal(active)
        return self._result(
            t,
            "headcount_cost",
            _q(payroll / w),
            self.currency,
            m,
            months,
            f"sum(P&L accounts containing 'payroll') / {w}",
            inputs,
            detail=detail,
        )
