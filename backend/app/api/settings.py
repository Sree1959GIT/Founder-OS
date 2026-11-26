"""`/api/settings`: what the Settings panel can change while the app runs. Never a key: those stay in `.env`.

Choices are saved to `<data>/<workspace>/ui_settings.json` and win over `.env` until they are changed again. Keys, and
which providers have one, are only ever read: this API reports `configured: true/false` and nothing else about a key.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from app.agents.registry import REGISTRY
from app.agents.setup import build_decisions
from app.config import DeepProvider, Settings
from app.llm.ai_model import CONSERVATIVE_PRICE, AIModelStore, SecretBox, build_provider, preset_for
from app.llm.base import LLMProvider
from app.llm.router import build_cloud_provider, build_routes

router = APIRouter(tags=["settings"])

FILE_NAME = "ui_settings.json"
PRIVACY_NOTE = (
    "Local by default: your numbers, notes and customers stay on this PC. A cloud agent runs only when cloud is on, "
    "its provider has a key and the monthly cap allows it, and every cloud payload goes through the privacy filter: "
    "no raw financial rows, and customer and person names replaced by stand-ins. Agents marked local never use the "
    "cloud. Keys are kept encrypted or in .env and are never shown here."
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
    # Founder F12: the member's currency for costs and the cap (the cap is still stored in USD).
    member_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")


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
    chosen, member_model = ai_model_provider(effective)
    if chosen:  # the AI model card decides the deep-work model; per-agent routes below still apply
        llm.cloud = member_model
    llm.routes = build_routes(effective)
    if llm.ledger is not None:
        llm.ledger.monthly_cap_usd = effective.cloud_monthly_cap_usd
        if member_model is not None and member_model.model not in llm.ledger.prices:
            llm.ledger.prices[member_model.model] = CONSERVATIVE_PRICE  # the cap still counts it (PRD §12, M7a)
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


def ai_model_provider(settings: Settings) -> tuple[bool, LLMProvider | None]:
    """(chosen, provider) from the workspace's AI model card. Not chosen: `.env` decides, as before M7a.

    Chosen with Qwen, or a saved key that can no longer be read (the server secret changed): (True, None), so the
    deep-work agents use Qwen rather than an `.env` provider the member did not pick.
    """
    choice = AIModelStore(settings.workspace_data_dir()).load()
    if choice is None:
        return False, None
    if not choice.active or not choice.has_key:
        return True, None
    key = SecretBox.from_settings(settings).decrypt(choice.key_token)
    if key is None:
        logger.warning("The saved AI model key cannot be read (the server secret changed?); using Qwen")
        return True, None
    try:
        preset = preset_for(choice.preset)
        return True, build_provider(
            preset, choice.model, key, base_url=choice.base_url, timeout_s=settings.llm_timeout_s
        )
    except ValueError as exc:
        logger.warning("Ignoring the saved AI model: {}", exc)
        return True, None


def ai_model_in_use(settings: Settings) -> dict[str, Any] | None:
    """Founder F6: the verified AI model card choice in use for the deep-work agents, or None (Qwen / `.env`).

    The top bar, the Cloud section and "Default" in Provider per agent show this, e.g. "Gemini · gemini-3.8-flash
    (from AI model)", instead of the `.env` providers' "no key"."""
    choice = AIModelStore(settings.workspace_data_dir()).load()
    if choice is None or not choice.active or not choice.has_key or choice.verified_at is None:
        return None
    if SecretBox.from_settings(settings).decrypt(choice.key_token) is None:
        return None
    try:
        preset = preset_for(choice.preset)
    except ValueError:
        return None
    return {
        "preset": preset.id,
        "label": preset.label,
        "model": choice.model,
        "text": f"{preset.label} · {choice.model} (from AI model)",
    }


def cloud_usable(settings: Settings) -> bool:
    """A key that can be used: a verified AI model card key, or a `.env` provider key while the card was never used.

    Founder F4b: once the card has a choice (Qwen, or a removed key) the router no longer uses `.env` keys, so they
    cannot make cloud work either."""
    if ai_model_in_use(settings) is not None:
        return True
    if AIModelStore(settings.workspace_data_dir()).load() is not None:
        return False
    return any(settings.provider_configured(p) for p in DeepProvider if p is not DeepProvider.OLLAMA)


def save_choices(app: Any, update: dict[str, Any]) -> Settings:
    """Merge `update` into `ui_settings.json`, write it atomically and apply it to the running app."""
    base: Settings = app.state.base_settings
    choices = {**_load(base), **update}
    effective = _apply(app, base, choices)
    path = _file(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(choices, indent=2), encoding="utf-8")
    temporary.replace(path)
    return effective


def reapply(app: Any) -> Settings:
    """Apply the saved choices again (after the AI model card changed what the deep-work agents use)."""
    base: Settings = app.state.base_settings
    return _apply(app, base, _load(base))


def _current(request: Request) -> Settings:
    return getattr(request.app.state, "effective_settings", request.app.state.base_settings)


def _usd_info(asked: str) -> dict[str, Any]:
    return {"asked": asked or "USD", "currency": "USD", "symbol": "$", "rate": 1.0, "as_of": None, "source": ""}


def _view(request: Request) -> dict[str, Any]:
    settings = _current(request)
    fx = getattr(request.app.state, "fx", None)
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
        "ai_model": ai_model_in_use(settings),
        "cloud_usable": cloud_usable(settings),
        "member_currency": settings.member_currency,
        # Founder F12: the member's currency and today's rate (US dollars when there is none). The cap stays in USD.
        "fx": fx.info(settings.member_currency) if fx is not None else _usd_info(settings.member_currency),
        "privacy_note": PRIVACY_NOTE,
    }


@router.get("/settings")
async def get_settings_view(request: Request) -> dict[str, Any]:
    return _view(request)


@router.put("/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
    # Founder F4: only a passing, saved key may turn cloud on. With none, nothing could leave this PC anyway.
    if body.cloud_allowed and not _current(request).cloud_allowed and not cloud_usable(_current(request)):
        raise HTTPException(
            422, "Test and save a key in the AI model card first: only a key that passed its test can turn cloud on."
        )
    save_choices(request.app, body.model_dump(mode="json", exclude_none=True))
    return _view(request)
