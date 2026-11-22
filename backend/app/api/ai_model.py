"""`/api/settings/ai-model`: the AI model card (M7a). A member's own key, tested before it is kept.

- `GET` the card: presets, what is in use, the saved key as `••••abcd` only.
- `POST /test` sends one tiny request (15 s). Passed: the key is stored encrypted for this workspace, cloud is turned on
  for the deep-work agents and the model is used from the next question. Failed: nothing is stored, and the answer is
  one plain-English line (wrong key, no credit, rate limited, can't reach the server, model not found).
- `POST /use-local` goes back to Qwen and keeps the saved key unused; `DELETE /key` removes the key.

A key never comes back in a response, never reaches a log, and a saved key is only ever sent to the preset (and base
URL) it was saved and tested with.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field, SecretStr

from app.api.settings import reapply, save_choices
from app.config import Settings
from app.llm.ai_model import (
    AIModelChoice,
    AIModelStore,
    SecretBox,
    build_provider,
    check_base_url,
    explain_failure,
    mask,
    preset_for,
    probe_key,
)
from app.llm.base import LLMError
from app.llm.presets import LOCAL_PRESET, PRESETS, default_model

router = APIRouter(prefix="/settings/ai-model", tags=["settings"])

TEST_MAX_TOKENS = 16


class KeyTestRequest(BaseModel):
    preset: str
    model: str = Field("", max_length=200)
    base_url: str = Field("", max_length=500)
    # Empty: test (again) with the key saved for this same preset and base URL.
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))


def _settings(request: Request) -> Settings:
    return request.app.state.base_settings  # type: ignore[no-any-return]


def _store(settings: Settings) -> AIModelStore:
    return AIModelStore(settings.workspace_data_dir())


def _view(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    effective: Settings = getattr(request.app.state, "effective_settings", settings)
    box = SecretBox.from_settings(settings)
    choice = _store(settings).load() or AIModelChoice()
    unreadable = choice.has_key and box.decrypt(choice.key_token) is None
    active = choice.active and choice.has_key and not unreadable
    preset = PRESETS.get(choice.preset, PRESETS[LOCAL_PRESET])
    saved = None
    if choice.has_key:
        saved = {
            "preset": preset.id,
            "label": preset.label,
            "model": choice.model,
            "base_url": choice.base_url,
            "key_masked": choice.key_last4,
            "verified_at": choice.verified_at.isoformat() if choice.verified_at else None,
            "unreadable": unreadable,
        }
    local = PRESETS[LOCAL_PRESET]
    return {
        "in_use": {
            "preset": preset.id if active else LOCAL_PRESET,
            "label": preset.label if active else local.label,
            "model": choice.model if active else settings.ollama_chat_model,
            "verified": active,
            "local": not active,
        },
        "saved": saved,
        "cloud_paused": active and not effective.cloud_allowed,
        "secret_ready": box.ready,
        "secret_problem": box.problem,
        "test_timeout_s": settings.ai_model_test_timeout_s,
        "presets": [
            {
                "id": p.id,
                "label": p.label,
                "title": p.title,
                "needs_key": p.needs_key,
                "custom_base_url": p.custom_base_url,
                "base_url": p.base_url,
                "default_model": default_model(p, settings),
                "key_hint": p.key_hint,
            }
            for p in PRESETS.values()
        ],
    }


@router.get("")
async def get_ai_model(request: Request) -> dict[str, Any]:
    return _view(request)


@router.post("/test")
async def test_ai_model(body: KeyTestRequest, request: Request) -> dict[str, Any]:
    settings = _settings(request)
    try:
        preset = preset_for(body.preset)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not preset.needs_key:
        raise HTTPException(422, 'Qwen on our server needs no key: use "Use Qwen".')
    box = SecretBox.from_settings(settings)
    if not box.ready:
        return {"ok": False, "code": "no_secret", "message": box.problem, "view": _view(request)}
    model = body.model.strip() or default_model(preset, settings)
    if not model:
        return {"ok": False, "code": "missing", "message": "Enter the model name.", "view": _view(request)}
    base_url = ""
    if preset.custom_base_url:
        try:
            base_url = await check_base_url(body.base_url, allow_private=settings.ai_model_allow_private_urls)
        except ValueError as exc:
            return {"ok": False, "code": "bad_url", "message": str(exc), "view": _view(request)}
    store = _store(settings)
    saved = store.load()
    key = body.api_key.get_secret_value().strip()
    if len(key) > 500 or any(ch.isspace() for ch in key):
        return {
            "ok": False,
            "code": "wrong_key",
            "message": "That does not look like an API key: copy it again.",
            "view": _view(request),
        }
    if not key:
        # A saved key goes only to the preset and address it was tested with, never to a new server.
        same_place = saved is not None and saved.preset == preset.id and saved.base_url == base_url
        key = (box.decrypt(saved.key_token) or "") if same_place and saved is not None else ""
        if not key:
            return {"ok": False, "code": "missing", "message": "Paste your API key first.", "view": _view(request)}
    timeout = settings.ai_model_test_timeout_s
    # Anthropic needs a token limit; OpenAI-style servers get none (newer OpenAI models refuse `max_tokens`).
    limit = TEST_MAX_TOKENS if preset.kind == "anthropic" else None
    provider = build_provider(preset, model, key, base_url=base_url, timeout_s=timeout, max_tokens=limit)
    try:
        await probe_key(provider, timeout)
    except (LLMError, TimeoutError) as exc:
        code, message = explain_failure(exc, preset.label, model, timeout)
        # The reason only, never the key or the provider's text (it can echo what was sent).
        logger.info("AI model test failed: {} {} ({})", preset.label, code, getattr(exc, "status", None))
        return {"ok": False, "code": code, "message": message, "view": _view(request)}
    now = datetime.now(UTC)
    store.save(
        AIModelChoice(
            active=True,
            preset=preset.id,
            model=model,
            base_url=base_url,
            key_token=box.encrypt(key),
            key_last4=mask(key),
            verified_at=now,
            saved_at=now,
        )
    )
    save_choices(request.app, {"cloud_allowed": True})  # verifying a key is the member's choice to use it
    logger.info("AI model set for the deep-work agents: {} {}", preset.label, model)
    return {"ok": True, "code": "ok", "message": f"{preset.label} · {model} · key verified", "view": _view(request)}


@router.post("/use-local")
async def use_local(request: Request) -> dict[str, Any]:
    store = _store(_settings(request))
    choice = store.load() or AIModelChoice()
    store.save(choice.model_copy(update={"active": False, "saved_at": datetime.now(UTC)}))
    reapply(request.app)
    return _view(request)


@router.delete("/key")
async def remove_key(request: Request) -> dict[str, Any]:
    _store(_settings(request)).clear_key()
    reapply(request.app)
    logger.info("AI model key removed; the deep-work agents use Qwen")
    return _view(request)
