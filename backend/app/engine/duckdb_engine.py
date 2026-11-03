"""The workspace DuckDB database (`data/<ws>/founder.duckdb`).

One `FinanceDB` per workspace. Connections are short-lived and serialised by a lock: DuckDB does not allow a
read-write and a read-only connection to the same file at the same time within one process, and the data volumes
here (thousands of rows) make opening a connection cheap. External file access is disabled on every connection, so
SQL can never read or write files outside the database (e.g. `read_csv('C:/...')` or `COPY ... TO`).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

DB_FILE_NAME = "founder.duckdb"
INGEST_LOG_TABLE = "_ingest_log"


class NoDataError(RuntimeError):
    """The workspace has no financial data loaded yet (or the table needed is missing)."""


class FinanceDB:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / DB_FILE_NAME
        self._lock = threading.RLock()
        # Bumped on every write; caches (e.g. scenario drivers) key on it.
        self.version = 0

    @contextmanager
    def connect(self, *, read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
        with self._lock:
            if read_only and not self.path.exists():
                raise NoDataError("No financial data loaded yet. Load the sample data or upload a file.")
            if not read_only:
                self.data_dir.mkdir(parents=True, exist_ok=True)
            con = duckdb.connect(str(self.path), read_only=read_only, config={"enable_external_access": False})
            try:
                yield con
            finally:
                con.close()
                if not read_only:
                    self.version += 1

    def tables(self) -> set[str]:
        """Names of the user tables present (excluding internal ones)."""
        if not self.path.exists():
            return set()
        with self.connect() as con:
            rows = con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        return {name for (name,) in rows if not name.startswith("_")}
