"""SQL guard: only a single read-only SELECT over canonical tables, within row and time limits."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.duckdb_engine import FinanceDB
from app.engine.sql_guard import SqlGuardError, run_guarded_query


def test_simple_select(loaded_db: FinanceDB) -> None:
    result = run_guarded_query(loaded_db, "SELECT closing_balance FROM bank_balance WHERE month = '2026-10';")
    assert result.columns == ["closing_balance"]
    assert result.rows == [[Decimal("1835125.06")]]
    assert not result.truncated
    assert result.lineage.source_files == ["bank_balance.csv"]
    # The lineage holds the statement that ran: DuckDB's canonical form of the validated query.
    assert result.lineage.sql == ["SELECT closing_balance FROM bank_balance WHERE (\"month\" = '2026-10')"]


def test_cte_and_join_allowed(loaded_db: FinanceDB) -> None:
    sql = """WITH s AS (SELECT customer_id, sum(mrr) AS mrr FROM subscriptions WHERE month = '2026-10' GROUP BY 1)
             SELECT c.segment, sum(s.mrr) FROM s JOIN customers c USING (customer_id) GROUP BY 1 ORDER BY 1"""
    result = run_guarded_query(loaded_db, sql)
    assert sum(r[1] for r in result.rows) == Decimal("255344.27")
    assert sorted(result.lineage.source_files) == ["customers.csv", "subscriptions.csv"]


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("DROP TABLE pnl", "Only SELECT"),
        ("DELETE FROM pnl", "Only SELECT"),
        ("INSERT INTO pnl SELECT * FROM pnl", "Only SELECT"),
        ("CREATE TABLE x AS SELECT 1", "Only SELECT"),
        ("COPY pnl TO 'out.csv'", "Only SELECT"),
        ("ATTACH 'other.duckdb'", "Only SELECT"),
        ("PRAGMA database_list", "Only SELECT"),
        ("SET enable_external_access = true", "Only SELECT"),
        ("SELECT 1; SELECT 2", "Exactly one statement"),
        ("SELECT 1; DROP TABLE pnl", "Exactly one statement"),
        ("SELECT * FROM read_csv('C:/Windows/win.ini')", "Table functions"),
        ("SELECT * FROM glob('*')", "Table functions"),
        ("SELECT * FROM 'sample_data/pnl.csv'", "not allowed"),
        ("SELECT * FROM information_schema.tables", "workspace database"),
        ("SELECT * FROM _ingest_log", "not allowed"),
        ("SELECT * FROM secrets", "not allowed"),
        ("WITH pnl AS (SELECT * FROM _ingest_log) SELECT * FROM pnl", "not allowed"),
        # Review finding: a CTE in a subquery could hide a real read of an internal table elsewhere.
        (
            "SELECT * FROM (WITH _ingest_log AS (SELECT 1 AS x) SELECT * FROM _ingest_log) a, _ingest_log",
            "CTE name",
        ),
        ('WITH "pnl.csv" AS (SELECT 1) SELECT * FROM "pnl.csv"', "CTE name"),
        ("SELECT * FROM pnl WHERE amount > (SELECT count(*) FROM _ingest_log)", "not allowed"),
        ("SELECT * FROM (SELECT * FROM duckdb_settings())", "Table functions"),
        ("SELEC 1", "does not parse"),
        ("SELECT " + "1 + " * 5000 + "1", "longer than"),
    ],
)
def test_rejected(loaded_db: FinanceDB, sql: str, message: str) -> None:
    with pytest.raises(SqlGuardError, match=message):
        run_guarded_query(loaded_db, sql)


def test_trailing_comment_and_semicolon(loaded_db: FinanceDB) -> None:
    """Review finding: a trailing `--` comment swallowed the wrapper's closing parenthesis."""
    result = run_guarded_query(loaded_db, "SELECT count(*) AS n FROM pnl -- total rows")
    assert result.rows == [[360]]
    assert run_guarded_query(loaded_db, "SELECT count(*) FROM pnl; -- done").rows == [[360]]


def test_row_limit(loaded_db: FinanceDB) -> None:
    result = run_guarded_query(loaded_db, "SELECT * FROM subscriptions", max_rows=10)
    assert result.row_count == 10
    assert result.truncated


def test_timeout(loaded_db: FinanceDB) -> None:
    slow = "SELECT count(*) FROM subscriptions a, subscriptions b, subscriptions c WHERE a.mrr + b.mrr > c.mrr"
    with pytest.raises(SqlGuardError, match="time limit"):
        run_guarded_query(loaded_db, slow, timeout_s=0.2)


def test_connection_cannot_touch_files(loaded_db: FinanceDB) -> None:
    """Defence in depth: even unguarded SQL on our connections cannot read files."""
    import duckdb

    with loaded_db.connect() as con, pytest.raises(duckdb.Error, match="disabled"):
        con.execute("SELECT * FROM read_csv('pnl.csv')").fetchall()
