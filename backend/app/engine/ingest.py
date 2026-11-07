"""Ingest CSV/XLSX files into the workspace DuckDB, mapping their columns onto the canonical schema.

Flow per sheet (a CSV file is one sheet): pick the canonical table (explicit choice > saved mapping > file or sheet
name > best header match), map each header through the synonyms in `schema.py`, parse and validate every row, then
replace the table. Parsing is strict: one bad value rejects the file with a list of row-level errors, because a
silently skipped row would make every number downstream wrong. Mappings are saved to `data/<ws>/mappings.json` so
the same file maps the same way next time (and can be edited by hand or, from M4, in the UI).

Each loaded row keeps `_source_file`, `_source_sheet` and `_source_row` (the CSV line / Excel row number, header =
row 1) so lineage can point at the exact rows behind a number.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
from pydantic import BaseModel, Field

from app.engine.duckdb_engine import INGEST_LOG_TABLE, FinanceDB
from app.engine.schema import TABLES, Column, ColumnType, TableSpec, normalise_category, normalise_header

SUPPORTED_SUFFIXES = (".csv", ".xlsx")
MAPPINGS_FILE_NAME = "mappings.json"
MAX_REPORTED_ERRORS = 25
CENT = Decimal("0.01")
MAX_MONEY = Decimal(10) ** 16  # DECIMAL(18,2) holds 16 digits before the point
MONEY_TEXT = re.compile(r"-?(\d+(\.\d*)?|\.\d+)")
_MONTH_NAMES = {
    **dict.fromkeys(("jan", "january"), 1),
    **dict.fromkeys(("feb", "february"), 2),
    **dict.fromkeys(("mar", "march"), 3),
    **dict.fromkeys(("apr", "april"), 4),
    "may": 5,
    **dict.fromkeys(("jun", "june"), 6),
    **dict.fromkeys(("jul", "july"), 7),
    **dict.fromkeys(("aug", "august"), 8),
    **dict.fromkeys(("sep", "sept", "september"), 9),
    **dict.fromkeys(("oct", "october"), 10),
    **dict.fromkeys(("nov", "november"), 11),
    **dict.fromkeys(("dec", "december"), 12),
}


class IngestError(ValueError):
    """The file cannot be loaded. `errors` holds human-readable reasons (row-level where possible)."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class SheetMapping(BaseModel):
    table: str
    columns: dict[str, str] = Field(description="source header -> canonical column")


class TableReport(BaseModel):
    table: str
    source_file: str
    sheet: str | None
    rows: int
    columns: dict[str, str]
    unmapped_headers: list[str]
    warnings: list[str]


@dataclass
class RawSheet:
    file_name: str
    sheet: str | None
    headers: list[str]
    rows: list[tuple[int, list[Any]]]  # (row number in the file, cell values)

    @property
    def key(self) -> str:
        return f"{self.file_name}#{self.sheet}" if self.sheet else self.file_name


# --- reading -------------------------------------------------------------------------------------------------------
def read_file(path: Path, display_name: str | None = None) -> list[RawSheet]:
    """Read a CSV (one sheet) or XLSX (every non-empty sheet). The first row holds the headers."""
    name = display_name or path.name
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        return [_read_csv(path.read_bytes(), name)]
    if suffix == ".xlsx":
        return _read_xlsx(path, name)
    raise IngestError(f"Unsupported file type {suffix or '(none)'!r}; use one of {', '.join(SUPPORTED_SUFFIXES)}")


def _read_csv(data: bytes, name: str) -> RawSheet:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1252")  # Excel on Windows saves "CSV" in the ANSI code page
        except UnicodeDecodeError as exc:
            raise IngestError(f"{name}: not UTF-8 or Windows-1252 text; save it as 'CSV UTF-8' in Excel") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    headers = next(reader, None)
    if not headers or not any(h.strip() for h in headers):
        raise IngestError(f"{name}: the first row must contain column headers")
    rows = [(i, row) for i, row in enumerate(reader, start=2) if any(cell.strip() for cell in row)]
    return RawSheet(name, None, headers, rows)


def _read_xlsx(path: Path, name: str) -> list[RawSheet]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for corrupt or non-xlsx files
        raise IngestError(f"{name}: not a readable .xlsx workbook ({exc})") from exc
    sheets: list[RawSheet] = []
    try:
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            header_row = next(it, None)
            if not header_row or not any(h is not None and str(h).strip() for h in header_row):
                continue
            headers = ["" if h is None else str(h) for h in header_row]
            rows = [
                (i, list(row))
                for i, row in enumerate(it, start=2)
                if any(v is not None and str(v).strip() for v in row)
            ]
            sheets.append(RawSheet(name, ws.title, headers, rows))
    finally:
        wb.close()
    if not sheets:
        raise IngestError(f"{name}: the workbook has no sheet with headers")
    return sheets


# --- mapping -------------------------------------------------------------------------------------------------------
class MappingStore:
    """`data/<ws>/mappings.json`: `{"<file>[#<sheet>]": {"table": ..., "columns": {header: canonical}}}`."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / MAPPINGS_FILE_NAME

    def load(self) -> dict[str, SheetMapping]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {k: SheetMapping.model_validate(v) for k, v in raw.items()}
        except (ValueError, TypeError) as exc:
            raise IngestError(f"{self.path.name} is not valid JSON mapping data: {exc}") from exc

    def save(self, key: str, mapping: SheetMapping) -> None:
        data = self.load()
        data[key] = mapping
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.model_dump() for k, v in sorted(data.items())}
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def _name_tokens(text: str) -> str:
    return normalise_header(Path(text).stem if "." in text else text)


def detect_table(sheet: RawSheet, explicit: str | None, saved: SheetMapping | None) -> TableSpec:
    if explicit:
        if explicit not in TABLES:
            raise IngestError(f"Unknown table {explicit!r}; choose one of {', '.join(TABLES)}")
        return TABLES[explicit]
    if saved and saved.table in TABLES:
        return TABLES[saved.table]
    for candidate in filter(None, (sheet.sheet, sheet.file_name)):
        key = _name_tokens(candidate)
        for spec in TABLES.values():
            if key in spec.name_synonyms:
                return spec
        for spec in TABLES.values():  # e.g. "northwind_pnl_2025" contains "pnl"
            if any(re.search(rf"(^|_){re.escape(s)}(_|$)", key) for s in spec.name_synonyms):
                return spec
    # Fall back to the table whose required columns are all present, preferring the best overall header match.
    best: tuple[int, TableSpec] | None = None
    for spec in TABLES.values():
        try:
            mapped = map_columns(spec, sheet.headers, None)
        except IngestError:
            continue
        if best is None or len(mapped) > best[0]:
            best = (len(mapped), spec)
    if best is None:
        raise IngestError(
            f"{sheet.key}: cannot tell which table this is. Name the file or sheet after a table "
            f"({', '.join(TABLES)}) or choose the table explicitly."
        )
    return best[1]


def map_columns(spec: TableSpec, headers: list[str], saved: SheetMapping | None) -> dict[int, Column]:
    """Header index -> canonical column. Saved mappings win; then exact names; then synonyms."""
    result: dict[int, Column] = {}
    used: set[str] = set()
    normalised = [normalise_header(h) for h in headers]
    saved_columns = saved.columns if saved and saved.table == spec.name else {}

    def assign(index: int, column: Column) -> None:
        result[index] = column
        used.add(column.name)

    for i, header in enumerate(headers):
        target = saved_columns.get(header)
        if target and target not in used:
            try:
                assign(i, spec.column(target))
            except KeyError as exc:
                raise IngestError(f"Saved mapping points {header!r} at unknown column {target!r}") from exc
    for i, key in enumerate(normalised):
        if i in result:
            continue
        for column in spec.columns:
            if column.name not in used and key == column.name:
                assign(i, column)
                break
    for i, key in enumerate(normalised):
        if i in result:
            continue
        for column in spec.columns:
            if column.name not in used and key in column.synonyms:
                assign(i, column)
                break
    missing = [c.name for c in spec.required if c.name not in used]
    if missing:
        raise IngestError(
            f"{spec.name}: required column(s) not found: {', '.join(missing)}",
            [f"Headers in the file: {', '.join(h for h in headers if h.strip())}"],
        )
    return result


# --- parsing -------------------------------------------------------------------------------------------------------
def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_money(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("not a number")
    if isinstance(value, int | Decimal):
        number = Decimal(value)
    elif isinstance(value, float):
        number = Decimal(repr(value))
    else:
        text = str(value).strip().replace("\u2212", "-")  # Unicode minus sign
        # Accounting negatives: "(1,000)", "$(1,000)", "USD (250.00)".
        negative = bool(re.search(r"\(.*\)", text))
        text = text.replace("(", "").replace(")", "")
        # Currency codes as a prefix or suffix ("Rs. 1,000", "USD 10", "84,000 INR"), then symbols and separators.
        text = re.sub(r"(?i)^\s*(usd|inr|eur|gbp|rs\.?)|(usd|inr|eur|gbp)\s*$", "", text)
        text = re.sub(r"[$₹€£,\s]", "", text)
        if not MONEY_TEXT.fullmatch(text):
            raise ValueError("not a number")
        number = Decimal(text)
        if negative:
            number = -abs(number)
    if not number.is_finite():
        raise ValueError("not a finite number")
    if abs(number) >= MAX_MONEY:
        raise ValueError("too large (limit 10^16)")
    return number.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_month(value: Any) -> str:
    if isinstance(value, datetime | date):
        return f"{value.year:04d}-{value.month:02d}"
    text = str(value).strip()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?(?:[ T].*)?", text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"(\d{1,2})[-/.](\d{4})", text):
        month, year = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"([A-Za-z]+)[\s\-']+(\d{2}|\d{4})", text):
        month = _MONTH_NAMES.get(m.group(1).lower(), 0)
        year = int(m.group(2)) + (2000 if len(m.group(2)) == 2 else 0)
    else:
        raise ValueError("not a month (expected e.g. 2026-10, 2026-10-01 or Oct 2026)")
    if not 1 <= month <= 12 or not 1900 <= year <= 2200:
        raise ValueError("month or year out of range")
    return f"{year:04d}-{month:02d}"


def parse_integer(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("not a whole number")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("not a whole number")
        return int(value)
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"-?\d+", text):
        raise ValueError("not a whole number")
    return int(text)


def parse_ratio(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("not a number")
    text = str(value).strip() if not isinstance(value, float) else repr(value)
    percent = text.endswith("%")
    try:
        number = Decimal(text.rstrip("%").strip())
    except InvalidOperation as exc:
        raise ValueError("not a number") from exc
    if percent:
        number /= 100
    if not 0 <= number <= 1:
        raise ValueError("must be between 0 and 1 (or 0% and 100%)")
    return number.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def parse_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # Excel stores ids typed as numbers as floats
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value).strip()


PARSERS = {
    ColumnType.TEXT: parse_text,
    ColumnType.MONTH: parse_month,
    ColumnType.MONEY: parse_money,
    ColumnType.INTEGER: parse_integer,
    ColumnType.RATIO: parse_ratio,
}


def parse_rows(spec: TableSpec, sheet: RawSheet, mapping: dict[int, Column]) -> list[list[Any]]:
    """Canonical rows (in `spec.columns` order) + provenance. Raises `IngestError` listing every bad cell."""
    errors: list[str] = []
    out: list[list[Any]] = []
    order = {c.name: n for n, c in enumerate(spec.columns)}
    for row_number, cells in sheet.rows:
        values: list[Any] = [None] * len(spec.columns)
        for index, column in mapping.items():
            raw = cells[index] if index < len(cells) else None
            if _blank(raw):
                if column.required:
                    errors.append(f"row {row_number}, {sheet.headers[index]!r}: value is required")
                continue
            try:
                value = PARSERS[column.type](raw)
                if spec.name == "pnl" and column.name == "category":
                    canonical = normalise_category(value)
                    if canonical is None:
                        raise ValueError("expected Revenue, COGS or Operating expense")
                    value = canonical
            except ValueError as exc:
                errors.append(f"row {row_number}, {sheet.headers[index]!r}: {raw!r} is {exc}")
                continue
            values[order[column.name]] = value
        out.append([*values, sheet.file_name, sheet.sheet, row_number])
    if spec.name == "bank_balance":
        # Metrics read one bank row per month (burn sums the window, runway reads the closing balance).
        first_seen: dict[str, int] = {}
        month_index = [c.name for c in spec.columns].index("month")
        for row in out:
            month, row_number = row[month_index], row[-1]
            if month is None:
                continue
            if month in first_seen:
                errors.append(f"row {row_number}: month {month} already appears in row {first_seen[month]}")
            else:
                first_seen[month] = row_number
    if errors:
        shown = errors[:MAX_REPORTED_ERRORS]
        more = len(errors) - len(shown)
        raise IngestError(
            f"{sheet.key}: {len(errors)} invalid value(s); nothing was loaded",
            shown + ([f"... and {more} more"] if more else []),
        )
    if not out:
        raise IngestError(f"{sheet.key}: no data rows")
    return out


def validation_warnings(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    """Non-fatal consistency checks after loading (identities a founder would want to know about)."""
    checks = {
        "bank_balance": [
            (
                "SELECT count(*) FROM bank_balance WHERE closing_balance <> opening_balance + cash_in - cash_out",
                "{n} month(s) where closing_balance <> opening_balance + cash_in - cash_out",
            ),
        ],
        "subscriptions": [
            (
                "SELECT count(*) FROM (SELECT 1 FROM subscriptions GROUP BY month, customer_id HAVING count(*) > 1)",
                "{n} customer-month(s) appear more than once; their MRR is added together",
            ),
        ],
    }
    warnings: list[str] = []
    for sql, message in checks.get(table, []):
        row = con.execute(sql).fetchone()
        if row and row[0]:
            warnings.append(message.format(n=row[0]))
    return warnings


# --- loading -------------------------------------------------------------------------------------------------------
def _create_and_insert(con: duckdb.DuckDBPyConnection, spec: TableSpec, rows: list[list[Any]]) -> None:
    cols = ", ".join(f'"{c.name}" {c.sql_type}' for c in spec.columns)
    con.execute(
        f'CREATE OR REPLACE TABLE "{spec.name}" ({cols}, _source_file VARCHAR, _source_sheet VARCHAR, '
        "_source_row INTEGER)"
    )
    # Bulk load through a registered column view (numpy object arrays, values as text, cast in SQL): DuckDB's
    # executemany runs one statement per row and is far slower.
    names = [c.name for c in spec.columns] + ["_source_file", "_source_sheet", "_source_row"]
    types = [c.sql_type for c in spec.columns] + ["VARCHAR", "VARCHAR", "INTEGER"]
    view = {
        f"c{i}": np.array([None if row[i] is None else str(row[i]) for row in rows], dtype=object)
        for i in range(len(names))
    }
    con.register("_ingest_rows", view)
    try:
        select = ", ".join(f"CAST(c{i} AS {t})" for i, t in enumerate(types))
        try:
            con.execute(f'INSERT INTO "{spec.name}" SELECT {select} FROM _ingest_rows')
        except duckdb.Error as exc:  # parsed values are validated, so this is a safety net, not the normal path
            raise IngestError(f"{spec.name}: could not store the data ({exc})") from exc
    finally:
        con.unregister("_ingest_rows")


def _append(con: duckdb.DuckDBPyConnection, spec: TableSpec, rows: list[list[Any]]) -> None:
    """Add rows to a table that is already loaded, through a scratch table with the same columns."""
    scratch = TableSpec(name=f"_append_{spec.name}", description=spec.description, columns=spec.columns)
    _create_and_insert(con, scratch, rows)
    try:
        con.execute(f'INSERT INTO "{spec.name}" SELECT * FROM "{scratch.name}"')
    except duckdb.Error as exc:
        raise IngestError(f"{spec.name}: these rows could not be added ({exc})") from exc
    finally:
        con.execute(f'DROP TABLE IF EXISTS "{scratch.name}"')


def _log(con: duckdb.DuckDBPyConnection, report: TableReport) -> None:
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {INGEST_LOG_TABLE} (table_name VARCHAR PRIMARY KEY, source_file VARCHAR, "
        "source_sheet VARCHAR, row_count BIGINT, columns_json VARCHAR, ingested_at TIMESTAMP)"
    )
    con.execute(
        f"INSERT OR REPLACE INTO {INGEST_LOG_TABLE} VALUES (?, ?, ?, ?, ?, ?)",
        [
            report.table,
            report.source_file,
            report.sheet,
            report.rows,
            json.dumps(report.columns),
            datetime.now(UTC).replace(tzinfo=None),
        ],
    )


BACKUP_PREFIX = "_backup_"
BACKUPS_TABLE = "_backups"
IngestMode = Literal["replace", "append"]


class Conflict(BaseModel):
    """A table the upload would change that already holds data: the founder chooses before anything is written."""

    table: str
    existing_rows: int
    existing_source: str | None
    incoming_rows: int
    incoming_source: str


class BackupInfo(BaseModel):
    table: str
    rows: int
    source_file: str | None
    saved_at: str


def ingest_file(
    db: FinanceDB,
    path: Path,
    *,
    table: str | None = None,
    display_name: str | None = None,
    mode: IngestMode = "replace",
) -> list[TableReport]:
    """Load every sheet of `path`. All sheets are parsed before anything is written, so a bad sheet loads nothing."""
    sheets = read_file(path, display_name)
    if table and len(sheets) > 1:
        raise IngestError("Choosing a table is only possible for single-sheet files")
    return _ingest_sheets(db, sheets, table, mode=mode, backup=True)


def upload_conflicts(
    db: FinanceDB, path: Path, *, table: str | None = None, display_name: str | None = None
) -> list[Conflict]:
    """Which tables `path` would change that already hold rows, with both row counts. Writes nothing.

    Seen in the founder's review: a one-row file mapped to `pnl` replaced all 360 rows, with no warning.
    """
    sheets = read_file(path, display_name)
    if table and len(sheets) > 1:
        raise IngestError("Choosing a table is only possible for single-sheet files")
    prepared = _prepare(db, sheets, table)
    if not db.path.exists():
        return []  # nothing loaded yet, so nothing to overwrite
    loaded = {row["table"]: row for row in ingest_log(db)}
    conflicts: list[Conflict] = []
    with db.connect() as con:
        present = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        for spec, sheet, _, rows in prepared:
            if spec.name not in present:
                continue
            count = con.execute(f'SELECT count(*) FROM "{spec.name}"').fetchone()
            existing = int(count[0]) if count else 0
            if existing:
                conflicts.append(
                    Conflict(
                        table=spec.name,
                        existing_rows=existing,
                        existing_source=loaded.get(spec.name, {}).get("source_file"),
                        incoming_rows=len(rows),
                        incoming_source=sheet.file_name,
                    )
                )
    return conflicts


def _backup(con: duckdb.DuckDBPyConnection, name: str) -> None:
    """Keep the table as it was before this upload, with its log row, so the upload can be undone."""
    present = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()
    if not present or not present[0]:
        return
    con.execute(f'CREATE OR REPLACE TABLE "{BACKUP_PREFIX}{name}" AS SELECT * FROM "{name}"')
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {BACKUPS_TABLE} (table_name VARCHAR PRIMARY KEY, row_count BIGINT, "
        "source_file VARCHAR, log_json VARCHAR, saved_at TIMESTAMP)"
    )
    log: dict[str, Any] | None = None
    has_log = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [INGEST_LOG_TABLE]
    ).fetchone()
    if has_log and has_log[0]:
        row = con.execute(
            f"SELECT source_file, source_sheet, row_count, columns_json FROM {INGEST_LOG_TABLE} WHERE table_name = ?",
            [name],
        ).fetchone()
        if row:
            log = {"source_file": row[0], "sheet": row[1], "rows": row[2], "columns_json": row[3]}
    count = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()
    con.execute(
        f"INSERT OR REPLACE INTO {BACKUPS_TABLE} VALUES (?, ?, ?, ?, ?)",
        [
            name,
            int(count[0]) if count else 0,
            log["source_file"] if log else None,
            json.dumps(log) if log else None,
            datetime.now(UTC).replace(tzinfo=None),
        ],
    )


def backups(db: FinanceDB) -> list[BackupInfo]:
    if not db.path.exists():
        return []
    with db.connect() as con:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [BACKUPS_TABLE]
        ).fetchone()
        if not exists or not exists[0]:
            return []
        rows = con.execute(
            f"SELECT table_name, row_count, source_file, saved_at FROM {BACKUPS_TABLE} ORDER BY table_name"
        ).fetchall()
    return [
        BackupInfo(table=t, rows=int(n), source_file=f, saved_at=at.isoformat() if at else "") for t, n, f, at in rows
    ]


def undo_upload(db: FinanceDB, name: str) -> BackupInfo:
    """Put a table back as it was before the last upload that changed it. The backup is used up."""
    found = next((b for b in backups(db) if b.table == name), None)
    if found is None:
        raise IngestError(f"There is no earlier version of {name} to go back to")
    with db.connect(read_only=False) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM "{BACKUP_PREFIX}{name}"')
            row = con.execute(f"SELECT log_json FROM {BACKUPS_TABLE} WHERE table_name = ?", [name]).fetchone()
            log = json.loads(row[0]) if row and row[0] else None
            if log is not None:
                con.execute(
                    f"INSERT OR REPLACE INTO {INGEST_LOG_TABLE} VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        name,
                        log["source_file"],
                        log["sheet"],
                        log["rows"],
                        log["columns_json"],
                        datetime.now(UTC).replace(tzinfo=None),
                    ],
                )
            con.execute(f'DROP TABLE "{BACKUP_PREFIX}{name}"')
            con.execute(f"DELETE FROM {BACKUPS_TABLE} WHERE table_name = ?", [name])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return found


def ingest_directory(db: FinanceDB, directory: Path) -> list[TableReport]:
    """Load every canonical-table CSV found in `directory` (e.g. `sample_data/`) in one transaction."""
    files = [directory / f"{name}.csv" for name in TABLES if (directory / f"{name}.csv").exists()]
    if not files:
        raise IngestError(f"No table CSVs found in {directory}")
    return _ingest_sheets(db, [sheet for path in files for sheet in read_file(path)], None)


Prepared = list[tuple[TableSpec, RawSheet, dict[int, Column], list[list[Any]]]]


def _prepare(db: FinanceDB, sheets: list[RawSheet], table: str | None) -> Prepared:
    saved_all = MappingStore(db.data_dir).load()
    prepared: Prepared = []
    seen: set[str] = set()
    for sheet in sheets:
        saved = saved_all.get(sheet.key)
        spec = detect_table(sheet, table, saved)
        if spec.name in seen:
            raise IngestError(f"{sheet.key}: more than one sheet maps to table {spec.name!r}")
        seen.add(spec.name)
        mapping = map_columns(spec, sheet.headers, saved)
        prepared.append((spec, sheet, mapping, parse_rows(spec, sheet, mapping)))
    return prepared


def _ingest_sheets(
    db: FinanceDB,
    sheets: list[RawSheet],
    table: str | None,
    *,
    mode: IngestMode = "replace",
    backup: bool = False,
) -> list[TableReport]:
    store = MappingStore(db.data_dir)
    prepared = _prepare(db, sheets, table)
    loaded = {row["table"]: row for row in ingest_log(db)} if mode == "append" else {}

    reports: list[TableReport] = []
    with db.connect(read_only=False) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            for spec, sheet, mapping, rows in prepared:
                if backup:
                    _backup(con, spec.name)
                total = len(rows)
                source = sheet.file_name
                if mode == "append" and spec.name in loaded:
                    _append(con, spec, rows)
                    count = con.execute(f'SELECT count(*) FROM "{spec.name}"').fetchone()
                    total = int(count[0]) if count else len(rows)
                    before = loaded[spec.name].get("source_file")
                    source = sheet.file_name if not before or before == sheet.file_name else f"{before} + {source}"
                else:
                    _create_and_insert(con, spec, rows)
                report = TableReport(
                    table=spec.name,
                    source_file=source,
                    sheet=sheet.sheet,
                    rows=total,
                    columns={sheet.headers[i]: c.name for i, c in sorted(mapping.items())},
                    unmapped_headers=[h for i, h in enumerate(sheet.headers) if i not in mapping and h.strip()],
                    warnings=validation_warnings(con, spec.name),
                )
                _log(con, report)
                reports.append(report)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    for (_, sheet, _, _), report in zip(prepared, reports, strict=True):
        store.save(sheet.key, SheetMapping(table=report.table, columns=report.columns))
    return reports


def ingest_log(db: FinanceDB) -> list[dict[str, Any]]:
    if not db.path.exists():
        return []
    with db.connect() as con:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [INGEST_LOG_TABLE]
        ).fetchone()
        if not exists or not exists[0]:
            return []
        rows = con.execute(
            f"SELECT table_name, source_file, source_sheet, row_count, columns_json, ingested_at "
            f"FROM {INGEST_LOG_TABLE} ORDER BY table_name"
        ).fetchall()
    return [
        {
            "table": t,
            "source_file": f,
            "sheet": s,
            "rows": n,
            "columns": json.loads(c),
            "ingested_at": at.isoformat() if at else None,
        }
        for t, f, s, n, c, at in rows
    ]
