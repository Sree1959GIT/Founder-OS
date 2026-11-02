"""Tests for scripts/generate_demo_data.py: determinism and the accounting identities M1 relies on."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

from app.config import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "scripts" / "generate_demo_data.py"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_demo_data", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


gen = load_generator()


def read(out: Path, name: str) -> list[dict[str, str]]:
    with (out / f"{name}.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("northwind")
    gen.write_outputs(path, seed=42, currency="USD", start="2024-11", months=24)
    return path


def test_writes_all_files(out: Path) -> None:
    expected = {
        "customers.csv",
        "subscriptions.csv",
        "pipeline.csv",
        "marketing_spend.csv",
        "headcount.csv",
        "pnl.csv",
        "bank_balance.csv",
        "northwind_financials.xlsx",
        "meta.json",
    }
    assert expected <= {p.name for p in out.iterdir()}
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["company"] == "Northwind Analytics"
    assert (meta["start_month"], meta["end_month"], meta["months"]) == ("2024-11", "2026-10", 24)


def test_deterministic_byte_for_byte(out: Path, tmp_path: Path) -> None:
    gen.write_outputs(tmp_path, seed=42, currency="USD", start="2024-11", months=24)
    for path in out.iterdir():
        assert (tmp_path / path.name).read_bytes() == path.read_bytes(), path.name


def test_committed_sample_data_matches_generator(out: Path) -> None:
    committed = PROJECT_ROOT / "sample_data"
    for name in ("pnl.csv", "bank_balance.csv", "subscriptions.csv", "meta.json"):
        assert (committed / name).read_bytes() == (out / name).read_bytes(), f"re-run the generator: {name}"


def test_different_seed_changes_data(out: Path, tmp_path: Path) -> None:
    gen.write_outputs(tmp_path, seed=7, currency="USD", start="2024-11", months=24)
    assert (tmp_path / "customers.csv").read_bytes() != (out / "customers.csv").read_bytes()


def test_bank_balance_reconciles_with_pnl(out: Path) -> None:
    bank = read(out, "bank_balance")
    pnl = read(out, "pnl")
    assert len(bank) == 24
    revenue: dict[str, Decimal] = defaultdict(Decimal)
    costs: dict[str, Decimal] = defaultdict(Decimal)
    for row in pnl:
        (revenue if row["category"] == "Revenue" else costs)[row["month"]] += Decimal(row["amount"])
    previous_close = None
    for row in bank:
        d = {k: Decimal(v) for k, v in row.items() if k not in ("month", "note")}
        assert d["closing_balance"] == d["opening_balance"] + d["cash_in"] - d["cash_out"]
        assert d["net_cash_flow"] == d["cash_in"] - d["cash_out"]
        assert d["cash_in"] == d["customer_receipts"] + d["financing_inflows"]
        assert d["customer_receipts"] == revenue[row["month"]]
        assert d["cash_out"] == costs[row["month"]]
        if previous_close is not None:
            assert d["opening_balance"] == previous_close
        previous_close = d["closing_balance"]
    funded = [r for r in bank if Decimal(r["financing_inflows"]) > 0]
    assert [r["month"] for r in funded] == ["2025-08"]


def test_subscription_revenue_equals_mrr(out: Path) -> None:
    mrr: dict[str, Decimal] = defaultdict(Decimal)
    for row in read(out, "subscriptions"):
        mrr[row["month"]] += Decimal(row["mrr"])
    for row in read(out, "pnl"):
        if row["account"] == "Subscription revenue":
            assert Decimal(row["amount"]) == mrr[row["month"]]


def test_marketing_programs_equals_channel_spend(out: Path) -> None:
    spend: dict[str, Decimal] = defaultdict(Decimal)
    for row in read(out, "marketing_spend"):
        spend[row["month"]] += Decimal(row["spend"])
    assert {r["channel"] for r in read(out, "marketing_spend")} == set(gen.CHANNELS)
    for row in read(out, "pnl"):
        if row["account"] == "Marketing programs":
            assert Decimal(row["amount"]) == spend[row["month"]]


def test_company_shape_matches_prd(out: Path) -> None:
    """PRD F1: ~150 customers, 3 channels, ~25 staff, and a company that is burning cash."""
    customers = read(out, "customers")
    active_last_month = {r["customer_id"] for r in read(out, "subscriptions") if r["month"] == "2026-10"}
    assert 120 <= len(active_last_month) <= 180
    assert {r["status"] for r in customers if r["customer_id"] in active_last_month} == {"active"}
    staff = [r for r in read(out, "headcount") if not r["end_month"]]
    assert 22 <= len(staff) <= 30
    last = read(out, "bank_balance")[-1]
    burn = -Decimal(last["net_cash_flow"])
    assert burn > 0
    runway_months = Decimal(last["closing_balance"]) / burn
    assert 6 <= runway_months <= 18


def test_won_opportunities_link_to_new_customers(out: Path) -> None:
    customers = {r["customer_id"]: r for r in read(out, "customers")}
    won = [r for r in read(out, "pipeline") if r["stage"] == "Closed Won"]
    assert won
    for opp in won:
        customer = customers[opp["customer_id"]]
        assert customer["signup_month"] == opp["closed_month"]
        assert customer["acquisition_channel"] == opp["channel"]
    open_opps = [r for r in read(out, "pipeline") if not r["closed_month"]]
    assert open_opps and all(0 < float(r["probability"]) < 1 for r in open_opps)


def test_inr_is_same_company_scaled(out: Path, tmp_path: Path) -> None:
    gen.write_outputs(tmp_path, seed=42, currency="INR", start="2024-11", months=24)
    usd = read(out, "bank_balance")[0]
    inr = read(tmp_path, "bank_balance")[0]
    assert Decimal(inr["opening_balance"]) == Decimal(usd["opening_balance"]) * gen.CURRENCY_FACTORS["INR"]
    assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))["currency"] == "INR"


def test_xlsx_has_every_table(out: Path) -> None:
    from openpyxl import load_workbook

    wb = load_workbook(out / "northwind_financials.xlsx", read_only=True)
    assert set(wb.sheetnames) == {"customers", "subscriptions", "pipeline", "marketing_spend", "headcount", "pnl",
                                  "bank_balance"}  # fmt: skip
    rows = list(wb["bank_balance"].iter_rows(values_only=True))
    assert len(rows) == 25
    assert rows[1][1] == pytest.approx(float(read(out, "bank_balance")[0]["opening_balance"]))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"currency": "EUR"}, "currency"), ({"months": 6}, "months"), ({"start": "Nov 2024"}, "YYYY-MM")],
)
def test_rejects_bad_options(tmp_path: Path, kwargs: dict[str, object], message: str) -> None:
    options: dict[str, object] = {"seed": 1, "currency": "USD", "start": "2024-11", "months": 24} | kwargs
    with pytest.raises(ValueError, match=message):
        gen.write_outputs(tmp_path, **options)
