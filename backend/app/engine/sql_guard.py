"""Guarded SQL: the fallback path when no pre-built metric routine fits (PRD R1).

An agent-written (or user-written) query only runs if it is exactly one SELECT statement, reads only canonical
tables of this workspace (no table functions such as `read_csv`, no file paths, no system catalogs, no internal
`_` tables) and finishes within the row and time limits. It runs on a read-only connection with external access
disabled, so even a query that slipped past the parser could not write or touch the file system.
"""

from __future__ import annotations

import json
import re
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
CTE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


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
    """Return the statement to run and the tables it reads, or raise `SqlGuardError`.

    The statement returned is DuckDB's own re-serialisation of the validated AST (comments and `;` removed), so what
    runs is exactly what was checked.
    """
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

    row = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()
    ast = json.loads(row[0]) if row else {"error": True, "error_message": "no parse result"}
    if ast.get("error"):
        raise SqlGuardError(f"Query does not parse: {ast.get('error_message')}")
    cte_names: set[str] = set()
    referenced: set[str] = set()
    for node in _walk(ast):
        node_type = node.get("type")
        if node_type == "TABLE_FUNCTION":
            raise SqlGuardError("Table functions (e.g. read_csv, glob) are not allowed")
        if node_type == "BASE_TABLE":
            if node.get("catalog_name") or node.get("schema_name") not in ("", "main"):
                raise SqlGuardError("Only tables in the workspace database may be queried")
            referenced.add(str(node.get("table_name")))
        cte_map = node.get("cte_map")
        if isinstance(cte_map, dict):
            cte_names.update(str(entry.get("key")) for entry in cte_map.get("map", []))
    # CTE references are not table reads. CTE scopes are not tracked, so a CTE must never be able to stand in for
    # a table that is not allowed: the only such tables are internal (`_` prefix) and file paths, and both are
    # impossible as plain CTE names.
    for name in cte_names:
        if not CTE_NAME.fullmatch(name):
            raise SqlGuardError(f"CTE name {name!r} is not allowed (use letters, digits and _, not starting with _)")
    tables = referenced - cte_names
    forbidden = sorted(t for t in tables if t not in allowed_tables)
    if forbidden:
        raise SqlGuardError(
            f"Table(s) not allowed: {', '.join(forbidden)}. Allowed: {', '.join(sorted(allowed_tables)) or 'none'}"
        )
    canonical = con.execute("SELECT json_deserialize_sql(?)", [row[0]]).fetchone() if row else None
    if not canonical or not canonical[0]:
        raise SqlGuardError("Query could not be normalised")
    return str(canonical[0]), tables


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
