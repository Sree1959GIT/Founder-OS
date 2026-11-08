"""`/api/data/*`: load financial files, inspect tables and mappings, run guarded SQL."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.deps import FinanceDep, SettingsDep
from app.engine.ingest import (
    SUPPORTED_SUFFIXES,
    BackupInfo,
    Conflict,
    IngestError,
    MadeBy,
    MappingStore,
    SheetMapping,
    TableReport,
    backups,
    ingest_directory,
    ingest_file,
    ingest_log,
    undo_upload,
    upload_conflicts,
)
from app.engine.schema import TABLES
from app.engine.sql_guard import DEFAULT_MAX_ROWS, GuardedQueryResult, run_guarded_query

router = APIRouter(prefix="/data", tags=["data"])

UPLOADS_DIR_NAME = "uploads"
SAMPLE_WORKBOOK = "northwind_financials.xlsx"
CHUNK_BYTES = 1024 * 1024


class IngestResponse(BaseModel):
    tables: list[TableReport]
    conflicts: list[Conflict] = Field(
        default_factory=list,
        description="mode=check only: tables that already hold rows. Nothing was written; upload again with a mode",
    )
    backups: list[BackupInfo] = Field(default_factory=list, description="Earlier versions that Undo can restore")


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


class MappingUpdate(BaseModel):
    key: str = Field(min_length=1, max_length=300, description="File name, as `<file>` or `<file>#<sheet>`")
    table: str
    columns: dict[str, str] = Field(description="Source header -> canonical column")


@router.put("/mappings")
def save_mapping(body: MappingUpdate, finance: FinanceDep) -> dict[str, Any]:
    """Save how a file's columns map. It applies the next time that file is uploaded, and wins over auto-detection."""
    spec = TABLES.get(body.table)
    if spec is None:
        raise HTTPException(status_code=422, detail=f"Unknown table: {body.table}")
    known = {column.name for column in spec.columns}
    unknown = sorted(set(body.columns.values()) - known)
    if unknown:
        raise HTTPException(status_code=422, detail=f"{body.table} has no column: {', '.join(unknown)}")
    targets = list(body.columns.values())
    if len(targets) != len(set(targets)):
        raise HTTPException(status_code=422, detail="Two source columns point at the same column")
    name, _, sheet = body.key.partition("#")
    key = f"{safe_file_name(name)}#{sheet}" if sheet else safe_file_name(name)  # the name ingest will look it up by
    store = MappingStore(finance.db.data_dir)
    store.save(key, SheetMapping(table=body.table, columns=body.columns))
    return {key: m.model_dump() for key, m in store.load().items()}


@router.post("/load-sample", response_model=IngestResponse)
def load_sample(settings: SettingsDep, finance: FinanceDep) -> IngestResponse:
    """(Re)load the Northwind demo data, replacing those tables, all from one file (founder review 33).

    The workbook holds every table, one sheet each, so every table's lineage names the same source. Without it, the
    CSVs are used. A table that is not the sample now is kept as an earlier version first, so this can be undone.
    It is a reset: each sheet goes to its own table whatever mapping was saved (founder re-test 46).
    """
    folder = settings.sample_data_path()
    workbook = folder / SAMPLE_WORKBOOK
    if workbook.is_file():
        tables = ingest_file(finance.db, workbook, made_by="sample", use_saved_mappings=False)
    else:
        tables = ingest_directory(finance.db, folder, made_by="sample")
    return IngestResponse(tables=tables, backups=backups(finance.db))


@router.post("/upload", response_model=IngestResponse)
def upload(
    settings: SettingsDep,
    finance: FinanceDep,
    file: Annotated[UploadFile, File(description="CSV or XLSX")],
    table: Annotated[str | None, Form(description="Canonical table (optional; auto-detected)")] = None,
    mode: Annotated[
        Literal["check", "replace", "append"],
        Form(description="check (default): write nothing if a table already holds rows; replace or append: do it"),
    ] = "check",
    via: Annotated[
        Literal["upload", "mapping"], Form(description="mapping: the retry after the founder mapped the columns")
    ] = "upload",
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
        if mode == "check":
            conflicts = upload_conflicts(finance.db, partial, table=table or None, display_name=name)
            if conflicts:
                return IngestResponse(tables=[], conflicts=conflicts, backups=backups(finance.db))
        write_mode: Literal["replace", "append"] = "append" if mode == "append" else "replace"
        made_by: MadeBy = "append" if write_mode == "append" else via
        reports = ingest_file(
            finance.db, partial, table=table or None, display_name=name, mode=write_mode, made_by=made_by
        )
        # Keep the accepted file so lineage can point at it.
        shutil.move(partial, uploads / name)
    finally:
        partial.unlink(missing_ok=True)
    return IngestResponse(tables=reports, backups=backups(finance.db))


class UndoRequest(BaseModel):
    table: str = Field(min_length=1, max_length=64)
    version_id: str | None = Field(None, max_length=32, description="Which earlier version; the newest if left out")


@router.get("/backups")
def list_backups(finance: FinanceDep) -> list[BackupInfo]:
    return backups(finance.db)


@router.post("/undo")
def undo(body: UndoRequest, finance: FinanceDep) -> dict[str, Any]:
    """Put a table back to an earlier version (the newest, or `version_id`). The current one is kept in turn."""
    if body.table not in TABLES:
        raise HTTPException(status_code=422, detail=f"Unknown table: {body.table}")
    try:
        restored = undo_upload(finance.db, body.table, body.version_id)
    except IngestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"restored": restored.model_dump(), "loaded": ingest_log(finance.db)}


@router.post("/query", response_model=GuardedQueryResult)
def query(body: QueryRequest, finance: FinanceDep) -> GuardedQueryResult:
    """Run one read-only SELECT over the loaded tables (SQL guard: single statement, allow-list, limits)."""
    return run_guarded_query(finance.db, body.sql, max_rows=body.max_rows)
