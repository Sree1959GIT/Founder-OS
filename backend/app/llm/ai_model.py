"""The member's own AI model (M7a): a tested API key, encrypted at rest, per workspace, driving the deep-work agents.

- `SecretBox` encrypts keys with Fernet under `FOUNDEROS_SECRET_KEY` (in `.env`, written by `scripts/ensure_secret.py`).
- `AIModelStore` keeps one choice per workspace in `<data>/<ws>/ai_model.json`: the preset, model, base URL, the
  encrypted key and its last four characters. The key itself is never written in clear, logged or returned.
- `probe_key` sends one tiny request; `explain_failure` turns any failure into one plain-English line.
- `check_base_url` keeps a custom base URL on https and a public address, so a hosted server cannot be pointed at its
  own network.

A key is saved only after its test passed (see `app/api/ai_model.py`), so the model in use has always answered once.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, Message
from app.llm.cloud import AnthropicAPIProvider, GeminiProvider, OpenAICompatibleProvider
from app.llm.presets import LOCAL_PRESET, PRESETS, Preset

FILE_NAME = "ai_model.json"
TEST_PROMPT = "Reply with the single word OK."
# A model with no price in the table is counted at this (USD per million tokens, input and output), so the monthly cap
# still protects the member. Above every price in `costs.DEFAULT_PRICES`; set the real one in LLM_PRICES.
CONSERVATIVE_PRICE: tuple[float, float] = (15.0, 75.0)

Resolver = Callable[[str], Awaitable[list[str]]]


class SecretBox:
    """Fernet under the server secret. `problem` says, in plain words, why keys cannot be saved yet."""

    def __init__(self, secret: str | None) -> None:
        self._fernet: Fernet | None = None
        self.problem: str | None = None
        if not secret:
            self.problem = (
                "The server has no secret to encrypt keys with yet. Run setup.bat (or python scripts/ensure_secret.py) "
                "once, then restart FounderOS."
            )
            return
        try:
            self._fernet = Fernet(secret.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            self.problem = (
                "FOUNDEROS_SECRET_KEY in .env is not a valid key. Delete that line, run "
                "python scripts/ensure_secret.py, "
                "restart FounderOS and enter your API key again."
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> SecretBox:
        secret = settings.founderos_secret_key
        return cls(secret.get_secret_value() if secret is not None else None)

    @property
    def ready(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        if self._fernet is None:
            raise RuntimeError(self.problem or "no server secret")
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str | None:
        """None when it cannot be read (no secret, or the secret changed since the key was saved)."""
        if self._fernet is None or not token:
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError):
            return None


def mask(key: str) -> str:
    """Only the last four characters, and only when the key is long enough that they give nothing away."""
    key = key.strip()
    return f"••••{key[-4:]}" if len(key) >= 12 else "••••"


class AIModelChoice(BaseModel):
    """What `ai_model.json` holds. `active` false: Qwen is in use, and any saved key waits unused."""

    version: int = 1
    active: bool = False
    preset: str = LOCAL_PRESET
    model: str = ""
    base_url: str = ""
    key_token: str = ""  # Fernet token of the API key
    key_last4: str = ""  # the masked form, so the card can show it without decrypting
    verified_at: datetime | None = None
    saved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_key(self) -> bool:
        return bool(self.key_token)


class AIModelStore:
    """One workspace's choice. A damaged file reads as "nothing chosen" (the app starts on Qwen), never a crash."""

    def __init__(self, workspace_dir: Path) -> None:
        self.path = workspace_dir / FILE_NAME

    def load(self) -> AIModelChoice | None:
        if not self.path.is_file():
            return None
        try:
            return AIModelChoice.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring {}: {}", self.path.name, type(exc).__name__)
            return None

    def save(self, choice: AIModelChoice) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(choice.model_dump(mode="json"), indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def clear_key(self) -> AIModelChoice:
        """Remove key: the key, its mask and its verification go; Qwen is used from now on."""
        choice = AIModelChoice(active=False, preset=LOCAL_PRESET)
        self.save(choice)
        return choice


def preset_for(preset_id: str) -> Preset:
    preset = PRESETS.get(preset_id)
    if preset is None:
        raise ValueError(f"Unknown AI model choice {preset_id!r}.")
    return preset


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.to_thread(socket.getaddrinfo, host, 443, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


async def check_base_url(url: str, *, allow_private: bool = False, resolver: Resolver = _resolve) -> str:
    """A custom base URL, normalised, or ValueError with a plain-English reason.

    https and a public address only, unless `allow_private` (AI_MODEL_ALLOW_PRIVATE_URLS) says otherwise: a hosted
    server must not be made to call its own network or the cloud's metadata address with a member's request.
    """
    url = url.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("Enter the server's full address, starting with https://, e.g. https://api.example.com/v1.")
    if parts.username or parts.password:
        raise ValueError("Put the key in the key box, not in the address.")
    if parts.scheme != "https" and not allow_private:
        raise ValueError("The address must start with https:// so the key travels encrypted.")
    if allow_private:
        return url
    host = parts.hostname
    try:
        addresses = [host] if _is_ip(host) else await resolver(host)
    except OSError as exc:
        raise ValueError(f"Can't reach the server: no server called {host} was found.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise ValueError(f"{host} is a private or local address. Use the provider's public https address.")
    return url


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def build_provider(
    preset: Preset,
    model: str,
    key: str,
    *,
    base_url: str = "",
    timeout_s: float = 120.0,
    max_tokens: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LLMProvider:
    """The provider for a preset, on the existing provider layer (`app/llm/cloud.py`). Not for the local preset."""
    match preset.kind:
        case "anthropic":
            return AnthropicAPIProvider(
                key, model, timeout_s=timeout_s, max_tokens=max_tokens or 2048, transport=transport
            )
        case "gemini":
            return GeminiProvider(key, model, timeout_s=timeout_s, transport=transport)
        case "openai_compatible":
            provider = OpenAICompatibleProvider(
                key,
                model,
                name=preset.id,
                base_url=base_url or preset.base_url,
                timeout_s=timeout_s,
                json_mode=preset.json_mode,
                max_tokens=max_tokens,
                transport=transport,
            )
            return provider
        case _:
            raise ValueError("Qwen on our server needs no key.")


async def probe_key(provider: LLMProvider, timeout_s: float) -> None:
    """One tiny request. Raises `LLMError` (or `TimeoutError`) when it does not answer."""
    await asyncio.wait_for(provider.complete([Message.user(TEST_PROMPT)]), timeout=timeout_s)


CREDIT_WORDS = (
    "insufficient_quota",
    "credit balance",
    "credits",
    "no credit",
    "insufficient balance",
    "payment required",
)
KEY_WORDS = ("api key", "api_key", "apikey", "unauthorized", "authentication", "invalid key", "incorrect key")
MODEL_MISSING = (
    "not found",
    "does not exist",
    "not exist",
    "unknown model",
    "invalid model",
    "no such model",
    "unsupported model",
)


def explain_failure(exc: BaseException, label: str, model: str, timeout_s: float) -> tuple[str, str]:
    """(code, one plain-English line) for a failed key test. Never includes the provider's own text or the key."""
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return "unreachable", (
            f"Can't reach the server: {label} did not answer within {timeout_s:.0f} seconds. "
            "Check your internet connection (and the address, for Custom), then test again."
        )
    if not isinstance(exc, LLMError):
        return "other", f"The test could not run ({type(exc).__name__}). Try again in a minute."
    if exc.network:
        return "unreachable", (
            f"Can't reach the server: {label} could not be reached. "
            "Check your internet connection (and the address, for Custom), then test again."
        )
    status, detail = exc.status, exc.detail.lower()
    if status == 402 or (status != 429 and "billing" in detail) or any(word in detail for word in CREDIT_WORDS):
        return "no_credit", (
            f"No credit: {label} accepted the key, but the account has no credit or billing set up. "
            f"Add credit in your {label} account, then test again."
        )
    if status in (401, 403) or (status == 400 and any(word in detail for word in KEY_WORDS) and "model" not in detail):
        return "wrong_key", f"Wrong key: {label} did not accept it. Copy the whole key again from your {label} account."
    if status == 429:
        return "rate_limited", (
            f"Rate limited: {label} is getting too many requests on this key right now. Wait a minute, then test again."
        )
    if status in (400, 404, 422) and "model" in detail and any(word in detail for word in MODEL_MISSING):
        return "model_not_found", (
            f'Model not found: {label} has no model called "{model}" for this key. '
            f"Check the spelling against your {label} model list."
        )
    if status == 404:
        return "model_not_found", (
            f'Model not found: {label} answered "not found" for "{model}". Check the model name '
            "(and the address, for Custom)."
        )
    if status is not None and status >= 500:
        return (
            "unreachable",
            f"Can't reach the server: {label} had a problem of its own (HTTP {status}). Try again later.",
        )
    code = f" (HTTP {status})" if status else ""
    return "other", f"{label} refused the test{code}. Check the key and the model name, then test again."
