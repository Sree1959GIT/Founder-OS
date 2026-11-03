"""FastAPI application factory.

Run from `backend/` with `uvicorn --factory app.main:create_app --port 8000`. There is deliberately no module-level
app, so importing this module never reads `.env` or the environment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app import __version__
from app.api import data, health, metrics, scenario
from app.config import Settings, get_settings
from app.deps import FinanceServices
from app.engine.calibration import CalibrationError
from app.engine.duckdb_engine import NoDataError
from app.engine.ingest import IngestError, ingest_directory
from app.engine.metrics import MetricError
from app.engine.sql_guard import SqlGuardError
from app.logging_setup import configure_logging


def load_sample_data_if_empty(settings: Settings, services: FinanceServices) -> None:
    """Startup convenience for the demo: an empty workspace gets the Northwind data. Never raises (PRD R3)."""
    if not settings.auto_load_sample_data:
        return
    try:
        if services.db.tables():
            return
        source = settings.sample_data_path()
        reports = ingest_directory(services.db, source)
        logger.info("Loaded sample data from {} ({} tables)", source, len(reports))
    except Exception as exc:  # a broken sample folder must not stop the backend
        logger.error("Could not load sample data: {}", exc)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Passing `settings` pins them for every request (used by tests)."""
    pinned = settings is not None
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        for directory in (settings.workspace_data_dir(), settings.workspace_vault_dir()):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # PRD R3: keep serving; /api/health reports the storage problem.
                logger.error("Cannot create {}: {}", directory, exc)
        app.state.http_client = httpx.AsyncClient()
        app.state.finance = {}
        services = app.state.finance.setdefault(str(settings.workspace_data_dir()), FinanceServices(settings))
        load_sample_data_if_empty(settings, services)
        logger.info(
            "FounderOS backend {} started (workspace={}, data={})",
            __version__,
            settings.workspace_id,
            settings.workspace_data_dir(),
        )
        try:
            yield
        finally:
            await app.state.http_client.aclose()

    app = FastAPI(title="FounderOS", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    if pinned:
        app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(health.router, prefix="/api")
    app.include_router(data.router, prefix="/api")
    app.include_router(metrics.router, prefix="/api")
    app.include_router(scenario.router, prefix="/api")
    _add_error_handlers(app)
    return app


def _add_error_handlers(app: FastAPI) -> None:
    """Engine errors become clear JSON errors instead of 500s."""

    def handler(status: int):  # type: ignore[no-untyped-def]
        async def handle(_: Request, exc: Exception) -> JSONResponse:
            body: dict[str, object] = {"detail": str(exc)}
            if isinstance(exc, IngestError) and exc.errors:
                body["errors"] = exc.errors
            return JSONResponse(status_code=status, content=body)

        return handle

    app.add_exception_handler(NoDataError, handler(409))
    app.add_exception_handler(IngestError, handler(422))
    app.add_exception_handler(MetricError, handler(422))
    app.add_exception_handler(SqlGuardError, handler(400))
    app.add_exception_handler(CalibrationError, handler(422))
