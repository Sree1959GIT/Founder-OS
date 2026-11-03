"""Guarded SQL: the fallback path when no pre-built metric routine fits (PRD R1).

An agent-written (or user-written) query only runs if it is exactly one SELECT statement, reads only canonical
tables of this workspace (no table functions such as `read_csv`, no file paths, no system catalogs, no internal
`_` tables) and finishes within the row and time limits. It runs on a read-only connection with external access
disabled, so even a query that slipped past the parser could not write or touch the file system.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import duckdb
from pydantic import BaseModel

from app.engine.duckdb_engine import FinanceDB
from app.engine.lineage import Lineage, SourceRef
from app.engine.schema import TABLES

DEFAULT_MAX_ROWS = 1000
DEFAULT_TIMEOUT_S = 5.0
MAX_SQL_CHARS = 10_000


class SqlGuardError(ValueError):
    """The query was rejected before running, or failed / timed out while running."""


class GuardedQueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float
    lineage: Lineage


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def validate_sql(con: duckdb.DuckDBPyConnection, sql: str, allowed_tables: set[str]) -> tuple[str, set[str]]:
    """Return the cleaned statement and the tables it reads, or raise `SqlGuardError`."""
    if len(sql) > MAX_SQL_CHARS:
        raise SqlGuardError(f"Query is longer than {MAX_SQL_CHARS} characters")
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        raise SqlGuardError(f"Query does not parse: {exc}") from exc
    if len(statements) != 1:
        raise SqlGuardError(f"Exactly one statement is allowed (got {len(statements)})")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise SqlGuardError(f"Only SELECT queries are allowed (got {statements[0].type.name})")
    cleaned = sql.strip().rstrip(";").strip()

    row = con.execute("SELECT json_serialize_sql(?)", [cleaned]).fetchone()
    ast = json.loads(row[0]) if row else {"error": True, "error_message": "no parse result"}
    if ast.get("error"):
        raise SqlGuardError(f"Query does not parse: {ast.get('error_message')}")
    for node in _walk(ast):
        node_type = node.get("type")
        if node_type == "TABLE_FUNCTION":
            raise SqlGuardError("Table functions (e.g. read_csv, glob) are not allowed")
        if node_type == "BASE_TABLE" and (node.get("catalog_name") or node.get("schema_name") not in ("", "main")):
            raise SqlGuardError("Only tables in the workspace database may be queried")

    try:
        tables = set(con.get_table_names(cleaned))
    except duckdb.Error as exc:
        raise SqlGuardError(f"Query does not parse: {exc}") from exc
    forbidden = sorted(t for t in tables if t not in allowed_tables)
    if forbidden:
        raise SqlGuardError(
            f"Table(s) not allowed: {', '.join(forbidden)}. Allowed: {', '.join(sorted(allowed_tables)) or 'none'}"
        )
    return cleaned, tables


def run_guarded_query(
    db: FinanceDB,
    sql: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> GuardedQueryResult:
    allowed = db.tables() & set(TABLES)
    started = datetime.now(UTC)
    with db.connect(read_only=True) as con:
        cleaned, tables = validate_sql(con, sql, allowed)
        wrapped = f"SELECT * FROM ({cleaned}) AS guarded_query LIMIT {int(max_rows) + 1}"
        timer = threading.Timer(timeout_s, con.interrupt)
        timer.start()
        try:
            cursor = con.execute(wrapped)
            columns = [d[0] for d in cursor.description or []]
            rows = cursor.fetchall()
        except duckdb.InterruptException as exc:
            raise SqlGuardError(f"Query exceeded the {timeout_s:g} s time limit") from exc
        except duckdb.Error as exc:
            raise SqlGuardError(f"Query failed: {exc}") from exc
        finally:
            timer.cancel()
        sources = [
            SourceRef(table=t, file=f, sheet=s, rows="all", row_count=n)
            for t in sorted(tables)
            for f, s, n in con.execute(
                f'SELECT _source_file, _source_sheet, count(*) FROM "{t}" GROUP BY ALL ORDER BY 1, 2'
            ).fetchall()
        ]
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    elapsed_ms = (datetime.now(UTC) - started).total_seconds() * 1000
    return GuardedQueryResult(
        columns=columns,
        rows=[list(r) for r in rows],
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=round(elapsed_ms, 1),
        lineage=Lineage(
            metric="guarded_sql",
            sql=[cleaned],
            source_files=sorted({s.file for s in sources}),
            source_rows=sources,
            formula="Result of the validated query (read-only, single SELECT, table allow-list)",
            computed_at=started,
        ),
    )
