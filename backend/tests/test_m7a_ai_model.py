"""M7a: the AI model card. Presets, Test key, plain-English failures, keys encrypted per workspace, routing, fallback.

Every provider call goes to an `httpx.MockTransport`: no real key, no network.
"""

from __future__ import annotations

import asyncio
import functools
import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from loguru import logger
from pydantic import SecretStr

import app.api.ai_model as ai_api
from app.api.settings import ai_model_provider
from app.config import PROJECT_ROOT, Settings
from app.llm.ai_model import (
    CONSERVATIVE_PRICE,
    AIModelChoice,
    AIModelStore,
    ModelInfo,
    SecretBox,
    build_provider,
    check_base_url,
    explain_failure,
    list_models,
    mask,
    pick_models,
    probe_key,
)
from app.llm.base import LLMError, Message
from app.llm.cloud import AnthropicAPIProvider, OpenAICompatibleProvider
from app.llm.costs import CostLedger
from app.llm.fake import FakeProvider
from app.llm.presets import LOCAL_PRESET, PRESETS, detect_preset
from app.llm.router import LLMRouter
from app.main import create_app

KEY = "sk-ant-api03-REALLYSECRET-9f3c"
SECRET = Fernet.generate_key().decode()


# What each provider's models endpoint lists for the fake key (founder F3): chat models mixed with ones that are not.
ANTHROPIC_MODELS = {
    "data": [
        {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "created_at": "2026-09-01T00:00:00Z"},
        {"id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5.5", "created_at": "2026-09-01T00:00:00Z"},
        {"id": "claude-haiku-5-5", "display_name": "Claude Haiku 5.5", "created_at": "2026-09-01T00:00:00Z"},
        {"id": "claude-sonnet-4-5-20250929", "display_name": "Claude Sonnet 4.5", "created_at": "2025-09-29T00:00:00Z"},
    ],
    "has_more": False,
}
GEMINI_MODELS = {
    "models": [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {
            "name": "models/gemini-3.8-flash",
            "displayName": "Gemini 3.8 Flash",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        },
        {"name": "models/gemini-4.0-flash-preview-11-2026", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-pro", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-flash-image", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-002", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/imagen-5.0-generate", "supportedGenerationMethods": ["predict"]},
    ]
}
OPENAI_MODELS = {
    "data": [
        {"id": "gpt-6.1-terra", "created": 1790000000},
        {"id": "gpt-6-mini", "created": 1780000000},
        {"id": "gpt-6-mini-2026-05-01", "created": 1780000000},
        {"id": "gpt-5-mini", "created": 1750000000},
        {"id": "text-embedding-3-large", "created": 1700000000},
        {"id": "whisper-1", "created": 1700000000},
        {"id": "gpt-image-2", "created": 1790000000},
        {"id": "tts-1-hd", "created": 1700000000},
        {"id": "omni-moderation-latest", "created": 1700000000},
        {"id": "gpt-6-realtime", "created": 1790000000},
    ]
}


def models_reply(request: httpx.Request) -> httpx.Response | None:
    if request.method != "GET":
        return None
    url = str(request.url)
    if "anthropic" in url:
        return httpx.Response(200, json=ANTHROPIC_MODELS)
    if "generativelanguage" in url:
        return httpx.Response(200, json=GEMINI_MODELS)
    return httpx.Response(200, json=OPENAI_MODELS)


def ok_reply(request: httpx.Request) -> httpx.Response:
    listed = models_reply(request)
    if listed is not None:
        return listed
    if "anthropic" in str(request.url):
        return httpx.Response(200, json={"content": [{"type": "text", "text": "OK"}], "usage": {}})
    if "generativelanguage" in str(request.url):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
    return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})


class Server:
    """What the fake provider answers, and every request it saw (to prove where keys went)."""

    def __init__(self) -> None:
        self.reply: Any = ok_reply
        self.seen: list[httpx.Request] = []

    @property
    def posts(self) -> list[httpx.Request]:
        """The model calls (the key test's tiny request), without the GET of the models list."""
        return [r for r in self.seen if r.method == "POST"]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply(request)  # type: ignore[no-any-return]


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Server:
    srv = Server()
    transport = httpx.MockTransport(srv.handle)
    monkeypatch.setattr(ai_api, "build_provider", functools.partial(build_provider, transport=transport))
    monkeypatch.setattr(ai_api, "list_models", functools.partial(list_models, transport=transport))

    async def public(host: str) -> list[str]:
        return {"llm.example.com": ["93.184.216.34"], "intranet.example.com": ["10.0.0.5"]}.get(host, ["8.8.8.8"])

    real_check = ai_api.check_base_url
    monkeypatch.setattr(ai_api, "check_base_url", functools.partial(real_check, resolver=public))
    return srv


@pytest.fixture
def secured(settings: Settings) -> Settings:
    return settings.model_copy(update={"founderos_secret_key": SecretStr(SECRET)})


@pytest.fixture
def client(secured: Settings) -> Any:
    with TestClient(create_app(secured)) as c:
        yield c


def _router(client: TestClient) -> LLMRouter:
    return client.app.state.orchestrator.router  # type: ignore[attr-defined,no-any-return]


# --- the card -----------------------------------------------------------------------------------------------------
def test_card_starts_on_qwen_with_every_preset_and_no_subscription_sign_in(client: TestClient) -> None:
    view = client.get("/api/settings/ai-model").json()
    assert view["in_use"] == {
        "preset": LOCAL_PRESET,
        "label": "Qwen",
        "model": "qwen3:8b",
        "verified": False,
        "local": True,
    }
    ids = [p["id"] for p in view["presets"]]
    assert ids == ["qwen_local", "claude", "gemini", "openai", "openrouter", "groq", "ollama_cloud", "custom"]
    assert view["presets"][0]["title"] == "Qwen on our server (free, private, slower)"
    ollama_cloud = next(p for p in view["presets"] if p["id"] == "ollama_cloud")
    assert ollama_cloud["base_url"] == "https://ollama.com/v1"
    text = json.dumps(view).lower()
    for banned in ("oauth", "subscription", "sign in with", "claude pro", "ai pro", "claude_code"):
        assert banned not in text
    assert view["saved"] is None and view["secret_ready"] is True and view["test_timeout_s"] == 15


def test_a_passing_key_is_saved_encrypted_and_drives_the_deep_work_agents(
    client: TestClient, server: Server, secured: Settings
) -> None:
    body = client.post("/api/settings/ai-model/test", json={"preset": "claude", "api_key": KEY}).json()
    assert body["ok"] is True
    assert body["message"] == "Claude · claude-sonnet-5-5 · key verified"
    assert body["view"]["in_use"]["verified"] is True and body["view"]["in_use"]["label"] == "Claude"
    assert body["view"]["saved"]["key_masked"] == "••••9f3c"
    # The models list, then one tiny request, to the preset's own server, with the key in the header only.
    listing, request = server.seen
    assert str(listing.url).startswith("https://api.anthropic.com/v1/models") and listing.headers["x-api-key"] == KEY
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert json.loads(request.content)["max_tokens"] == 16
    assert KEY not in json.dumps(body) and KEY not in client.get("/api/settings/ai-model").text
    assert KEY not in client.get("/api/settings").text
    # At rest: a Fernet token, never the key.
    stored = (secured.workspace_data_dir() / "ai_model.json").read_text(encoding="utf-8")
    assert KEY not in stored and "REALLYSECRET" not in stored
    assert Fernet(SECRET.encode()).decrypt(json.loads(stored)["key_token"].encode()).decode() == KEY
    # Routing: cloud on, the member's model for cloud_allowed/cloud agents, Qwen behind it; local agents stay local.
    llm = _router(client)
    assert llm.cloud_allowed is True
    assert isinstance(llm.cloud, AnthropicAPIProvider) and llm.cloud.model == "claude-sonnet-5-5"
    deep = llm.chain("cloud_allowed", agent_type="market_scout")
    assert [p.is_cloud for p in deep] == [True, False]
    assert llm.chain("local", agent_type="advisor") == [llm.local]  # the Advisor and the voice path stay local


def test_the_test_has_a_15_second_timeout(client: TestClient, server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Any] = []
    real = ai_api.build_provider

    def spy(*args: Any, **kwargs: Any) -> Any:
        built.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(ai_api, "build_provider", spy)
    client.post("/api/settings/ai-model/test", json={"preset": "openai", "api_key": "sk-proj-abcdefghijkl1234"})
    assert built[0]["timeout_s"] == 15.0

    async def slow(*_: Any, **__: Any) -> None:
        await asyncio.sleep(5)

    monkeypatch.setattr(ai_api, "probe_key", lambda provider, timeout: asyncio.wait_for(slow(), timeout=0.01))
    body = client.post("/api/settings/ai-model/test", json={"preset": "openai", "api_key": "sk-proj-abcdefghijkl1234"})
    assert body.json()["code"] == "unreachable" and "15 seconds" in body.json()["message"]


@pytest.mark.parametrize(
    ("preset", "status", "error", "code", "phrase"),
    [
        (
            "claude",
            401,
            {"error": {"type": "authentication_error", "message": "invalid x-api-key"}},
            "wrong_key",
            "Wrong key",
        ),
        (
            "gemini",
            400,
            {"error": {"message": "API key not valid. Please pass a valid API key."}},
            "wrong_key",
            "Wrong key",
        ),
        (
            "claude",
            400,
            {"error": {"message": "Your credit balance is too low to access the Anthropic API."}},
            "no_credit",
            "No credit",
        ),
        (
            "openai",
            429,
            {"error": {"code": "insufficient_quota", "message": "check billing"}},
            "no_credit",
            "No credit",
        ),
        ("openrouter", 402, {"error": {"message": "Insufficient credits"}}, "no_credit", "No credit"),
        ("groq", 429, {"error": {"message": "Rate limit reached for model"}}, "rate_limited", "Rate limited"),
        (
            "openai",
            404,
            {"error": {"code": "model_not_found", "message": "The model `gpt-x` does not exist"}},
            "model_not_found",
            "Model not found",
        ),
        ("ollama_cloud", 404, {"error": "model 'nope' not found"}, "model_not_found", "Model not found"),
        ("gemini", 503, {"error": {"message": "overloaded"}}, "unreachable", "Can't reach the server"),
    ],
)
def test_failures_are_explained_in_plain_english_and_nothing_is_saved(
    client: TestClient,
    server: Server,
    secured: Settings,
    preset: str,
    status: int,
    error: dict[str, Any],
    code: str,
    phrase: str,
) -> None:
    server.reply = lambda _request: httpx.Response(status, json=error)
    body = client.post("/api/settings/ai-model/test", json={"preset": preset, "api_key": KEY}).json()
    assert body["ok"] is False and body["code"] == code and body["message"].startswith(phrase)
    assert json.dumps(error["error"])[:20] not in body["message"]  # the provider's own text is not passed on
    assert body["view"]["in_use"]["local"] is True and body["view"]["saved"] is None
    assert not (secured.workspace_data_dir() / "ai_model.json").exists()
    assert _router(client).cloud is None


def test_an_unreachable_server_is_said_so(client: TestClient, server: Server) -> None:
    server.reply = httpx.ConnectError("Name or service not known")
    body = client.post("/api/settings/ai-model/test", json={"preset": "openai", "api_key": KEY}).json()
    assert body["code"] == "unreachable" and body["message"].startswith("Can't reach the server")


def test_custom_needs_a_public_https_address(client: TestClient, server: Server) -> None:
    def custom(url: str) -> dict[str, Any]:
        payload = {"preset": "custom", "model": "my-model", "base_url": url, "api_key": KEY}
        return client.post("/api/settings/ai-model/test", json=payload).json()  # type: ignore[no-any-return]

    for url in (
        "http://llm.example.com/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest",
        "https://intranet.example.com/v1",
        "https://user:pw@llm.example.com/v1",
        "ftp://llm.example.com",
    ):
        assert custom(url)["code"] == "bad_url", url
    assert server.seen == []
    good = custom("https://llm.example.com/v1/")
    assert good["ok"] is True and good["message"] == "Custom · my-model · key verified"
    assert "max_tokens" not in json.loads(server.posts[0].content)  # newer OpenAI models refuse it (review finding)
    assert str(server.posts[0].url) == "https://llm.example.com/v1/chat/completions"
    assert server.posts[0].headers["authorization"] == f"Bearer {KEY}"
    assert str(server.seen[0].url) == "https://llm.example.com/v1/models"  # the list asked of the same server only


def test_a_saved_key_is_reused_only_for_its_own_preset_and_address(client: TestClient, server: Server) -> None:
    client.post(
        "/api/settings/ai-model/test",
        json={"preset": "custom", "model": "m", "base_url": "https://llm.example.com/v1", "api_key": KEY},
    )
    server.seen.clear()
    again = client.post(
        "/api/settings/ai-model/test",
        json={"preset": "custom", "model": "m2", "base_url": "https://llm.example.com/v1"},
    ).json()
    assert again["ok"] is True and server.seen[0].headers["authorization"] == f"Bearer {KEY}"
    server.seen.clear()
    moved = client.post(
        "/api/settings/ai-model/test",
        json={"preset": "custom", "model": "m", "base_url": "https://other.example.com/v1"},
    ).json()
    assert moved["code"] == "missing" and server.seen == []  # never sent to a new server
    other = client.post("/api/settings/ai-model/test", json={"preset": "openai"}).json()
    assert other["code"] == "missing" and server.seen == []


def test_use_qwen_keeps_the_key_and_remove_key_deletes_it(
    client: TestClient, server: Server, secured: Settings
) -> None:
    client.post("/api/settings/ai-model/test", json={"preset": "groq", "api_key": KEY})
    assert isinstance(_router(client).cloud, OpenAICompatibleProvider)
    local = client.post("/api/settings/ai-model/use-local").json()
    assert local["in_use"]["local"] is True and local["saved"]["key_masked"] == "••••9f3c"
    assert _router(client).cloud is None  # Qwen, even if .env names a deep provider
    removed = client.delete("/api/settings/ai-model/key").json()
    assert removed["saved"] is None and removed["in_use"]["local"] is True
    stored = json.loads((secured.workspace_data_dir() / "ai_model.json").read_text(encoding="utf-8"))
    assert stored["key_token"] == "" and stored["key_last4"] == ""


def test_the_choice_survives_a_restart_and_cloud_off_still_wins(secured: Settings, server: Server) -> None:
    with TestClient(create_app(secured)) as first:
        first.post("/api/settings/ai-model/test", json={"preset": "openai", "api_key": KEY})
    with TestClient(create_app(secured)) as second:
        llm = _router(second)
        assert isinstance(llm.cloud, OpenAICompatibleProvider) and llm.cloud_allowed is True
        second.put("/api/settings", json={"cloud_allowed": False})  # the kill switch
        assert _router(second).chain("cloud_allowed", agent_type="market_scout") == [llm.local]
        assert second.get("/api/settings/ai-model").json()["cloud_paused"] is True


def test_no_server_secret_means_no_key_is_kept(settings: Settings, server: Server) -> None:
    with TestClient(create_app(settings)) as c:
        view = c.get("/api/settings/ai-model").json()
        assert view["secret_ready"] is False and "setup.bat" in view["secret_problem"]
        body = c.post("/api/settings/ai-model/test", json={"preset": "claude", "api_key": KEY}).json()
        assert body["code"] == "no_secret" and server.seen == []


def test_a_key_saved_under_another_secret_reads_as_unreadable_and_qwen_is_used(secured: Settings) -> None:
    other = SecretBox(Fernet.generate_key().decode())
    AIModelStore(secured.workspace_data_dir()).save(
        AIModelChoice(active=True, preset="claude", model="claude-sonnet-5-5", key_token=other.encrypt(KEY))
    )
    assert ai_model_provider(secured) == (True, None)
    with TestClient(create_app(secured)) as c:
        view = c.get("/api/settings/ai-model").json()
        assert view["in_use"]["local"] is True and view["saved"]["unreadable"] is True
        assert _router(c).cloud is None


def test_keys_never_reach_the_log(client: TestClient, server: Server) -> None:
    lines: list[str] = []
    sink = logger.add(lines.append, level="DEBUG")
    try:
        client.post("/api/settings/ai-model/test", json={"preset": "claude", "api_key": KEY})
        server.reply = lambda _r: httpx.Response(401, text=f"bad key {KEY}")
        client.post("/api/settings/ai-model/test", json={"preset": "claude", "api_key": KEY})
        client.delete("/api/settings/ai-model/key")
    finally:
        logger.remove(sink)
    assert lines and not any(KEY in line or "REALLYSECRET" in line for line in lines)


# --- routing, fallback, privacy and cap ------------------------------------------------------------------------------
async def test_a_failing_member_model_falls_back_to_qwen_through_the_privacy_filter(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []

    def broken(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(500, json={"error": "down"})

    cloud = build_provider(PRESETS["openrouter"], "some/model", KEY, transport=httpx.MockTransport(broken))
    ledger = CostLedger(tmp_path / "calls.jsonl", prices={"some/model": CONSERVATIVE_PRICE})
    local = FakeProvider(["from qwen"], name="ollama", model="qwen3:8b")
    llm = LLMRouter(local, cloud, cloud_allowed=True, ledger=ledger)
    done = await llm.complete(
        "cloud_allowed", [Message.user("mail ana@example.com about it")], agent_type="market_scout"
    )
    assert done.text == "from qwen" and done.fallback_from == "openrouter"
    assert "ana@example.com" not in json.dumps(seen)  # the privacy filter ran on the member's provider too
    ledger.monthly_cap_usd = 0.0
    assert llm.chain("cloud_allowed", agent_type="market_scout") == [local]  # the cap still sends calls to Qwen


def test_a_member_model_with_no_known_price_is_capped_at_a_conservative_price(
    client: TestClient, server: Server
) -> None:
    client.post(
        "/api/settings/ai-model/test", json={"preset": "openrouter", "model": "vendor/new-model", "api_key": KEY}
    )
    ledger = _router(client).ledger
    assert ledger is not None and ledger.prices["vendor/new-model"] == CONSERVATIVE_PRICE
    assert ledger.refusal("vendor/new-model") is None


async def test_ollama_cloud_gets_the_schema_in_the_instructions(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    provider = build_provider(PRESETS["ollama_cloud"], "gemma4:31b", KEY, transport=httpx.MockTransport(handler))
    done = await provider.complete([Message.user("hi")], json_schema={"type": "object"})
    assert done.json() == {"a": 1}
    assert "response_format" not in seen[0]
    assert '{"type": "object"}' in seen[0]["messages"][-1]["content"]


async def test_probe_key_raises_on_failure() -> None:
    provider = build_provider(
        PRESETS["openai"], "m", KEY, transport=httpx.MockTransport(lambda _r: httpx.Response(401, json={}))
    )
    with pytest.raises(LLMError) as caught:
        await probe_key(provider, 15)
    assert explain_failure(caught.value, "OpenAI", "m", 15)[0] == "wrong_key"


# --- pieces ---------------------------------------------------------------------------------------------------------
def test_secret_box_and_mask() -> None:
    box = SecretBox(SECRET)
    token = box.encrypt(KEY)
    assert KEY not in token and box.decrypt(token) == KEY
    assert SecretBox(Fernet.generate_key().decode()).decrypt(token) is None
    assert not SecretBox(None).ready and "setup.bat" in (SecretBox(None).problem or "")
    assert not SecretBox("not-a-key").ready and "not a valid key" in (SecretBox("not-a-key").problem or "")
    assert mask(KEY) == "••••9f3c" and mask("short") == "••••"


async def test_base_url_check_resolves_names() -> None:
    async def resolver(host: str) -> list[str]:
        return {"localhost": ["127.0.0.1"], "api.example.com": ["93.184.216.34"]}[host]

    assert await check_base_url("https://api.example.com/v1/", resolver=resolver) == "https://api.example.com/v1"
    with pytest.raises(ValueError, match="private or local"):
        await check_base_url("https://localhost/v1", resolver=resolver)
    assert await check_base_url("http://192.168.1.20:8080/v1", allow_private=True) == "http://192.168.1.20:8080/v1"


def test_ensure_secret_script_creates_once_and_never_prints_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = importlib.util.spec_from_file_location("ensure_secret", PROJECT_ROOT / "scripts" / "ensure_secret.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env = tmp_path / ".env"
    env.write_text("OLLAMA_CHAT_MODEL=qwen3:8b\nFOUNDEROS_SECRET_KEY=\n", encoding="utf-8")
    assert module.main(["--env-file", str(env)]) == 0
    text = env.read_text(encoding="utf-8")
    secret = text.split("FOUNDEROS_SECRET_KEY=")[1].strip()
    assert SecretBox(secret).ready and text.startswith("OLLAMA_CHAT_MODEL=qwen3:8b\n") and text.count("FOUNDEROS") == 1
    assert secret not in capsys.readouterr().out
    assert module.main(["--env-file", str(env)]) == 0 and env.read_text(encoding="utf-8") == text  # left alone
    assert module.main(["--env-file", str(tmp_path / "none.env"), "--check"]) == 1


# --- founder F3: key-only setup ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("key", "preset"),
    [
        ("AIzaSyA-fake-gemini-key-000000000", "gemini"),
        ("sk-ant-api03-fake-000000000000", "claude"),
        ("sk-or-v1-fake-0000000000000000", "openrouter"),
        ("gsk_fake0000000000000000000000", "groq"),
        ("sk-proj-fake00000000000000000000", "openai"),
        ("sk-fake000000000000000000000000", "openai"),
        ("  sk-ant-api03-padded-0000000000  ", "claude"),
        ("0123abcd.ollama-ish-key", None),
        ("", None),
    ],
)
def test_the_provider_is_found_from_the_key_shape(key: str, preset: str | None) -> None:
    assert detect_preset(key) == preset


@pytest.mark.parametrize(
    ("key", "preset", "label", "model"),
    [
        ("sk-ant-api03-fake-key-0000-9f3c", "claude", "Claude", "claude-sonnet-5-5"),
        # Not gemini-2.5-flash (older), not the 4.0 preview, not -lite or -image: the newest stable Flash.
        ("AIzaSyFAKE-gemini-key-00000-9f3c", "gemini", "Gemini", "gemini-3.8-flash"),
        ("sk-proj-fake-openai-key-0000-9f3c", "openai", "OpenAI", "gpt-6-mini"),
    ],
)
def test_only_a_key_picks_the_provider_and_the_best_model_it_has(
    client: TestClient, server: Server, key: str, preset: str, label: str, model: str
) -> None:
    body = client.post("/api/settings/ai-model/test", json={"api_key": key}).json()
    assert body["ok"] is True and body["preset"] == preset
    assert body["message"] == f"{label} · {model} · key verified"
    assert body["view"]["in_use"] == {
        "preset": preset,
        "label": label,
        "model": model,
        "verified": True,
        "local": False,
    }
    ids = [m["id"] for m in body["view"]["saved"]["models"]]
    assert ids[0] == model
    for not_chat in ("embedding", "whisper", "image", "tts", "moderation", "realtime", "imagen"):
        assert not any(not_chat in i for i in ids), (not_chat, ids)
    assert len(server.posts) == 1 and server.seen[0].method == "GET"
    assert key not in json.dumps(body)


def test_gemini_lists_with_the_key_in_a_header_not_the_address(client: TestClient, server: Server) -> None:
    key = "AIzaSyFAKE-gemini-key-00000-9f3c"
    client.post("/api/settings/ai-model/test", json={"api_key": key})
    listing = server.seen[0]
    assert listing.url.path == "/v1beta/models" and listing.headers["x-goog-api-key"] == key
    assert key not in str(listing.url)


def test_a_key_with_no_known_shape_asks_for_the_provider_and_sends_nothing(client: TestClient, server: Server) -> None:
    body = client.post("/api/settings/ai-model/test", json={"api_key": "0123abcd.ollama-ish-key"}).json()
    assert body["ok"] is False and body["code"] == "unknown_provider" and "Pick the provider" in body["message"]
    assert server.seen == []
    picked = client.post(
        "/api/settings/ai-model/test", json={"preset": "ollama_cloud", "api_key": "0123abcd.ollama-ish-key"}
    ).json()
    assert picked["ok"] is True and str(server.seen[0].url) == "https://ollama.com/v1/models"  # the list overrides


def test_the_list_overrides_the_key_shape(client: TestClient, server: Server) -> None:
    """An OpenRouter-style proxy key in the Custom preset: the member's pick wins over the shape."""
    body = client.post(
        "/api/settings/ai-model/test",
        json={"preset": "custom", "base_url": "https://llm.example.com/v1", "api_key": "sk-ant-proxied-000000000"},
    ).json()
    assert body["ok"] is True and body["preset"] == "custom" and server.seen[0].url.host == "llm.example.com"


def test_a_wrong_key_fails_at_the_models_list_and_no_model_is_tried(client: TestClient, server: Server) -> None:
    server.reply = lambda _r: httpx.Response(401, json={"error": {"type": "authentication_error"}})
    body = client.post("/api/settings/ai-model/test", json={"api_key": KEY}).json()
    assert body["code"] == "wrong_key" and body["preset"] == "claude" and server.posts == []


def test_a_listed_model_that_refuses_the_key_is_skipped_for_the_next_best(client: TestClient, server: Server) -> None:
    """Like gemini-2.5-flash for new users: listed, but not open to this key."""

    def reply(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "gemini-3.8-flash:" in request.url.path:
            return httpx.Response(
                404, json={"error": {"message": "models/gemini-3.8-flash is not found for API version v1beta"}}
            )
        return ok_reply(request)

    server.reply = reply
    body = client.post("/api/settings/ai-model/test", json={"api_key": "AIzaSyFAKE-gemini-key-00000-9f3c"}).json()
    assert body["ok"] is True and body["message"] == "Gemini · gemini-2.5-flash · key verified"
    assert [r.url.path.split("/")[-1] for r in server.posts] == [
        "gemini-3.8-flash:generateContent",
        "gemini-2.5-flash:generateContent",
    ]


def test_change_model_uses_the_saved_key_and_keeps_the_list(client: TestClient, server: Server) -> None:
    first = client.post("/api/settings/ai-model/test", json={"api_key": KEY}).json()
    assert first["view"]["in_use"]["model"] == "claude-sonnet-5-5"
    server.seen.clear()
    changed = client.post("/api/settings/ai-model/test", json={"preset": "claude", "model": "claude-haiku-5-5"}).json()
    assert changed["ok"] is True and changed["message"] == "Claude · claude-haiku-5-5 · key verified"
    assert server.posts[0].headers["x-api-key"] == KEY and json.loads(server.posts[0].content)["model"] == (
        "claude-haiku-5-5"
    )
    assert [m["id"] for m in changed["view"]["saved"]["models"]][:3] == [
        "claude-sonnet-5-5",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-5-5",
    ]


def test_a_server_with_no_models_list_needs_the_model_name_under_advanced(client: TestClient, server: Server) -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "no such route"}) if request.method == "GET" else ok_reply(request)

    server.reply = reply
    custom = {"preset": "custom", "base_url": "https://llm.example.com/v1", "api_key": KEY}
    body = client.post("/api/settings/ai-model/test", json=custom).json()
    assert body["code"] == "missing" and "under Advanced" in body["message"] and server.posts == []
    named = client.post("/api/settings/ai-model/test", json={**custom, "model": "my-model"}).json()
    assert named["ok"] is True and named["message"] == "Custom · my-model · key verified"


async def test_openrouter_and_groq_lists_keep_text_models_only() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openrouter.ai":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "google/gemini-3.8-flash", "architecture": {"output_modalities": ["text"]}},
                        {
                            "id": "google/gemini-3.8-flash-image",
                            "architecture": {"output_modalities": ["image", "text"]},
                        },
                        {"id": "anthropic/claude-sonnet-5-5", "architecture": {"output_modalities": ["text"]}},
                        {"id": "openai/gpt-6-mini", "architecture": {"output_modalities": ["text"]}},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "llama-3.3-70b-versatile", "active": True},
                    {"id": "openai/gpt-oss-120b", "active": True},
                    {"id": "whisper-large-v3", "active": True},
                    {"id": "meta-llama/llama-guard-4-12b", "active": True},
                    {"id": "old-model-retired", "active": False},
                    {"id": "playai-tts", "active": True},
                ]
            },
        )

    transport = httpx.MockTransport(reply)
    settings = Settings(_env_file=None)
    routed, _ = await list_models(PRESETS["openrouter"], KEY, transport=transport)
    ranked = pick_models(routed, settings.ai_model_preferences["openrouter"])
    assert [m.id for m in ranked] == ["google/gemini-3.8-flash", "anthropic/claude-sonnet-5-5", "openai/gpt-6-mini"]
    groq, _ = await list_models(PRESETS["groq"], KEY, transport=transport)
    assert [m.id for m in pick_models(groq, settings.ai_model_preferences["groq"])] == [
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
    ]


def test_pick_models_prefers_stable_and_newest_within_a_family() -> None:
    ids = ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-4.0-flash-preview-11-2026", "gemini-3.8-pro", "gemini-x"]
    ranked = [
        m.id
        for m in pick_models([ModelInfo(id=i) for i in ids], Settings(_env_file=None).ai_model_preferences["gemini"])
    ]
    assert ranked == [
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-4.0-flash-preview-11-2026",
        "gemini-3.8-pro",
        "gemini-x",
    ]
    only_preview = pick_models([ModelInfo(id="gemini-4.0-flash-preview-11-2026")], ["gemini-*-flash"])
    assert [m.id for m in only_preview] == ["gemini-4.0-flash-preview-11-2026"]  # used when it is all the key has
    assert pick_models([ModelInfo(id="gemini-flash-latest")], [])[0].id == "gemini-flash-latest"
