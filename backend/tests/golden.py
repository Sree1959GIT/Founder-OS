"""Independent re-computation of the metric definitions straight from the sample CSVs (plain Python + Decimal).

Nothing here uses DuckDB or the engine code, so the golden tests compare two separate implementations. Rounding
mirrors the documented behaviour of the routines (money to cents, ratios to 4 dp, both ROUND_HALF_UP).
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path

from app.config import PROJECT_ROOT

SAMPLE = PROJECT_ROOT / "sample_data"
CENT = Decimal("0.01")
RATIO = Decimal("0.0001")
SM_ACCOUNTS = {"Marketing programs", "Sales payroll", "Marketing payroll", "Sales commissions"}


def q(x: Decimal, step: Decimal = CENT) -> Decimal:
    return x.quantize(step, rounding=ROUND_HALF_UP)


@cache
def rows(name: str, directory: Path = SAMPLE) -> list[dict[str, str]]:
    with (directory / f"{name}.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def shift(month: str, n: int) -> str:
    y, m = divmod(int(month[5:7]) - 1 + n, 12)
    return f"{int(month[:4]) + y:04d}-{m + 1:02d}"


def window(end: str, w: int) -> list[str]:
    return [shift(end, -i) for i in range(w - 1, -1, -1)]


def bank(month: str) -> dict[str, str]:
    return next(r for r in rows("bank_balance") if r["month"] == month)


def gross_burn(m: str, w: int) -> Decimal:
    return q(sum(Decimal(bank(x)["cash_out"]) for x in window(m, w)) / w)


def net_burn(m: str, w: int) -> Decimal:
    months = window(m, w)
    out = sum(Decimal(bank(x)["cash_out"]) for x in months)
    receipts = sum(Decimal(bank(x)["customer_receipts"]) for x in months)
    return q((out - receipts) / w)


def runway(m: str, w: int) -> tuple[Decimal, str]:
    r = q(Decimal(bank(m)["closing_balance"]) / net_burn(m, w))
    return r, shift(m, math.ceil(r))


def subs(month: str) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows("subscriptions"):
        if r["month"] == month:
            out[r["customer_id"]] += Decimal(r["mrr"])
    return dict(out)


def mrr(m: str) -> tuple[Decimal, int]:
    s = subs(m)
    return sum(s.values(), Decimal(0)), len(s)


def pnl_total(months: list[str], predicate) -> Decimal:  # type: ignore[no-untyped-def]
    return sum(
        (Decimal(r["amount"]) for r in rows("pnl") if r["month"] in months and predicate(r)),
        Decimal(0),
    )


def revenue(months: list[str]) -> Decimal:
    return pnl_total(months, lambda r: r["category"] == "Revenue")


def gross_margin_raw(months: list[str]) -> Decimal:
    rev = revenue(months)
    cogs = pnl_total(months, lambda r: r["category"] == "COGS")
    return q((rev - cogs) / rev, RATIO)


def new_customers(months: list[str], channel: str | None = None) -> int:
    return sum(
        1
        for c in rows("customers")
        if c["signup_month"] in months and (channel is None or c["acquisition_channel"] == channel)
    )


def cac(m: str, w: int) -> Decimal:
    months = window(m, w)
    cost = pnl_total(months, lambda r: r["account"] in SM_ACCOUNTS)
    return q(cost / new_customers(months))


def churn_parts(m: str, w: int) -> tuple[int, int, Decimal, Decimal]:
    start = lost = 0
    start_mrr = lost_mrr = Decimal(0)
    for month in window(m, w):
        prev, cur = subs(shift(month, -1)), subs(month)
        start += len(prev)
        lost += sum(1 for c in prev if c not in cur)
        start_mrr += sum(prev.values(), Decimal(0))
        lost_mrr += sum((max(v - cur.get(c, Decimal(0)), Decimal(0)) for c, v in prev.items()), Decimal(0))
    return start, lost, start_mrr, lost_mrr


def nrr(m: str, lookback: int) -> Decimal:
    then, now = subs(shift(m, -lookback)), subs(m)
    return q(sum(now.get(c, Decimal(0)) for c in then) / sum(then.values()), RATIO)


def unit_economics(m: str, w: int) -> dict[str, Decimal]:
    total, customers = mrr(m)
    arpa = total / customers
    gm = gross_margin_raw(window(m, w))
    start, lost, _, _ = churn_parts(m, w)
    churn = Decimal(lost) / Decimal(start)
    c = cac(m, w)
    ltv = q(arpa * gm / churn)
    return {"ltv": ltv, "ltv_cac": q(ltv / c), "cac_payback": q(c / (arpa * gm)), "arpa": q(arpa)}


def payroll(m: str, w: int) -> Decimal:
    return q(pnl_total(window(m, w), lambda r: "payroll" in r["account"].lower()) / w)


def active_headcount(m: str) -> int:
    return sum(1 for e in rows("headcount") if e["start_month"] <= m and (not e["end_month"] or m < e["end_month"]))


def csv_line(table: str, predicate) -> list[int]:  # type: ignore[no-untyped-def]
    """CSV line numbers (header = 1) of the rows matching `predicate`, i.e. the Excel row numbers."""
    return [i for i, r in enumerate(rows(table), start=2) if predicate(r)]
