"""Canonical schema of the financial spine and the header synonyms used to map real files onto it.

Every ingested file is mapped onto one of these tables. Column names are canonical snake_case; months are stored as
`YYYY-MM` text (sortable, matches the source files) and money as `DECIMAL(18,2)`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ColumnType(Enum):
    TEXT = "text"
    MONTH = "month"  # stored as 'YYYY-MM' text
    MONEY = "money"
    INTEGER = "integer"
    RATIO = "ratio"


SQL_TYPES: dict[ColumnType, str] = {
    ColumnType.TEXT: "VARCHAR",
    ColumnType.MONTH: "VARCHAR",
    ColumnType.MONEY: "DECIMAL(18,2)",
    ColumnType.INTEGER: "BIGINT",
    ColumnType.RATIO: "DECIMAL(9,4)",
}


@dataclass(frozen=True)
class Column:
    name: str
    type: ColumnType
    required: bool = True
    synonyms: tuple[str, ...] = ()

    @property
    def sql_type(self) -> str:
        return SQL_TYPES[self.type]


@dataclass(frozen=True)
class TableSpec:
    name: str
    description: str
    columns: tuple[Column, ...]
    name_synonyms: tuple[str, ...] = field(default=())

    @property
    def required(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.required)

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)


M = ColumnType
TABLES: dict[str, TableSpec] = {
    spec.name: spec
    for spec in (
        TableSpec(
            "pnl",
            "Profit and loss, one row per month and account",
            (
                Column("month", M.MONTH, synonyms=("period", "date", "month_start", "posting_month")),
                Column("account", M.TEXT, synonyms=("account_name", "line_item", "gl_account", "ledger", "item")),
                Column("category", M.TEXT, synonyms=("type", "account_type", "class", "group", "section")),
                Column("amount", M.MONEY, synonyms=("value", "total", "net_amount", "amount_usd", "amount_inr")),
            ),
            ("pnl", "p_l", "p_and_l", "profit_and_loss", "profit_loss", "income_statement"),
        ),
        TableSpec(
            "bank_balance",
            "Cash position, one row per month",
            (
                Column("month", M.MONTH, synonyms=("period", "date", "month_start")),
                Column("opening_balance", M.MONEY, synonyms=("opening", "opening_cash", "start_balance")),
                Column("customer_receipts", M.MONEY, False, ("receipts", "collections", "operating_receipts")),
                Column("financing_inflows", M.MONEY, False, ("financing", "funding", "equity_raised", "investment")),
                Column("cash_in", M.MONEY, synonyms=("inflows", "total_inflows", "cash_inflow", "money_in")),
                Column("cash_out", M.MONEY, synonyms=("outflows", "total_outflows", "cash_outflow", "money_out")),
                Column("net_cash_flow", M.MONEY, False, ("net_flow", "net_cash", "net_change")),
                Column("closing_balance", M.MONEY, synonyms=("closing", "closing_cash", "end_balance", "balance")),
                Column("note", M.TEXT, False, ("notes", "memo", "comment", "description")),
            ),
            ("bank_balance", "bank", "cash", "cash_balance", "bank_statement", "cash_flow"),
        ),
        TableSpec(
            "customers",
            "One row per customer",
            (
                Column("customer_id", M.TEXT, synonyms=("customer", "client_id", "account_id", "id")),
                Column("name", M.TEXT, False, ("customer_name", "company", "client_name")),
                Column("segment", M.TEXT, False, ("tier", "customer_segment")),
                Column("plan", M.TEXT, False, ("product", "package")),
                Column("region", M.TEXT, False, ("country", "geo", "geography")),
                Column("acquisition_channel", M.TEXT, False, ("channel", "source", "lead_source")),
                Column("signup_month", M.MONTH, synonyms=("signup", "start_month", "signup_date", "start_date")),
                Column("churn_month", M.MONTH, False, ("churn", "churn_date", "cancel_month", "end_month")),
                Column("status", M.TEXT, False, ("state", "customer_status")),
            ),
            ("customers", "customer", "clients", "accounts"),
        ),
        TableSpec(
            "subscriptions",
            "MRR per month and active customer",
            (
                Column("month", M.MONTH, synonyms=("period", "date", "month_start")),
                Column("customer_id", M.TEXT, synonyms=("customer", "client_id", "account_id")),
                Column("mrr", M.MONEY, synonyms=("monthly_recurring_revenue", "recurring_revenue", "amount")),
            ),
            ("subscriptions", "subscription", "mrr", "recurring_revenue"),
        ),
        TableSpec(
            "pipeline",
            "Sales opportunities",
            (
                Column("opportunity_id", M.TEXT, synonyms=("opportunity", "deal_id", "opp_id", "id")),
                Column("created_month", M.MONTH, synonyms=("created", "created_date", "create_date")),
                Column("channel", M.TEXT, False, ("source", "lead_source")),
                Column("segment", M.TEXT, False, ("tier",)),
                Column("stage", M.TEXT, synonyms=("deal_stage", "status")),
                Column("annual_value", M.MONEY, synonyms=("acv", "arr", "deal_value", "amount", "value")),
                Column("probability", M.RATIO, False, ("win_probability", "prob")),
                Column("expected_close_month", M.MONTH, False, ("expected_close", "close_date", "expected_close_date")),
                Column("closed_month", M.MONTH, False, ("closed", "closed_date")),
                Column("customer_id", M.TEXT, False, ("customer", "account_id")),
            ),
            ("pipeline", "opportunities", "deals", "crm", "sales_pipeline"),
        ),
        TableSpec(
            "marketing_spend",
            "Marketing spend per month and channel",
            (
                Column("month", M.MONTH, synonyms=("period", "date", "month_start")),
                Column("channel", M.TEXT, synonyms=("source", "campaign_channel", "medium")),
                Column("spend", M.MONEY, synonyms=("cost", "amount", "budget_spent")),
                Column("leads", M.INTEGER, False, ("lead_count", "leads_generated")),
            ),
            ("marketing_spend", "marketing", "ad_spend", "marketing_costs"),
        ),
        TableSpec(
            "headcount",
            "One row per employee",
            (
                Column("employee_id", M.TEXT, synonyms=("employee", "emp_id", "staff_id", "id")),
                Column("department", M.TEXT, synonyms=("dept", "team", "function")),
                Column("role", M.TEXT, False, ("title", "job_title", "position")),
                Column("start_month", M.MONTH, synonyms=("start", "start_date", "hire_date", "joined")),
                Column("end_month", M.MONTH, False, ("end", "end_date", "leave_date", "exit_date")),
                Column("annual_salary", M.MONEY, synonyms=("salary", "base_salary", "annual_pay", "ctc")),
            ),
            ("headcount", "employees", "staff", "people", "team"),
        ),
    )
}

# P&L category normalisation: canonical name -> accepted spellings (normalised with `normalise_header`).
PNL_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Revenue": ("revenue", "income", "sales", "turnover"),
    "COGS": ("cogs", "cost_of_sales", "cost_of_revenue", "cost_of_goods_sold", "direct_costs"),
    "Operating expense": ("operating_expense", "operating_expenses", "opex", "expense", "expenses", "overheads"),
}


def normalise_header(text: str) -> str:
    """`" Annual Salary ($) "` -> `"annual_salary"`: lowercase, non-alphanumerics collapsed to `_`."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def normalise_category(text: str) -> str | None:
    key = normalise_header(text)
    for canonical, spellings in PNL_CATEGORIES.items():
        if key in spellings:
            return canonical
    return None
