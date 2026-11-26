"""`/api/settings/ai-model`: the AI model card (M7a). A member's own key, tested before it is kept.

- `GET` the card: presets, what is in use, the saved key as `••••abcd` only.
- `POST /test` (founder F3: the key is enough) finds the provider from the key's shape, asks it which models the key can
  use, picks the best one (`pick_models`) and sends one tiny request, all within 15 s. Passed: the key is stored
  encrypted for this workspace, cloud is turned on for the deep-work agents and the model is used from the next
  question. Failed: nothing is stored, and the answer is
  one plain-English line (wrong key, no credit, rate limited, can't reach the server, model not found).
- `POST /use-local` goes back to Qwen and keeps the saved key unused; `DELETE /key` removes the key.

A key never comes back in a response, never reaches a log, and a saved key is only ever sent to the preset (and base
URL) it was saved and tested with.
"""

from __future__ import annotations

import asyncio
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
    ModelInfo,
    SecretBox,
    build_provider,
    check_base_url,
    explain_failure,
    internet_works,
    is_timeout,
    list_models,
    mask,
    pick_models,
    preset_for,
    probe_key,
    retry_when_busy,
)
from app.llm.base import LLMError, LLMProvider
from app.llm.presets import LOCAL_PRESET, PRESETS, Preset, default_model, detect_preset, load_key_shapes

router = APIRouter(prefix="/settings/ai-model", tags=["settings"])

TEST_MAX_TOKENS = 16
MAX_TRIES = 3  # a listed model can still refuse the key (e.g. closed to new users): the next best is tried


class KeyTestRequest(BaseModel):
    preset: str = Field("", max_length=50)  # empty: found from the key's shape (founder F3)
    model: str = Field("", max_length=200)  # empty: the best model the key can use
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
            "models": [m.model_dump() for m in choice.models],
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
        "key_shapes": [{"prefix": s.prefix, "preset": s.preset} for s in load_key_shapes(settings)],
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


def _fail(request: Request, code: str, message: str | None, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "code": code, "message": message, "view": _view(request), **extra}


@router.post("/test")
async def test_ai_model(body: KeyTestRequest, request: Request) -> dict[str, Any]:
    settings = _settings(request)
    key = body.api_key.get_secret_value().strip()
    if len(key) > 500 or any(ch.isspace() for ch in key):
        return _fail(request, "wrong_key", "That does not look like an API key: copy it again.")
    preset_id = body.preset.strip() or (detect_preset(key, load_key_shapes(settings)) if key else "")
    if not preset_id:
        return _fail(
            request,
            "unknown_provider" if key else "missing",
            UNKNOWN_KEY if key else "Paste your API key first.",
        )
    try:
        preset = preset_for(preset_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not preset.needs_key:
        raise HTTPException(422, 'Qwen on our server needs no key: use "Use Qwen".')
    box = SecretBox.from_settings(settings)
    if not box.ready:
        return _fail(request, "no_secret", box.problem)
    base_url = ""
    if preset.custom_base_url:
        try:
            base_url = await check_base_url(body.base_url, allow_private=settings.ai_model_allow_private_urls)
        except ValueError as exc:
            return _fail(request, "bad_url", str(exc))
    saved = _store(settings).load()
    if not key:
        # A saved key goes only to the preset and address it was tested with, never to a new server.
        same_place = saved is not None and saved.preset == preset.id and saved.base_url == base_url
        key = (box.decrypt(saved.key_token) or "") if same_place and saved is not None else ""
        if not key:
            return _fail(request, "missing", "Paste your API key first.")
    timeout = settings.ai_model_test_timeout_s
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout  # the whole test (list + try) stays within the card's 15 s

    # 1. Which models can this key use? A wrong key, no credit or a rate limit already shows here.
    retries = settings.ai_model_busy_retries
    typed = bool(body.api_key.get_secret_value().strip())
    key_ok = saved is not None and saved.verified_at is not None and saved.preset == preset.id and not typed
    try:

        async def listing(left: float) -> tuple[list[ModelInfo], dict[str, float]]:
            return await asyncio.wait_for(list_models(preset, key, base_url=base_url, timeout_s=left), timeout=left)

        listed, created = await retry_when_busy(listing, deadline, retries)
        key_ok = True  # the provider answered with this key's model list: the key is accepted
    except (LLMError, TimeoutError) as exc:
        internet_ok = await _internet_ok(exc, preset)
        code, message = explain_failure(
            exc, preset.label, body.model.strip(), timeout, key_ok=key_ok, internet_ok=internet_ok
        )
        if isinstance(exc, TimeoutError) or getattr(exc, "network", False) or code in _KEY_PROBLEMS:
            logger.info("AI model test failed: {} {} (list, {})", preset.label, code, getattr(exc, "status", None))
            return _fail(request, code, message, preset=preset.id)
        listed, created = [], {}  # no model list here (some servers have none): fall back to the configured model
    ranked = pick_models(listed, settings.ai_model_preferences.get(preset.id, []), created)
    explicit = body.model.strip()
    if explicit:
        candidates = [explicit]
    elif ranked:
        candidates = [m.id for m in ranked[:MAX_TRIES]]
    else:
        fallback = default_model(preset, settings)
        candidates = [fallback] if fallback else []
    if not candidates:
        return _fail(
            request,
            "missing",
            "This server did not list its models: enter the model name under Advanced, then test again.",
            preset=preset.id,
        )

    # 2. One tiny request to the chosen model; a listed model that refuses is skipped for the next best one.
    model, failure = await _try_models(preset, key, base_url, candidates, deadline, timeout, retries, key_ok=key_ok)
    if failure is not None:
        code, message, status = failure
        logger.info("AI model test failed: {} {} ({})", preset.label, code, status)  # the reason only, never the key
        return _fail(request, code, message, preset=preset.id)
    models = ranked if any(m.id == model for m in ranked) else [ModelInfo(id=model), *ranked]
    now = datetime.now(UTC)
    _store(settings).save(
        AIModelChoice(
            active=True,
            preset=preset.id,
            model=model,
            base_url=base_url,
            key_token=box.encrypt(key),
            key_last4=mask(key),
            models=models,
            verified_at=now,
            saved_at=now,
        )
    )
    save_choices(request.app, {"cloud_allowed": True})  # verifying a key is the member's choice to use it
    logger.info("AI model set for the deep-work agents: {} {}", preset.label, model)
    # Founder F5: only the first 3 characters and the provider, to grow the key-shape list. Never more of the key.
    logger.info("AI model key shape: starts {!r} -> {}", key[:3], preset.id)
    return {
        "ok": True,
        "code": "ok",
        "message": f"{preset.label} · {model} · key verified",
        "preset": preset.id,
        "view": _view(request),
    }


async def _internet_ok(exc: BaseException, preset: Preset) -> bool:
    """Founder F7c: only for a connection error (not a timeout): does another AI provider answer from here?"""
    if not isinstance(exc, LLMError) or not exc.network or is_timeout(exc):
        return False
    return await internet_works(preset.id)


_KEY_PROBLEMS = ("wrong_key", "no_credit", "busy", "free_limit", "server_error", "slow")
UNKNOWN_KEY = "We couldn't recognise this key. Please check it, or pick the provider that issued it."


async def _try_models(
    preset: Preset,
    key: str,
    base_url: str,
    candidates: list[str],
    deadline: float,
    timeout: float,
    retries: int = 0,
    *,
    key_ok: bool = False,
) -> tuple[str, tuple[str, str, int | None] | None]:
    """(the model that answered, None) or (the last model tried, (code, message, HTTP status))."""
    loop = asyncio.get_running_loop()
    # Anthropic needs a token limit; OpenAI-style servers get none (newer OpenAI models refuse `max_tokens`).
    limit = TEST_MAX_TOKENS if preset.kind == "anthropic" else None
    failure: tuple[str, str, int | None] | None = None
    model = candidates[0]
    for index, model in enumerate(candidates):
        left = deadline - loop.time()
        if index and left < 1:
            break
        provider = build_provider(preset, model, key, base_url=base_url, timeout_s=timeout, max_tokens=limit)
        try:

            async def probe(seconds: float, provider: LLMProvider = provider) -> None:
                await probe_key(provider, seconds)  # the list and every try share the 15 s

            await retry_when_busy(probe, deadline, retries)
            return model, None
        except (LLMError, TimeoutError) as exc:
            internet_ok = await _internet_ok(exc, preset)
            code, message = explain_failure(exc, preset.label, model, timeout, key_ok=key_ok, internet_ok=internet_ok)
            failure = (code, message, getattr(exc, "status", None))
            if code != "model_not_found":
                break
    return model, failure


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
    # Founder F4b: removing the key turns cloud off (saved), so "Allow cloud agents" greys out again. The router
    # already ignores `.env` keys once the card was used, so no key is left that could make cloud work.
    save_choices(request.app, {"cloud_allowed": False})
    logger.info("AI model key removed; the deep-work agents use Qwen and cloud is off")
    return _view(request)
