"""`/api/settings`: what the Settings panel can change while the app runs. Never a key: those stay in `.env`.

Choices are saved to `<data>/<workspace>/ui_settings.json` and win over `.env` until they are changed again. Keys, and
which providers have one, are only ever read: this API reports `configured: true/false` and nothing else about a key.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel, Field

from app.agents.registry import REGISTRY
from app.agents.setup import build_decisions
from app.config import DeepProvider, Settings
from app.llm.router import build_cloud_provider, build_routes

router = APIRouter(tags=["settings"])

FILE_NAME = "ui_settings.json"
PRIVACY_NOTE = (
    "Local by default: your numbers, notes and customers stay on this PC. A cloud agent runs only when cloud is on, "
    "its provider has a key and the monthly cap allows it, and every cloud payload goes through the privacy filter: "
    "no raw financial rows, and customer and person names replaced by stand-ins. Agents marked local never use the "
    "cloud. Keys are kept in .env and are never shown here."
)


class SettingsUpdate(BaseModel):
    """Only what is sent changes."""

    cloud_allowed: bool | None = None
    deep_provider: DeepProvider | None = None
    agent_models: dict[str, str] | None = Field(None, description='Agent type -> "provider" or "provider:model"')
    cloud_monthly_cap_usd: float | None = Field(None, ge=0, le=100_000)
    team_approval: Literal["always", "cloud_only", "never"] | None = None
    max_local_agents: int | None = Field(None, ge=1, le=16)
    max_cloud_agents: int | None = Field(None, ge=1, le=32)


def _file(settings: Settings) -> Path:
    return settings.workspace_data_dir() / FILE_NAME


def _load(settings: Settings) -> dict[str, Any]:
    path = _file(settings)
    if not path.exists():
        return {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return SettingsUpdate(**saved).model_dump(mode="json", exclude_none=True)
    except (OSError, ValueError) as exc:  # a damaged file must not stop the app: the safe `.env` values stand
        logger.warning("Ignoring {}: {}", path, exc)
        return {}


def apply_saved(app: Any, settings: Settings) -> None:
    """At startup, after the agent stack is built."""
    _apply(app, settings, _load(settings))


def _apply(app: Any, settings: Settings, choices: dict[str, Any]) -> Settings:
    update = {**choices}
    if "deep_provider" in update:
        update["deep_provider"] = DeepProvider(update["deep_provider"])
    effective = settings.model_copy(update=update)
    orchestrator = app.state.orchestrator
    llm = orchestrator.router
    llm.cloud_allowed = effective.cloud_allowed
    llm.cloud = build_cloud_provider(effective)
    llm.routes = build_routes(effective)
    if llm.ledger is not None:
        llm.ledger.monthly_cap_usd = effective.cloud_monthly_cap_usd
    orchestrator.approval_policy = effective.team_approval
    if effective.decision_provider == "jev":  # a cloud service: "cloud off" must mean nothing leaves the PC
        orchestrator.decisions = build_decisions(effective, llm)
    if orchestrator.max_local != effective.max_local_agents:
        orchestrator.max_local, orchestrator.local_slots = (
            effective.max_local_agents,
            asyncio.Semaphore(effective.max_local_agents),
        )
    if orchestrator.max_cloud != effective.max_cloud_agents:
        orchestrator.max_cloud, orchestrator.cloud_slots = (
            effective.max_cloud_agents,
            asyncio.Semaphore(effective.max_cloud_agents),
        )
    app.state.effective_settings = effective
    return effective


def _current(request: Request) -> Settings:
    return getattr(request.app.state, "effective_settings", request.app.state.base_settings)


def _view(request: Request) -> dict[str, Any]:
    settings = _current(request)
    llm = request.app.state.orchestrator.router
    ledger = llm.ledger.summary() if llm.ledger is not None else {}
    return {
        "cloud_allowed": settings.cloud_allowed,
        "deep_provider": settings.deep_provider.value,
        "agent_models": settings.agent_models,
        "cloud_monthly_cap_usd": settings.cloud_monthly_cap_usd,
        "team_approval": settings.team_approval,
        "max_local_agents": settings.max_local_agents,
        "max_cloud_agents": settings.max_cloud_agents,
        "providers": [
            {"name": provider.value, "configured": settings.provider_configured(provider)} for provider in DeepProvider
        ],
        "agents": [
            {"type": spec.name, "title": spec.title, "privacy": spec.privacy, "job": spec.job}
            for spec in REGISTRY.values()
        ],
        "spend": ledger,
        "privacy_note": PRIVACY_NOTE,
    }


@router.get("/settings")
async def get_settings_view(request: Request) -> dict[str, Any]:
    return _view(request)


@router.put("/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
    base: Settings = request.app.state.base_settings
    choices = {**_load(base), **body.model_dump(mode="json", exclude_none=True)}
    _apply(request.app, base, choices)
    path = _file(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(choices, indent=2), encoding="utf-8")
    temporary.replace(path)
    return _view(request)
