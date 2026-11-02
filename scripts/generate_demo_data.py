"""Generate the synthetic "Northwind Analytics" demo company (B2B SaaS) into `sample_data/`.

Deterministic: the same seed and options always produce the same CSV contents, so the files can be the
basis of golden-number tests. Money is computed in integer minor units (cents/paise) and written with two
decimals, so totals reconcile exactly (e.g. closing cash = opening + cash in - cash out).

Usage (from the repo root):
    python scripts/generate_demo_data.py                  # USD, seed 42, 24 months from 2024-11
    python scripts/generate_demo_data.py --currency INR   # same company, amounts in INR
    python scripts/generate_demo_data.py --out some/dir --seed 7

Outputs: customers.csv, subscriptions.csv, pipeline.csv, marketing_spend.csv, headcount.csv, pnl.csv,
bank_balance.csv, northwind_financials.xlsx (all tables, one sheet each) and meta.json.
Only the standard library and openpyxl are needed.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

GENERATOR_VERSION = "1.0.0"
COMPANY = "Northwind Analytics"
DEFAULT_SEED = 42
DEFAULT_START = "2024-11"
DEFAULT_MONTHS = 24

# Fixed demo conversion so INR output is the same company at a different scale (not a live FX rate).
CURRENCY_FACTORS: dict[str, int] = {"USD": 1, "INR": 84}

CHANNELS = ("Paid Search", "Content & SEO", "Outbound")
SEGMENTS = ("SMB", "Mid-Market", "Enterprise")
REGIONS = ("North America", "Europe", "India", "Middle East")
# (segment weight, list price MRR in USD)
SEGMENT_MIX = {"SMB": (0.55, 450), "Mid-Market": (0.35, 1400), "Enterprise": (0.10, 4200)}
PLAN_BY_SEGMENT = {"SMB": "Starter", "Mid-Market": "Growth", "Enterprise": "Enterprise"}
MONTHLY_CHURN = {"SMB": 0.028, "Mid-Market": 0.014, "Enterprise": 0.006}

# channel: (base monthly spend USD, spend growth per month, cost per lead USD, lead->won rate)
CHANNEL_ECONOMICS = {
    "Paid Search": (16_000, 0.012, 95.0, 0.009),
    "Content & SEO": (9_000, 0.018, 60.0, 0.011),
    "Outbound": (12_000, 0.010, 150.0, 0.016),
}

# department: (headcount at start, hires over the period, annual salary range USD)
DEPARTMENTS = {
    "Engineering": (8, 3, (115_000, 165_000)),
    "Sales": (3, 2, (85_000, 130_000)),
    "Marketing": (2, 1, (80_000, 120_000)),
    "Customer Success": (3, 2, (65_000, 95_000)),
    "G&A": (2, 1, (90_000, 150_000)),
}
ROLES = {
    "Engineering": ("Software Engineer", "Senior Engineer", "Data Engineer", "Engineering Manager"),
    "Sales": ("Account Executive", "Sales Development Rep", "Head of Sales"),
    "Marketing": ("Growth Marketer", "Content Lead"),
    "Customer Success": ("Customer Success Manager", "Support Engineer"),
    "G&A": ("Finance Manager", "Operations Lead", "CEO"),
}
EMPLOYER_COST_RATE = 0.15  # payroll taxes and benefits on top of salary

OPENING_CASH_USD = 2_600_000
FUNDING_MONTH_INDEX = 9  # month 10 of 24
FUNDING_AMOUNT_USD = 3_500_000
FUNDING_LABEL = "Seed extension"

NAME_PREFIXES = (
    "Blue", "Cedar", "North", "Silver", "Iron", "Maple", "Harbor", "Summit", "Orchid", "Granite",
    "Copper", "Falcon", "River", "Atlas", "Lumen", "Pioneer", "Quartz", "Vertex", "Willow", "Zenith",
)  # fmt: skip
NAME_CORES = (
    "peak", "field", "bridge", "stone", "line", "wave", "point", "gate", "works", "path",
    "light", "forge", "crest", "vale", "port",
)  # fmt: skip
NAME_SUFFIXES = (
    "Logistics", "Retail", "Health", "Foods", "Labs", "Finance", "Energy", "Media", "Travel", "Systems",
)  # fmt: skip


@dataclass
class Month:
    index: int
    first_day: date

    @property
    def key(self) -> str:
        return self.first_day.strftime("%Y-%m")


@dataclass
class Customer:
    customer_id: str
    name: str
    segment: str
    channel: str
    region: str
    signup_index: int
    base_mrr: int  # minor units
    churn_index: int | None = None
    mrr_by_month: dict[int, int] = field(default_factory=dict)


@dataclass
class Employee:
    employee_id: str
    department: str
    role: str
    start_index: int  # may be negative (joined before the data window)
    annual_salary: int  # minor units
    end_index: int | None = None

    def active(self, month_index: int) -> bool:
        return self.start_index <= month_index and (self.end_index is None or month_index < self.end_index)


def build_months(start: str, count: int) -> list[Month]:
    try:
        first = datetime.strptime(start, "%Y-%m").date()
    except ValueError as exc:
        raise ValueError(f"start must be YYYY-MM, got {start!r}") from exc
    year, month = first.year, first.month
    months = []
    for i in range(count):
        y, m = divmod(month - 1 + i, 12)
        months.append(Month(i, date(year + y, m + 1, 1)))
    return months


def money(units: int) -> str:
    """Minor units -> fixed two-decimal string, e.g. 123456 -> '1234.56'."""
    sign = "-" if units < 0 else ""
    units = abs(units)
    return f"{sign}{units // 100}.{units % 100:02d}"


class Generator:
    def __init__(self, seed: int, currency: str, start: str, months: int) -> None:
        if currency not in CURRENCY_FACTORS:
            raise ValueError(f"currency must be one of {sorted(CURRENCY_FACTORS)}")
        if months < 13:
            raise ValueError("months must be at least 13 (the funding event happens in month 10)")
        self.rng = random.Random(seed)
        self.seed = seed
        self.currency = currency
        self.factor = CURRENCY_FACTORS[currency]
        self.months = build_months(start, months)
        self.customers: list[Customer] = []
        self.employees: list[Employee] = []
        self.marketing: list[dict[str, Any]] = []
        self.pipeline: list[dict[str, Any]] = []
        self._used_names: set[str] = set()
        self._tables: dict[str, tuple[list[str], list[dict[str, Any]], set[str]]] | None = None

    # -- helpers ---------------------------------------------------------
    def units(self, usd: float) -> int:
        """USD amount -> integer minor units in the output currency."""
        return round(usd * 100 * self.factor)

    def company_name(self) -> str:
        while True:
            name = f"{self.rng.choice(NAME_PREFIXES)}{self.rng.choice(NAME_CORES)} {self.rng.choice(NAME_SUFFIXES)}"
            if name not in self._used_names:
                self._used_names.add(name)
                return name

    def pick_segment(self) -> str:
        roll, acc = self.rng.random(), 0.0
        for segment, (weight, _) in SEGMENT_MIX.items():
            acc += weight
            if roll < acc:
                return segment
        return SEGMENTS[0]

    def new_customer(self, signup_index: int, channel: str) -> Customer:
        segment = self.pick_segment()
        list_price = SEGMENT_MIX[segment][1]
        price = list_price * self.rng.uniform(0.8, 1.25)
        customer = Customer(
            customer_id=f"C{len(self.customers) + 1:04d}",
            name=self.company_name(),
            segment=segment,
            channel=channel,
            region=self.rng.choices(REGIONS, weights=(0.45, 0.25, 0.20, 0.10))[0],
            signup_index=signup_index,
            base_mrr=self.units(round(price, -1)),
        )
        self.customers.append(customer)
        return customer

    # -- simulation ------------------------------------------------------
    def simulate_marketing_and_pipeline(self) -> dict[int, list[str]]:
        """Spend -> leads -> opportunities -> won deals. Returns the won channels per month."""
        won_channels: dict[int, list[str]] = {}
        opp_id = 0
        for month in self.months:
            won_channels[month.index] = []
            for channel in CHANNELS:
                base, growth, cpl, win_rate = CHANNEL_ECONOMICS[channel]
                spend_usd = base * (1 + growth) ** month.index * self.rng.uniform(0.9, 1.1)
                spend_usd = round(spend_usd, -1)
                leads = max(1, round(spend_usd / (cpl * self.rng.uniform(0.85, 1.15))))
                self.marketing.append(
                    {
                        "month": month.key,
                        "channel": channel,
                        "spend": self.units(spend_usd),
                        "leads": leads,
                    }
                )
                won = sum(1 for _ in range(leads) if self.rng.random() < win_rate)
                lost = sum(1 for _ in range(leads) if self.rng.random() < win_rate * 1.6)
                for outcome, count in (("Closed Won", won), ("Closed Lost", lost)):
                    for _ in range(count):
                        opp_id += 1
                        cycle = self.rng.randint(1, 3)
                        created = max(0, month.index - cycle)
                        self.pipeline.append(
                            {
                                "opportunity_id": f"O{opp_id:05d}",
                                "created_month": self.months[created].key,
                                "channel": channel,
                                "stage": outcome,
                                "closed_month": month.key,
                                "_close_index": month.index,
                            }
                        )
                        if outcome == "Closed Won":
                            won_channels[month.index].append(channel)
        # Open pipeline: opportunities created in the last three months that have not closed yet.
        open_stages = ("Discovery", "Qualified", "Proposal", "Negotiation")
        stage_probability = {"Discovery": 0.10, "Qualified": 0.25, "Proposal": 0.50, "Negotiation": 0.70}
        for month in self.months[-3:]:
            for channel in CHANNELS:
                for _ in range(self.rng.randint(4, 8)):
                    opp_id += 1
                    stage = self.rng.choice(open_stages)
                    segment = self.pick_segment()
                    amount = self.units(SEGMENT_MIX[segment][1] * 12 * self.rng.uniform(0.8, 1.3))
                    expected = month.first_day.month + self.rng.randint(1, 4)
                    exp_year = month.first_day.year + (expected - 1) // 12
                    self.pipeline.append(
                        {
                            "opportunity_id": f"O{opp_id:05d}",
                            "created_month": month.key,
                            "channel": channel,
                            "stage": stage,
                            "segment": segment,
                            "annual_value": amount,
                            "probability": stage_probability[stage],
                            "expected_close_month": f"{exp_year}-{(expected - 1) % 12 + 1:02d}",
                            "closed_month": "",
                            "customer_id": "",
                        }
                    )
        return won_channels

    def simulate_customers(self, won_channels: dict[int, list[str]]) -> None:
        # Customers acquired before the data window (signup_index < 0).
        for _ in range(70):
            self.new_customer(-self.rng.randint(1, 30), self.rng.choice(CHANNELS))
        won_opps = iter([o for o in self.pipeline if o["stage"] == "Closed Won"])
        for month in self.months:
            for channel in won_channels[month.index]:
                customer = self.new_customer(month.index, channel)
                opp = next(won_opps)
                opp.update(
                    segment=customer.segment,
                    annual_value=customer.base_mrr * 12,
                    probability=1.0,
                    expected_close_month=month.key,
                    customer_id=customer.customer_id,
                )
        for opp in self.pipeline:
            if opp["stage"] == "Closed Lost":
                segment = self.pick_segment()
                opp.update(
                    segment=segment,
                    annual_value=self.units(SEGMENT_MIX[segment][1] * 12 * self.rng.uniform(0.8, 1.3)),
                    probability=0.0,
                    expected_close_month=opp["closed_month"],
                    customer_id="",
                )
        # Monthly MRR with churn and occasional expansion; a price list uplift of 5% in month 13.
        for customer in self.customers:
            mrr = customer.base_mrr
            for month in self.months:
                if month.index < customer.signup_index:
                    continue
                if month.index > max(customer.signup_index, 0) and self.rng.random() < MONTHLY_CHURN[customer.segment]:
                    customer.churn_index = month.index
                    break
                if month.index > customer.signup_index and self.rng.random() < 0.02:
                    mrr = round(mrr * self.rng.uniform(1.1, 1.4))  # expansion (seats / upgrade)
                if month.index == 12 and customer.signup_index < 12:
                    mrr = round(mrr * 1.05)
                customer.mrr_by_month[month.index] = mrr

    def simulate_headcount(self) -> None:
        n = 0
        for department, (start_count, hires, (low, high)) in DEPARTMENTS.items():
            roles = ROLES[department]
            for i in range(start_count + hires):
                n += 1
                # Starters joined before the window; hires join during it.
                start_index = -self.rng.randint(2, 30) if i < start_count else self.rng.randint(1, len(self.months) - 2)
                role = "CEO" if department == "G&A" and i == 0 else self.rng.choice(roles[:-1] or roles)
                salary_usd = round(self.rng.uniform(low, high), -3)
                if role == "CEO":
                    salary_usd = 160_000
                self.employees.append(Employee(f"E{n:03d}", department, role, start_index, self.units(salary_usd)))
        # Two leavers during the window (not the CEO), each backfilled one month later.
        leavers = self.rng.sample([e for e in self.employees if e.role != "CEO" and e.start_index < 0], 2)
        for leaver in leavers:
            leaver.end_index = self.rng.randint(4, len(self.months) - 4)
            n += 1
            self.employees.append(
                Employee(
                    f"E{n:03d}",
                    leaver.department,
                    leaver.role,
                    leaver.end_index + 1,
                    round(leaver.annual_salary * 1.04),
                )
            )

    # -- derived tables ---------------------------------------------------
    def pnl_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for month in self.months:
            i = month.index
            subscription = sum(c.mrr_by_month.get(i, 0) for c in self.customers)
            services = self.units(self.rng.choice((0, 0, 2_500, 4_000, 6_000)))
            payroll = {d: 0 for d in DEPARTMENTS}
            for e in self.employees:
                if e.active(i):
                    payroll[e.department] += round(e.annual_salary * (1 + EMPLOYER_COST_RATE) / 12)
            marketing_programs = sum(m["spend"] for m in self.marketing if m["month"] == month.key)
            active_staff = sum(1 for e in self.employees if e.active(i))
            lines = [
                ("Subscription revenue", "Revenue", subscription),
                ("Professional services", "Revenue", services),
                ("Hosting & infrastructure", "COGS", round(subscription * self.rng.uniform(0.10, 0.12))),
                ("Third-party data & APIs", "COGS", round(subscription * 0.03)),
                ("Customer Success payroll", "COGS", payroll["Customer Success"]),
                ("Engineering payroll", "Operating expense", payroll["Engineering"]),
                ("Sales payroll", "Operating expense", payroll["Sales"]),
                ("Marketing payroll", "Operating expense", payroll["Marketing"]),
                ("G&A payroll", "Operating expense", payroll["G&A"]),
                ("Marketing programs", "Operating expense", marketing_programs),
                ("Sales commissions", "Operating expense", round(subscription * 0.04)),
                ("Rent & office", "Operating expense", self.units(14_000 if i < 12 else 18_500)),
                ("Software & tools", "Operating expense", self.units(160) * active_staff),
                ("Professional fees", "Operating expense", self.units(self.rng.uniform(3_000, 7_000))),
                ("Travel", "Operating expense", self.units(self.rng.uniform(2_000, 6_000))),
            ]
            for account, category, amount in lines:
                rows.append({"month": month.key, "account": account, "category": category, "amount": amount})
        return rows

    def bank_rows(self, pnl: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        balance = self.units(OPENING_CASH_USD)
        for month in self.months:
            month_lines = [r for r in pnl if r["month"] == month.key]
            collections = sum(r["amount"] for r in month_lines if r["category"] == "Revenue")
            payments = sum(r["amount"] for r in month_lines if r["category"] != "Revenue")
            funding = self.units(FUNDING_AMOUNT_USD) if month.index == FUNDING_MONTH_INDEX else 0
            cash_in = collections + funding
            closing = balance + cash_in - payments
            rows.append(
                {
                    "month": month.key,
                    "opening_balance": balance,
                    "customer_receipts": collections,
                    "financing_inflows": funding,
                    "cash_in": cash_in,
                    "cash_out": payments,
                    "net_cash_flow": cash_in - payments,
                    "closing_balance": closing,
                    "note": FUNDING_LABEL if funding else "",
                }
            )
            balance = closing
        return rows

    # -- output ------------------------------------------------------------
    def tables(self) -> dict[str, tuple[list[str], list[dict[str, Any]], set[str]]]:
        """table name -> (columns, rows, money columns). Simulates once; later calls reuse the result."""
        if self._tables is not None:
            return self._tables
        won = self.simulate_marketing_and_pipeline()
        self.simulate_customers(won)
        self.simulate_headcount()
        pnl = self.pnl_rows()
        bank = self.bank_rows(pnl)
        key = {m.index: m.key for m in self.months}

        def month_key(index: int | None) -> str:
            if index is None:
                return ""
            return key[index] if index >= 0 else _shift(self.months[0].first_day, index)

        customers = [
            {
                "customer_id": c.customer_id,
                "name": c.name,
                "segment": c.segment,
                "plan": PLAN_BY_SEGMENT[c.segment],
                "region": c.region,
                "acquisition_channel": c.channel,
                "signup_month": month_key(c.signup_index),
                "churn_month": month_key(c.churn_index),
                "status": "churned" if c.churn_index is not None else "active",
            }
            for c in self.customers
        ]
        subscriptions = [
            {"month": key[i], "customer_id": c.customer_id, "mrr": mrr}
            for i in range(len(self.months))
            for c in self.customers
            if (mrr := c.mrr_by_month.get(i)) is not None
        ]
        headcount = [
            {
                "employee_id": e.employee_id,
                "department": e.department,
                "role": e.role,
                "start_month": month_key(e.start_index),
                "end_month": month_key(e.end_index),
                "annual_salary": e.annual_salary,
            }
            for e in self.employees
        ]
        pipeline_columns = [
            "opportunity_id",
            "created_month",
            "channel",
            "segment",
            "stage",
            "annual_value",
            "probability",
            "expected_close_month",
            "closed_month",
            "customer_id",
        ]
        pipeline = sorted(
            ({k: o.get(k, "") for k in pipeline_columns} for o in self.pipeline),
            key=lambda o: o["opportunity_id"],
        )
        self._tables = {
            "customers": (list(customers[0]), customers, set()),
            "subscriptions": (["month", "customer_id", "mrr"], subscriptions, {"mrr"}),
            "pipeline": (pipeline_columns, pipeline, {"annual_value"}),
            "marketing_spend": (["month", "channel", "spend", "leads"], self.marketing, {"spend"}),
            "headcount": (list(headcount[0]), headcount, {"annual_salary"}),
            "pnl": (["month", "account", "category", "amount"], pnl, {"amount"}),
            "bank_balance": (
                list(bank[0]),
                bank,
                {
                    "opening_balance",
                    "customer_receipts",
                    "financing_inflows",
                    "cash_in",
                    "cash_out",
                    "net_cash_flow",
                    "closing_balance",
                },
            ),
        }
        return self._tables


def _shift(first: date, months: int) -> str:
    y, m = divmod(first.month - 1 + months, 12)
    return f"{first.year + y}-{m + 1:02d}"


def _format(row: dict[str, Any], money_columns: set[str]) -> dict[str, Any]:
    return {k: (money(v) if k in money_columns and v != "" else v) for k, v in row.items()}


def write_outputs(out_dir: Path, seed: int, currency: str, start: str, months: int) -> dict[str, Any]:
    """Generate and write every output file. Returns the metadata written to meta.json."""
    gen = Generator(seed=seed, currency=currency, start=start, months=months)
    tables = gen.tables()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (columns, rows, money_columns) in tables.items():
        with (out_dir / f"{name}.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(_format(r, money_columns) for r in rows)
    _write_xlsx(out_dir / "northwind_financials.xlsx", tables)
    meta = {
        "company": COMPANY,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "currency": currency,
        "start_month": gen.months[0].key,
        "end_month": gen.months[-1].key,
        "months": months,
        "rows": {name: len(rows) for name, (_, rows, _) in tables.items()},
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def _write_xlsx(path: Path, tables: dict[str, tuple[list[str], list[dict[str, Any]], set[str]]]) -> None:
    from openpyxl import Workbook  # imported lazily so CSV-only use has no hard dependency at import time

    wb = Workbook()
    wb.remove(wb.active)
    for name, (columns, rows, money_columns) in tables.items():
        ws = wb.create_sheet(title=name)
        ws.append(columns)
        for row in rows:
            ws.append([(row[c] / 100 if c in money_columns and row[c] != "" else row[c]) for c in columns])
        for column in money_columns:
            letter = ws.cell(row=1, column=columns.index(column) + 1).column_letter
            for cell in ws[letter][1:]:
                cell.number_format = "#,##0.00"
    fixed = datetime(2024, 1, 1)
    wb.properties.created = fixed
    wb.properties.modified = fixed
    buffer = io.BytesIO()
    wb.save(buffer)
    # Re-pack with fixed zip timestamps so the file is byte-identical across runs (stable in git).
    with zipfile.ZipFile(buffer) as src, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            entry = zipfile.ZipInfo(info.filename, date_time=(2024, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":  # openpyxl stamps "modified" with the current time on save
                data = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>2024-01-01T00:00:00Z\g<2>", data
                )
            dst.writestr(entry, data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Generate the {COMPANY} demo dataset.")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "sample_data")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--currency", choices=sorted(CURRENCY_FACTORS), default="USD")
    parser.add_argument("--start", default=DEFAULT_START, help="first month, YYYY-MM")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS)
    args = parser.parse_args(argv)
    meta = write_outputs(args.out, args.seed, args.currency, args.start, args.months)
    print(f"Wrote {COMPANY} ({meta['currency']}, {meta['start_month']}..{meta['end_month']}) to {args.out}")
    for name, count in meta["rows"].items():
        print(f"  {name}.csv: {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
