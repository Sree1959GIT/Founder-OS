"""The member's own AI model (M7a): a tested API key, encrypted at rest, per workspace, driving the deep-work agents.

- `SecretBox` encrypts keys with Fernet under `FOUNDEROS_SECRET_KEY` (in `.env`, written by `scripts/ensure_secret.py`).
- `AIModelStore` keeps one choice per workspace in `<data>/<ws>/ai_model.json`: the preset, model, base URL, the
  encrypted key and its last four characters. The key itself is never written in clear, logged or returned.
- `list_models` asks the provider which models the key can use (founder F3), keeps the text/chat ones and `pick_models`
  ranks them by the preference families in config, so the member never types a model name.
- `probe_key` sends one tiny request; `explain_failure` turns any failure into one plain-English line.
- `check_base_url` keeps a custom base URL on https and a public address, so a hosted server cannot be pointed at its
  own network.

A key is saved only after its test passed (see `app/api/ai_model.py`), so the model in use has always answered once.
"""

from __future__ import annotations

import asyncio
import fnmatch
import ipaddress
import json
import re
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, Message
from app.llm.cloud import AnthropicAPIProvider, GeminiProvider, OpenAICompatibleProvider, _http_error
from app.llm.presets import LOCAL_PRESET, PRESETS, Preset

FILE_NAME = "ai_model.json"
TEST_PROMPT = "Reply with the single word OK."
# A model with no price in the table is counted at this (USD per million tokens, input and output), so the monthly cap
# still protects the member. Above every price in `costs.DEFAULT_PRICES`; set the real one in LLM_PRICES.
CONSERVATIVE_PRICE: tuple[float, float] = (15.0, 75.0)

Resolver = Callable[[str], Awaitable[list[str]]]
_sleep = asyncio.sleep  # the back-off between busy retries (tests make it instant)


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


class ModelInfo(BaseModel):
    id: str
    label: str = ""  # the provider's display name, when it gives one


class AIModelChoice(BaseModel):
    """What `ai_model.json` holds. `active` false: Qwen is in use, and any saved key waits unused."""

    version: int = 1
    active: bool = False
    preset: str = LOCAL_PRESET
    model: str = ""
    base_url: str = ""
    key_token: str = ""  # Fernet token of the API key
    key_last4: str = ""  # the masked form, so the card can show it without decrypting
    models: list[ModelInfo] = Field(default_factory=list)  # what the key could use at its test, best first (F3)
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


async def retry_when_busy(
    attempt: Callable[[float], Awaitable[Any]], deadline: float, retries: int, *, backoff_s: float = 0.6
) -> Any:
    """Founder F7: `attempt(seconds_left)` again when the provider is busy (503) or rate limited (429), after a short
    back-off (0.6 s, then 1.8 s, ...), never past `deadline` (the test's 15 s). The last failure is raised."""
    loop = asyncio.get_running_loop()
    busy: LLMError | None = None
    for tries in range(retries + 1):
        left = deadline - loop.time()
        try:
            return await attempt(max(left, 1.0))
        except TimeoutError as exc:
            # Founder F7b: the time ran out on a retry after a 429/503. That is still "busy", never "check your
            # internet": the provider did answer, it was just busy.
            if busy is not None:
                raise busy from exc
            raise
        except LLMError as exc:
            if exc.network and busy is not None:
                raise busy from exc
            wait = round(backoff_s * (3**tries), 2)
            if not is_busy(exc) or is_free_limit(exc) or tries == retries or deadline - loop.time() < wait + 1.0:
                raise
            busy = exc
            logger.info("AI model test: provider busy (HTTP {}), asking again in {:.1f} s", exc.status, wait)
            await _sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


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


# Founder F7: who runs each provider's servers, for "Gemini is busy right now (Google error 503)".
VENDORS = {"Gemini": "Google", "Claude": "Anthropic", "OpenAI": "OpenAI"}
BUSY_STATUSES = (429, 502, 503, 504)


def is_busy(exc: BaseException) -> bool:
    """Overloaded (503, 502, 504) or rate limited (429): worth asking again in a moment. Not a quota with no credit."""
    if not isinstance(exc, LLMError) or exc.status not in BUSY_STATUSES:
        return False
    return not any(word in exc.detail.lower() for word in CREDIT_WORDS)


# Founder F7b: Google's 429 for a used-up quota (the free tier): asking again in a second does not help.
# Google's body: {"error": {"code": 429, "message": "You exceeded your current quota ... free_tier ...", "status":
# "RESOURCE_EXHAUSTED"}}. A plain "Resource has been exhausted (e.g. check quota)" is a busy minute: asked again.
FREE_LIMIT_WORDS = ("resource_exhausted", "free_tier", "free tier", "exceeded your current quota", "quota exceeded")


def is_free_limit(exc: BaseException) -> bool:
    """A rate limit that is a used-up quota (Gemini's RESOURCE_EXHAUSTED / free tier), not a busy moment."""
    return (
        isinstance(exc, LLMError) and exc.status == 429 and any(word in exc.detail.lower() for word in FREE_LIMIT_WORDS)
    )


FREE_LIMIT_LINES = {
    "Gemini": (
        "Your Gemini key has reached its free limit for now. Try again later, or add billing in Google AI Studio."
    ),
}


def is_timeout(exc: BaseException) -> bool:
    """Founder F7c: the provider did not answer in time (our 15 s, or the HTTP client's own read/connect timeout)."""
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return True
    return isinstance(exc, LLMError) and exc.network and "timeout" in str(exc).lower()


INTERNET_CHECK_S = 3.0


async def internet_works(
    skip_preset: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout_s: float = INTERNET_CHECK_S
) -> bool:
    """Founder F7c: does any other AI provider answer from here? Any HTTP reply counts (even 401/404): the
    connection works. Only when none answers is the member's internet the likely cause."""
    hosts = [p.base_url for p in PRESETS.values() if p.base_url and p.id != skip_preset and not p.custom_base_url]

    async def one(client: httpx.AsyncClient, url: str) -> bool:
        try:
            await client.head(url)
            return True
        except httpx.HTTPError:
            return False

    try:
        async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as client:
            return any(await asyncio.gather(*(one(client, url) for url in hosts)))
    except Exception as exc:
        logger.info("Internet check could not run: {}", type(exc).__name__)
    return False


def busy_line(label: str, status: int | None, *, key_ok: bool) -> str:
    vendor = VENDORS.get(label, label)
    fine = " Your key is fine." if key_ok else ""
    return f"{label} is busy right now ({vendor} error {status}).{fine} Try again in a minute."


def explain_failure(
    exc: BaseException,
    label: str,
    model: str,
    timeout_s: float,
    *,
    key_ok: bool = False,
    internet_ok: bool = False,
) -> tuple[str, str]:
    """(code, one plain-English line) for a failed key test. Never includes the provider's own text or the key.

    `key_ok`: the provider already accepted the key (its model list answered), so a busy server can say so (F7).
    `internet_ok`: another AI service answered just now, so a connection error is not the member's internet (F7c)."""
    if is_timeout(exc):
        # Founder F7c: a provider that simply does not answer in time is slow or limiting the key. The member's
        # internet is not the cause when another provider answers on the same connection (Groq passed, Gemini not).
        vendor = VENDORS.get(label, label)
        return "slow", (
            f"{label} didn't answer in {timeout_s:.0f} seconds. {vendor} may be slow or limiting your key. "
            "Try again later."
        )
    if not isinstance(exc, LLMError):
        return "other", f"The test could not run ({type(exc).__name__}). Try again in a minute."
    if exc.network:
        if internet_ok:  # F7c: other AI services answer, so the member's internet is fine
            return "unreachable", (
                f"Can't reach {label} right now, though other AI services answer, so your internet is fine. "
                "Try again later (and check the address, for Custom)."
            )
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
    if is_free_limit(exc):  # founder F7b: a used-up (free) quota is said as such, a yellow notice like busy
        return "free_limit", FREE_LIMIT_LINES.get(
            label, f"Your {label} key has reached its usage limit for now. Try again later, or check your plan."
        )
    if is_busy(exc):  # founder F7: busy is not "check your internet", and not a red error
        return "busy", busy_line(label, status, key_ok=key_ok)
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
        fine = " Your key is fine." if key_ok else ""
        return "server_error", f"{label} had a problem of its own (HTTP {status}).{fine} Try again in a minute."
    code = f" (HTTP {status})" if status else ""
    return "other", f"{label} refused the test{code}. Check the key and the model name, then test again."


# --- which models a key can use (founder F3) -------------------------------------------------------------------------
# Words in a model id that mean it is not a text/chat model (embeddings, speech, images, video, moderation, realtime).
NOT_CHAT = re.compile(
    r"embed|whisper|tts|speech|transcribe|audio|realtime|dall-e|image|imagen|veo|sora|moderation|guard|aqa|"
    r"(^|[-/])live([-:]|$)|babbage|davinci|turbo-instruct|computer-use|robotics|codex|search-preview|"
    r"playai|orpheus|-ocr",
    re.IGNORECASE,
)
UNSTABLE = re.compile(r"preview|(^|[-_.])exp(erimental)?([-_.]|$)|beta|alpha|(^|[-_.])test", re.IGNORECASE)
DATED = re.compile(r"\d{8}|\d{4}-\d{2}-\d{2}|-\d{2}-\d{4}|-\d{4}$")
VERSION = re.compile(r"\d+(?:[.-]\d+)*")
MAX_MODELS = 200  # OpenRouter lists hundreds; the dropdown keeps the best ranked


def is_chat_model(model_id: str) -> bool:
    return bool(model_id) and NOT_CHAT.search(model_id) is None


def _version(model_id: str) -> tuple[int, ...]:
    """The first version number in an id: claude-sonnet-4-5-20250929 → (4, 5), gemini-3.8-flash → (3, 8)."""
    match = VERSION.search(model_id.rsplit("/", 1)[-1])
    if match is None:
        return ()
    return tuple(int(part) for part in re.split(r"[.-]", match.group()) if len(part) < 4)


def _rank(model: ModelInfo, created: dict[str, float]) -> tuple[Any, ...]:
    """Stable before preview, newest version, newest release, then the plain alias before a dated snapshot."""
    return (
        UNSTABLE.search(model.id) is None,
        _version(model.id),
        created.get(model.id, 0.0),
        DATED.search(model.id) is None,
        -len(model.id),
    )


def pick_models(
    models: list[ModelInfo], preferences: list[str], created: dict[str, float] | None = None
) -> list[ModelInfo]:
    """The models, best first: the first preference family (fnmatch on the id) the key has, then the next, then the
    rest. Within a family: stable, then the newest version. Nothing is hard-coded: only models the key listed."""
    created = created or {}
    unique = list({m.id: m for m in models if is_chat_model(m.id)}.values())

    def tier(model: ModelInfo) -> int:
        lowered = model.id.lower()
        matches = (i for i, pattern in enumerate(preferences) if fnmatch.fnmatchcase(lowered, pattern.lower()))
        return next(matches, len(preferences))

    ordered = sorted(unique, key=lambda m: _rank(m, created), reverse=True)
    return sorted(ordered, key=tier)[:MAX_MODELS]  # sorted() is stable: the rank order holds inside each tier


async def list_models(
    preset: Preset,
    key: str,
    *,
    base_url: str = "",
    timeout_s: float = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[ModelInfo], dict[str, float]]:
    """(text/chat models the key can use, their release times when given). Raises `LLMError` like a provider call does:
    a wrong key, no credit or a rate limit fail here, before any model is tried."""
    root = (base_url or preset.base_url).rstrip("/")
    models: list[ModelInfo] = []
    created: dict[str, float] = {}
    async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as client:
        try:
            match preset.kind:
                case "anthropic":
                    response = await client.get(
                        f"{root}/v1/models",
                        params={"limit": 1000},
                        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    )
                    response.raise_for_status()
                    for item in _items(response.json(), "data"):
                        models.append(ModelInfo(id=str(item.get("id", "")), label=str(item.get("display_name", ""))))
                        created[models[-1].id] = _timestamp(item.get("created_at"))
                case "gemini":
                    token = ""
                    for _ in range(5):  # pages of 1000; one is plenty today
                        params: dict[str, Any] = {"pageSize": 1000}
                        if token:
                            params["pageToken"] = token
                        response = await client.get(
                            f"{root}/v1beta/models", params=params, headers={"x-goog-api-key": key}
                        )
                        response.raise_for_status()
                        data = response.json()
                        for item in _items(data, "models"):
                            if "generateContent" not in (item.get("supportedGenerationMethods") or []):
                                continue
                            name = str(item.get("name", "")).removeprefix("models/")
                            models.append(ModelInfo(id=name, label=str(item.get("displayName", ""))))
                        token = str(data.get("nextPageToken") or "") if isinstance(data, dict) else ""
                        if not token:
                            break
                case "openai_compatible":
                    response = await client.get(f"{root}/models", headers={"Authorization": f"Bearer {key}"})
                    response.raise_for_status()
                    for item in _items(response.json(), "data"):
                        if item.get("active") is False:  # Groq marks retired models
                            continue
                        arch = item.get("architecture")
                        if isinstance(arch, dict):  # OpenRouter says what goes in and out
                            out = arch.get("output_modalities") or ["text"]
                            if "text" not in out or "image" in out or "audio" in out:
                                continue
                        model_id = str(item.get("id", ""))
                        models.append(ModelInfo(id=model_id, label=str(item.get("name", "") or "")))
                        if isinstance(item.get("created"), int | float):
                            created[model_id] = float(item["created"])
                case _:
                    return [], {}
        except (httpx.HTTPError, ValueError) as exc:
            raise _http_error(preset.label, exc, key) from exc
    return [m for m in models if is_chat_model(m.id)], created


def _items(data: Any, field: str) -> list[dict[str, Any]]:
    items = data.get(field) if isinstance(data, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _timestamp(value: Any) -> float:
    if not isinstance(value, str):
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
