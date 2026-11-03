"""`/api/data/*`: load financial files, inspect tables and mappings, run guarded SQL."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.deps import FinanceDep, SettingsDep
from app.engine.ingest import SUPPORTED_SUFFIXES, MappingStore, TableReport, ingest_directory, ingest_file, ingest_log
from app.engine.schema import TABLES
from app.engine.sql_guard import DEFAULT_MAX_ROWS, GuardedQueryResult, run_guarded_query

router = APIRouter(prefix="/data", tags=["data"])

UPLOADS_DIR_NAME = "uploads"
CHUNK_BYTES = 1024 * 1024


class IngestResponse(BaseModel):
    tables: list[TableReport]


class TablesResponse(BaseModel):
    loaded: list[dict[str, Any]]
    canonical: list[dict[str, Any]]


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1)
    max_rows: int = Field(DEFAULT_MAX_ROWS, ge=1, le=10_000)


def safe_file_name(name: str) -> str:
    """Keep only the base name and a conservative character set (no paths, no reserved characters)."""
    base = Path(name.replace("\\", "/")).name
    stem, suffix = Path(base).stem, Path(base).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9 ._-]", "_", stem).strip(" .")[:100] or "upload"
    return f"{stem}{suffix}"


@router.get("/tables", response_model=TablesResponse)
def tables(finance: FinanceDep) -> TablesResponse:
    """What is loaded (table, source file, rows, column mapping) and the canonical schema."""
    return TablesResponse(
        loaded=ingest_log(finance.db),
        canonical=[
            {
                "table": spec.name,
                "description": spec.description,
                "columns": [
                    {"name": c.name, "type": c.type.value, "required": c.required, "synonyms": list(c.synonyms)}
                    for c in spec.columns
                ],
            }
            for spec in TABLES.values()
        ],
    )


@router.get("/mappings")
def mappings(finance: FinanceDep) -> dict[str, Any]:
    return {key: m.model_dump() for key, m in MappingStore(finance.db.data_dir).load().items()}


@router.post("/load-sample", response_model=IngestResponse)
def load_sample(settings: SettingsDep, finance: FinanceDep) -> IngestResponse:
    """(Re)load the Northwind demo data from `sample_data/`, replacing those tables."""
    return IngestResponse(tables=ingest_directory(finance.db, settings.sample_data_path()))


@router.post("/upload", response_model=IngestResponse)
def upload(
    settings: SettingsDep,
    finance: FinanceDep,
    file: Annotated[UploadFile, File(description="CSV or XLSX")],
    table: Annotated[str | None, Form(description="Canonical table (optional; auto-detected)")] = None,
) -> IngestResponse:
    name = safe_file_name(file.filename or "upload")
    if Path(name).suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail=f"Only {', '.join(SUPPORTED_SUFFIXES)} files are accepted")
    limit = settings.max_upload_mb * 1024 * 1024
    uploads = finance.db.data_dir / UPLOADS_DIR_NAME
    uploads.mkdir(parents=True, exist_ok=True)
    partial = uploads / f".partial-{name}"  # keeps the suffix (openpyxl checks it)
    size = 0
    try:
        with partial.open("wb") as out:
            while chunk := file.file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_mb} MB")
                out.write(chunk)
        reports = ingest_file(finance.db, partial, table=table or None, display_name=name)
        # Keep the accepted file so lineage can point at it.
        shutil.move(partial, uploads / name)
    finally:
        partial.unlink(missing_ok=True)
    return IngestResponse(tables=reports)


@router.post("/query", response_model=GuardedQueryResult)
def query(body: QueryRequest, finance: FinanceDep) -> GuardedQueryResult:
    """Run one read-only SELECT over the loaded tables (SQL guard: single statement, allow-list, limits)."""
    return run_guarded_query(finance.db, body.sql, max_rows=body.max_rows)
