"""FastAPI application factory. Run with `uvicorn app.main:app --port 8000` from `backend/`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import __version__
from app.api import health
from app.config import Settings, get_settings
from app.logging_setup import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Passing `settings` pins them for every request (used by tests)."""
    pinned = settings is not None
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        for directory in (settings.workspace_data_dir(), settings.workspace_vault_dir()):
            directory.mkdir(parents=True, exist_ok=True)
        app.state.http_client = httpx.AsyncClient()
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
    return app


app = create_app()
