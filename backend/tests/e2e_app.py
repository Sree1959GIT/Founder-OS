"""The app for the Playwright smoke test: the real backend and sample data, with a scripted model and no Ollama.

The model invents a market figure and a citation on purpose: the smoke test asserts that neither reaches the screen.
Start it with `uvicorn tests.e2e_app:create_e2e_app --factory` from `backend/`.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.config import Settings
from app.llm.fake import FakeProvider, schema_example
from app.main import create_app

INVENTED = "The Gulf market is worth $150 billion [notes/economic-overview.md]."


def _reply(_messages: list[Any], _tools: list[Any] | None, schema: dict[str, Any] | None) -> str:
    if schema is not None:
        return json.dumps(schema_example(schema))
    return f"{INVENTED} Confirm the budget before you commit."


def create_e2e_app() -> FastAPI:
    root = Path(tempfile.mkdtemp(prefix="founderos-e2e-"))
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_provider="fake",
        data_dir=root / "data",
        vault_path=root / "vault",
        auto_load_sample_data=True,
        embed_provider="fake",
        vector_store="memory",
        tokenizer="approx",
        vault_watch=False,
        ollama_warmup=False,
        team_approval="always",
    )
    app = create_app(settings)
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(running: FastAPI) -> AsyncIterator[None]:
        async with inner(running):
            running.state.orchestrator.router.local = FakeProvider(default=_reply)
            yield

    app.router.lifespan_context = lifespan
    return app
