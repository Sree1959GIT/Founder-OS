"""Ingestion and the column-mapping layer."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.config import PROJECT_ROOT
from app.engine.duckdb_engine import FinanceDB
from app.engine.ingest import (
    MAPPINGS_FILE_NAME,
    IngestError,
    ingest_directory,
    ingest_file,
    ingest_log,
    parse_integer,
    parse_money,
    parse_month,
    parse_ratio,
)
from tests import golden as g

SAMPLE = PROJECT_ROOT / "sample_data"


def write(path: Path, text: str, encoding: str = "utf-8") -> Path:
    path.write_text(text, encoding=encoding, newline="")
    return path


def scalar(db: FinanceDB, sql: str):  # type: ignore[no-untyped-def]
    with db.connect() as con:
        row = con.execute(sql).fetchone()
    return row[0] if row else None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.5", "1234.50"),
        ("$1,234.56", "1234.56"),
        ("(500)", "-500.00"),
        ("-12", "-12.00"),
        ("₹ 84,000", "84000.00"),
        ("USD 10", "10.00"),
        ("Rs. 1,000", "1000.00"),  # review finding: was read as 0.10
        ("Rs 1,000", "1000.00"),
        ("84,000 INR", "84000.00"),
        ("$(1,000)", "-1000.00"),  # review finding: sign was lost after a currency prefix
        ("USD (250.00)", "-250.00"),
        ("-$1,000", "-1000.00"),
        ("\u22125", "-5.00"),
        (1234.565, "1234.57"),
        (7, "7.00"),
        (Decimal("0.005"), "0.01"),
    ],
)
def test_parse_money(raw: object, expected: str) -> None:
    assert parse_money(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["abc", "", "1.2.3", True, "NaN", "Rs.", "12abc", "1e20", "99999999999999999"])
def test_parse_money_rejects(raw: object) -> None:
    with pytest.raises(ValueError):
        parse_money(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10", "2026-10"),
        ("2026-10-01", "2026-10"),
        ("2026/3", "2026-03"),
        ("03/2026", "2026-03"),
        ("Oct 2026", "2026-10"),
        ("October-26", "2026-10"),
        (date(2025, 2, 1), "2025-02"),
        (datetime(2025, 12, 31, 10, 0), "2025-12"),
        ("2026-10-01 00:00:00", "2026-10"),
    ],
)
def test_parse_month(raw: object, expected: str) -> None:
    assert parse_month(raw) == expected


@pytest.mark.parametrize("raw", ["2026-13", "Foo 2026", "10", "2026"])
def test_parse_month_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_month(raw)


def test_parse_integer_and_ratio() -> None:
    assert parse_integer("1,204") == 1204
    assert parse_integer(12.0) == 12
    with pytest.raises(ValueError):
        parse_integer(1.5)
    assert parse_ratio("25%") == Decimal("0.2500")
    assert parse_ratio(0.3) == Decimal("0.3000")
    with pytest.raises(ValueError):
        parse_ratio("150%")


def test_sample_directory_loads_every_table(empty_db: FinanceDB) -> None:
    reports = ingest_directory(empty_db, SAMPLE)
    meta = json.loads((SAMPLE / "meta.json").read_text(encoding="utf-8"))
    assert {r.table: r.rows for r in reports} == meta["rows"]
    assert all(not r.warnings and not r.unmapped_headers for r in reports)
    assert empty_db.tables() == set(meta["rows"])
    log = {entry["table"]: entry for entry in ingest_log(empty_db)}
    assert log["pnl"]["source_file"] == "pnl.csv" and log["pnl"]["rows"] == 360


def test_provenance_matches_csv_line_numbers(loaded_db: FinanceDB) -> None:
    with loaded_db.connect() as con:
        rows = con.execute("SELECT _source_row FROM bank_balance WHERE month = '2026-10'").fetchall()
    assert [r for (r,) in rows] == g.csv_line("bank_balance", lambda r: r["month"] == "2026-10") == [25]


def test_xlsx_loads_the_same_numbers_as_csv(tmp_path: Path, loaded_db: FinanceDB) -> None:
    db = FinanceDB(tmp_path / "xlsx")
    reports = ingest_file(db, SAMPLE / "northwind_financials.xlsx")
    assert len(reports) == 7
    for table, column in [("pnl", "amount"), ("subscriptions", "mrr"), ("bank_balance", "closing_balance")]:
        sql = f"SELECT sum({column}), count(*) FROM {table}"
        assert scalar(db, sql) == scalar(loaded_db, sql)
    with db.connect() as con:
        row = con.execute("SELECT _source_file, _source_sheet, _source_row FROM pnl ORDER BY _source_row LIMIT 1")
        assert row.fetchone() == ("northwind_financials.xlsx", "pnl", 2)


def test_header_synonyms_and_category_normalisation(empty_db: FinanceDB, tmp_path: Path) -> None:
    path = write(
        tmp_path / "Profit and Loss FY26.csv",
        "Period,Line Item,Type,Value,Comment\n"
        'Oct 2026,Subscriptions,Income,"$1,000.00",x\n'
        "2026-10-01,Hosting,Cost of Sales,(200),\n"
        "2026-10,Rent,Opex,300,\n",
    )
    (report,) = ingest_file(empty_db, path)
    assert report.table == "pnl"
    assert report.columns == {"Period": "month", "Line Item": "account", "Type": "category", "Value": "amount"}
    assert report.unmapped_headers == ["Comment"]
    with empty_db.connect() as con:
        rows = con.execute("SELECT month, category, amount FROM pnl ORDER BY _source_row").fetchall()
    assert rows == [
        ("2026-10", "Revenue", Decimal("1000.00")),
        ("2026-10", "COGS", Decimal("-200.00")),
        ("2026-10", "Operating expense", Decimal("300.00")),
    ]


def test_mapping_is_saved_and_reused(empty_db: FinanceDB, tmp_path: Path) -> None:
    path = write(tmp_path / "export.csv", "Period,Channel,Cost\n2026-10,Paid Search,100\n")
    (report,) = ingest_file(empty_db, path)  # detected by headers
    assert report.table == "marketing_spend"
    saved = json.loads((empty_db.data_dir / MAPPINGS_FILE_NAME).read_text(encoding="utf-8"))
    assert saved["export.csv"] == {
        "table": "marketing_spend",
        "columns": {"Period": "month", "Channel": "channel", "Cost": "spend"},
    }
    # A hand-edited mapping wins over auto-detection next time.
    saved["export.csv"]["columns"] = {"Period": "month", "Channel": "channel", "Cost": "spend"}
    (empty_db.data_dir / MAPPINGS_FILE_NAME).write_text(json.dumps(saved), encoding="utf-8")
    (again,) = ingest_file(empty_db, path)
    assert again.table == "marketing_spend"


def test_explicit_table_choice(empty_db: FinanceDB, tmp_path: Path) -> None:
    path = write(tmp_path / "data.csv", "month,customer_id,amount\n2026-10,C1,10\n")
    (report,) = ingest_file(empty_db, path, table="subscriptions")
    assert report.columns["amount"] == "mrr"
    with pytest.raises(IngestError, match="Unknown table"):
        ingest_file(empty_db, path, table="payroll_magic")


def test_bad_values_are_reported_by_row_and_nothing_is_loaded(empty_db: FinanceDB, tmp_path: Path) -> None:
    ingest_file(empty_db, write(tmp_path / "pnl.csv", "month,account,category,amount\n2026-10,A,Revenue,1\n"))
    bad = write(
        tmp_path / "pnl.csv",
        "month,account,category,amount\n2026-10,A,Revenue,abc\n2026-13,B,Revenue,1\n2026-10,,Revenue,1\n"
        "2026-10,C,Dividends,1\n",
    )
    with pytest.raises(IngestError) as info:
        ingest_file(empty_db, bad)
    errors = info.value.errors
    assert any(e.startswith("row 2, 'amount'") for e in errors)
    assert any(e.startswith("row 3, 'month'") for e in errors)
    assert any(e.startswith("row 4, 'account'") and "required" in e for e in errors)
    assert any(e.startswith("row 5, 'category'") for e in errors)
    assert scalar(empty_db, "SELECT count(*) FROM pnl") == 1  # the previous load is untouched


def test_missing_required_column(empty_db: FinanceDB, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="required column"):
        ingest_file(empty_db, write(tmp_path / "pnl.csv", "month,account,amount\n2026-10,A,1\n"))


def test_unknown_file_kind(empty_db: FinanceDB, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="cannot tell which table"):
        ingest_file(empty_db, write(tmp_path / "notes.csv", "foo,bar\n1,2\n"))
    with pytest.raises(IngestError, match="Unsupported file type"):
        ingest_file(empty_db, write(tmp_path / "x.txt", "a"))
    with pytest.raises(IngestError, match="headers"):
        ingest_file(empty_db, write(tmp_path / "pnl.csv", ""))


def test_corrupt_xlsx(empty_db: FinanceDB, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="not a readable"):
        ingest_file(empty_db, write(tmp_path / "pnl.xlsx", "not a zip"))


def test_windows_ansi_csv_is_accepted(empty_db: FinanceDB, tmp_path: Path) -> None:
    path = tmp_path / "pnl.csv"
    path.write_bytes("month,account,category,amount\n2026-10,Café supplies,Opex,£12\n".encode("cp1252"))
    ingest_file(empty_db, path)
    assert scalar(empty_db, "SELECT account FROM pnl") == "Café supplies"


def test_reload_replaces_the_table(empty_db: FinanceDB, tmp_path: Path) -> None:
    path = tmp_path / "pnl.csv"
    write(path, "month,account,category,amount\n2026-10,A,Revenue,1\n2026-10,B,Revenue,2\n")
    ingest_file(empty_db, path)
    write(path, "month,account,category,amount\n2026-10,A,Revenue,5\n")
    ingest_file(empty_db, path)
    assert scalar(empty_db, "SELECT sum(amount) FROM pnl") == Decimal("5.00")


def test_xlsx_with_excel_types(empty_db: FinanceDB, tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append(["Emp ID", "Dept", "Hire Date", "Salary"])
    ws.append([101, "Engineering", datetime(2025, 3, 15), 120000])
    ws.append([None, None, None, None])  # blank row is skipped
    ws.append([102, "Sales", "Apr 2025", "95,000"])
    wb.create_sheet("Empty")
    path = tmp_path / "people.xlsx"
    wb.save(path)
    (report,) = ingest_file(empty_db, path)
    assert report.table == "headcount" and report.rows == 2
    with empty_db.connect() as con:
        rows = con.execute("SELECT employee_id, start_month, annual_salary, _source_row FROM headcount").fetchall()
    assert rows == [("101", "2025-03", Decimal("120000.00"), 2), ("102", "2025-04", Decimal("95000.00"), 4)]


def test_two_sheets_for_one_table_rejected(empty_db: FinanceDB, tmp_path: Path) -> None:
    wb = Workbook()
    wb.active.title = "pnl"
    wb.active.append(["month", "account", "category", "amount"])
    wb.active.append(["2026-10", "A", "Revenue", 1])
    other = wb.create_sheet("P&L")
    other.append(["month", "account", "category", "amount"])
    other.append(["2026-10", "A", "Revenue", 1])
    wb.save(tmp_path / "book.xlsx")
    with pytest.raises(IngestError, match="more than one sheet"):
        ingest_file(empty_db, tmp_path / "book.xlsx")


def test_bank_month_must_be_unique(empty_db: FinanceDB, tmp_path: Path) -> None:
    """Review finding: duplicate months were summed into burn but runway read only one closing balance."""
    path = write(
        tmp_path / "bank.csv",
        "month,opening_balance,cash_in,cash_out,closing_balance\n"
        "2026-09,100,10,5,105\n2026-10,105,10,5,110\n2026-10,105,10,6,109\n",
    )
    with pytest.raises(IngestError) as info:
        ingest_file(empty_db, path)
    assert info.value.errors == ["row 4: month 2026-10 already appears in row 3"]


def test_undecodable_csv_is_a_clear_error(empty_db: FinanceDB, tmp_path: Path) -> None:
    """Review finding: bytes undefined in both UTF-8 and cp1252 raised a raw UnicodeDecodeError (500)."""
    path = tmp_path / "pnl.csv"
    path.write_bytes(b"month,account,category,amount\n2026-10,A\x81\x9d,Revenue,1\n")
    with pytest.raises(IngestError, match="UTF-8"):
        ingest_file(empty_db, path)


def test_bank_identity_warning(empty_db: FinanceDB, tmp_path: Path) -> None:
    path = write(
        tmp_path / "bank.csv",
        "month,opening_balance,cash_in,cash_out,closing_balance\n2026-10,100,10,5,999\n",
    )
    (report,) = ingest_file(empty_db, path)
    assert report.table == "bank_balance"
    assert report.warnings and "closing_balance" in report.warnings[0]
