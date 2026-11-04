"""FastAPI application factory.

Run from `backend/` with `uvicorn --factory app.main:create_app --port 8000`. There is deliberately no module-level
app, so importing this module never reads `.env` or the environment.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app import __version__
from app.agents.setup import build_orchestrator
from app.api import chat, data, health, metrics, scenario, vault
from app.config import Settings, get_settings
from app.deps import FinanceServices
from app.engine.calibration import CalibrationError
from app.engine.duckdb_engine import NoDataError
from app.engine.ingest import IngestError, ingest_directory
from app.engine.metrics import MetricError
from app.engine.sql_guard import SqlGuardError
from app.llm.base import LLMError
from app.llm.ollama import OllamaProvider
from app.logging_setup import configure_logging
from app.vault.manager import NoteExistsError, NoteNotFoundError, VaultError, VaultPathError
from app.vault.service import VaultService


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


async def warm_up_chat_model(provider: OllamaProvider) -> None:
    """Background task: load the chat model so the first question does not wait minutes. Never raises (PRD R3)."""
    logger.info("Loading {} into Ollama in the background (first load can take minutes)", provider.model)
    try:
        seconds = await provider.warm_up()
        logger.info("Ollama model {} is loaded ({} s)", provider.model, seconds)
    except LLMError as exc:
        logger.warning("Could not preload {}: {} (agents use rules until Ollama answers)", provider.model, exc)


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
        app.state.vaults = {}
        vault_service = app.state.vaults.setdefault(str(settings.workspace_vault_dir()), VaultService(settings))
        # Index in a worker thread so startup never waits for parsing or embeddings (PRD R3).
        indexing = asyncio.get_running_loop().run_in_executor(None, vault_service.ensure_started)
        if settings.vault_watch:
            await vault_service.start_watcher()
        orchestrator = build_orchestrator(settings, services, vault_service)
        app.state.event_bus = orchestrator.bus
        app.state.orchestrator = orchestrator
        logger.info(
            "Agents ready: local LLM {}:{} (thinking {}), deep provider {}, team approval {}",
            orchestrator.router.local.name,
            orchestrator.router.local.model,
            "on" if settings.ollama_think else "off",
            orchestrator.router.cloud.name if orchestrator.router.cloud else "none (local only)",
            settings.team_approval,
        )
        warmup = (
            asyncio.create_task(warm_up_chat_model(orchestrator.router.local))
            if settings.ollama_warmup and isinstance(orchestrator.router.local, OllamaProvider)
            else None
        )
        logger.info(
            "FounderOS backend {} started (workspace={}, data={})",
            __version__,
            settings.workspace_id,
            settings.workspace_data_dir(),
        )
        try:
            yield
        finally:
            if warmup is not None:
                warmup.cancel()
            await vault_service.stop_watcher()
            if not indexing.done():
                logger.info("Shutting down while the vault is still indexing")
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
    app.include_router(vault.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
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
    app.add_exception_handler(VaultPathError, handler(400))
    app.add_exception_handler(NoteNotFoundError, handler(404))
    app.add_exception_handler(NoteExistsError, handler(409))
    app.add_exception_handler(VaultError, handler(422))
