"""M7a gate fix round 2 (founder F4-F8, F12, 2026-11-26). Fakes only: no real key, no network, no Ollama.

F4 a failed test never turns cloud on; F5 key shapes as data (AQ. → Gemini, native endpoint), unknown keys, prefix
log; F6 the verified AI model shown everywhere; F7 busy (503/429) retried and said plainly; F8 a slow cloud agent
offered Qwen, switched only on the member's OK; F12 the spend report in the member's currency.
"""

from __future__ import annotations

import asyncio
import functools
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from loguru import logger
from pydantic import SecretStr

import app.api.ai_model as ai_api
from app.agents.events import AgentEvent, EventBus
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentResult, AgentRunner
from app.config import Settings
from app.llm.ai_model import build_provider, explain_failure, list_models
from app.llm.base import Completion, LLMError, LLMProvider, Message, ToolSpec
from app.llm.costs import CallRecord, CostLedger
from app.llm.fake import FakeProvider
from app.llm.presets import SHIPPED_KEY_SHAPES, detect_preset, load_key_shapes
from app.llm.router import LLMRouter
from app.llm.spend import FxRates, SpendReport, from_usd, money, spend_of, to_usd
from app.main import create_app

SECRET = Fernet.generate_key().decode()
AQ_KEY = "AQ.Ab8RN6LfakeFAKEfake-0000000000000000"
GEMINI_LIST = {
    "models": [
        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-pro", "supportedGenerationMethods": ["generateContent"]},
    ]
}


class Server:
    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []
        self.post_statuses: list[int] = []  # what each model call answers, in order (then 200)
        self.list_statuses: list[int] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.method == "GET":
            status = self.list_statuses.pop(0) if self.list_statuses else 200
            if status != 200:
                return httpx.Response(status, json={"error": {"message": "overloaded"}})
            if "generativelanguage" in str(request.url):
                return httpx.Response(200, json=GEMINI_LIST)
            if "anthropic" in str(request.url):
                return httpx.Response(200, json={"data": [{"id": "claude-sonnet-5-5"}]})
            return httpx.Response(200, json={"data": [{"id": "gpt-6-mini"}]})
        status = self.post_statuses.pop(0) if self.post_statuses else 200
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "The model is overloaded."}})
        if "generativelanguage" in str(request.url):
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
        if "anthropic" in str(request.url):
            return httpx.Response(200, json={"content": [{"type": "text", "text": "OK"}], "usage": {}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Server:
    srv = Server()
    transport = httpx.MockTransport(srv.handle)
    monkeypatch.setattr(ai_api, "build_provider", functools.partial(build_provider, transport=transport))
    monkeypatch.setattr(ai_api, "list_models", functools.partial(list_models, transport=transport))
    waits: list[float] = []

    async def instant(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("app.llm.ai_model._sleep", instant)
    srv.waits = waits  # type: ignore[attr-defined]
    return srv


@pytest.fixture
def secured(settings: Settings) -> Settings:
    return settings.model_copy(update={"founderos_secret_key": SecretStr(SECRET)})


@pytest.fixture
def client(secured: Settings) -> Any:
    with TestClient(create_app(secured)) as c:
        yield c


def _test(client: TestClient, **body: Any) -> dict[str, Any]:
    return client.post("/api/settings/ai-model/test", json=body).json()  # type: ignore[no-any-return]


# --- F4: a failed test changes nothing; only a passing key may turn cloud on ------------------------------------------
def test_f4_a_failed_test_never_turns_cloud_on(client: TestClient, server: Server, secured: Settings) -> None:
    server.list_statuses = [401]
    body = _test(client, api_key="sk-ant-wrong-000000000000")
    assert body["ok"] is False and body["code"] == "wrong_key"
    assert client.get("/api/settings").json()["cloud_allowed"] is False
    assert not (secured.workspace_data_dir() / "ui_settings.json").exists()  # nothing at all was saved
    assert client.app.state.orchestrator.router.cloud_allowed is False  # type: ignore[attr-defined]


def test_f4_cloud_cannot_be_ticked_on_without_a_passing_key(client: TestClient, server: Server) -> None:
    refused = client.put("/api/settings", json={"cloud_allowed": True})
    assert refused.status_code == 422 and "Test and save a key" in refused.json()["detail"]
    view = client.get("/api/settings").json()
    assert view["cloud_allowed"] is False and view["cloud_usable"] is False
    assert _test(client, api_key=AQ_KEY)["ok"] is True  # a passing key turns it on
    assert client.get("/api/settings").json()["cloud_allowed"] is True
    assert client.put("/api/settings", json={"cloud_allowed": False}).json()["cloud_allowed"] is False
    assert client.put("/api/settings", json={"cloud_allowed": True}).json()["cloud_allowed"] is True


def test_f4_an_env_key_still_lets_cloud_be_turned_on(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"gemini_api_key": SecretStr("k")}))
    with TestClient(app) as client:
        assert client.put("/api/settings", json={"cloud_allowed": True}).json()["cloud_allowed"] is True


# --- F5: key shapes as data, AQ. keys, unknown keys, prefix log ------------------------------------------------------
def test_f5_aq_keys_are_gemini_and_aiza_stays_as_legacy() -> None:
    shapes = load_key_shapes()
    assert detect_preset(AQ_KEY, shapes) == "gemini"
    assert detect_preset("AIzaSyLegacy000000", shapes) == "gemini"
    legacy = next(s for s in shapes if s.prefix == "AIza")
    assert legacy.legacy is True and next(s for s in shapes if s.prefix == "AQ.").legacy is False
    assert detect_preset("xyz-unknown-key", shapes) is None
    shipped = json.loads(SHIPPED_KEY_SHAPES.read_text(encoding="utf-8"))
    assert [s["prefix"] for s in shipped["shapes"]][:3] == ["sk-ant-", "sk-or-", "gsk_"]


def test_f5_the_server_can_change_the_hints_without_code(client: TestClient, secured: Settings) -> None:
    local = secured.workspace_data_dir().parent / "key_shapes.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps({"shapes": [{"prefix": "nv-", "preset": "openrouter"}]}), encoding="utf-8")
    view = client.get("/api/settings/ai-model").json()
    assert view["key_shapes"] == [{"prefix": "nv-", "preset": "openrouter"}]
    local.write_text("not json", encoding="utf-8")  # a damaged copy falls back to the shipped table
    assert {"prefix": "AQ.", "preset": "gemini"} in client.get("/api/settings/ai-model").json()["key_shapes"]


def test_f5_an_aq_key_uses_the_native_gemini_endpoint(client: TestClient, server: Server) -> None:
    body = _test(client, api_key=AQ_KEY)
    assert body["ok"] is True and body["message"] == "Gemini · gemini-3.8-flash · key verified"
    listing, call = server.seen
    assert str(listing.url).startswith("https://generativelanguage.googleapis.com/v1beta/models")
    assert str(call.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    for request in (listing, call):
        assert request.headers["x-goog-api-key"] == AQ_KEY and "authorization" not in request.headers
        assert "openai" not in str(request.url)


def test_f5_an_unknown_key_says_so_and_is_never_sent(client: TestClient, server: Server) -> None:
    body = _test(client, api_key="zz-unknown-1234567890")
    assert body["ok"] is False and body["code"] == "unknown_provider"
    assert body["message"] == "We couldn't recognise this key. Please check it, or pick the provider that issued it."
    assert server.seen == [] and body["view"]["in_use"]["local"] is True


def test_f5_only_three_characters_of_a_passing_key_reach_the_log(client: TestClient, server: Server) -> None:
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="INFO")
    try:
        assert _test(client, api_key=AQ_KEY)["ok"] is True
    finally:
        logger.remove(sink)
    shape = [line for line in lines if "key shape" in line]
    assert len(shape) == 1 and "'AQ.'" in shape[0] and "gemini" in shape[0]
    assert all(AQ_KEY[:4] not in line for line in lines)


# --- F6: the verified AI model everywhere -------------------------------------------------------------------------
def test_f6_top_bar_cloud_section_and_default_show_the_verified_model(client: TestClient, server: Server) -> None:
    cloud = next(d for d in client.get("/api/health").json()["dependencies"] if d["name"] == "cloud")
    assert cloud["info"]["ai_model"] is None and cloud["info"]["cloud_usable"] is False
    assert _test(client, api_key=AQ_KEY)["ok"] is True
    cloud = next(d for d in client.get("/api/health").json()["dependencies"] if d["name"] == "cloud")
    assert cloud["state"] == "ok" and cloud["info"]["cloud_usable"] is True
    assert cloud["info"]["ai_model"]["text"] == "Gemini · gemini-3.8-flash (from AI model)"
    assert "Gemini · gemini-3.8-flash (from AI model)" in cloud["detail"]
    view = client.get("/api/settings").json()
    assert view["ai_model"]["text"] == "Gemini · gemini-3.8-flash (from AI model)" and view["cloud_usable"] is True
    assert client.post("/api/settings/ai-model/use-local").status_code == 200
    assert client.get("/api/settings").json()["ai_model"] is None


# --- F7: busy is retried and said plainly ---------------------------------------------------------------------------
def test_f7_a_busy_gemini_is_asked_again_and_then_passes(client: TestClient, server: Server) -> None:
    server.post_statuses = [503, 503]
    body = _test(client, api_key=AQ_KEY)
    assert body["ok"] is True
    assert len([r for r in server.seen if r.method == "POST"]) == 3
    assert server.waits == [0.6, 1.8]  # type: ignore[attr-defined]  # short back-off, inside the 15 s


def test_f7_still_busy_says_the_key_is_fine_and_keeps_the_green_chip(client: TestClient, server: Server) -> None:
    assert _test(client, api_key=AQ_KEY)["ok"] is True
    server.post_statuses = [503, 503, 503]
    body = _test(client, preset="gemini", model="gemini-3.8-pro")  # Change model while Google is overloaded
    assert body["ok"] is False and body["code"] == "busy"
    assert body["message"] == ("Gemini is busy right now (Google error 503). Your key is fine. Try again in a minute.")
    assert body["view"]["in_use"]["verified"] is True and body["view"]["in_use"]["model"] == "gemini-3.8-flash"


def test_f7_429_is_handled_the_same_way_but_no_credit_is_not() -> None:
    busy = LLMError("x", status=429, detail="Resource has been exhausted (e.g. check quota).")
    code, line = explain_failure(busy, "Gemini", "m", 15, key_ok=True)
    assert code == "busy" and line.startswith("Gemini is busy right now (Google error 429). Your key is fine.")
    broke = LLMError("x", status=429, detail='{"code": "insufficient_quota"}')
    assert explain_failure(broke, "OpenAI", "m", 15)[0] == "no_credit"
    assert "internet" not in explain_failure(LLMError("x", status=503, detail=""), "Gemini", "m", 15)[1]


# --- F8: a slow cloud agent is named; Qwen only with the member's OK --------------------------------------------------
class SlowCloud(LLMProvider):
    name = "gemini"
    model = "gemini-3.8-flash"
    is_cloud = True

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.cancelled = False

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        try:
            await asyncio.sleep(self.seconds)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return Completion(text="cloud answer", provider=self.name, model=self.model)


def _slow_runner(cloud: LLMProvider, bus: EventBus) -> tuple[AgentRunner, AgentInstance]:
    router = LLMRouter(FakeProvider(["qwen answer"], name="ollama", model="qwen3:8b"), cloud, cloud_allowed=True)
    runner = AgentRunner(router, bus, "run_slow", lambda _aid: None)  # type: ignore[arg-type,return-value]
    runner.go_local, runner.slow_after_s, runner.slow_min_s = asyncio.Event(), 0.05, 0.0
    inst = AgentInstance(type="market_scout", name="Market Scout", brief="b", is_cloud=True, provider="gemini")
    return runner, inst


async def test_f8_slow_cloud_is_named_and_switches_only_with_ok() -> None:
    bus, cloud = EventBus(), SlowCloud(30)
    runner, inst = _slow_runner(cloud, bus)
    task = asyncio.create_task(runner._complete(REGISTRY["market_scout"], inst, [Message.user("q")], None))
    await asyncio.sleep(0.3)
    slow = [e for e in bus.history("run_slow") if e.type == "agent.slow"]
    assert len(slow) == 1 and not task.done()  # named, and still waiting: nothing switched on its own
    assert slow[0].data["reason"].startswith("Gemini has not answered in 0 s")
    steps = [e.data["step"] for e in bus.history("run_slow") if e.type == "agent.step"]
    assert steps == [f"Slow: {slow[0].data['reason']}"]  # the card shows the reason
    assert runner.go_local is not None
    runner.go_local.set()  # "Continue on Qwen on our server"
    completion = await asyncio.wait_for(task, 2)
    assert completion.text == "qwen answer" and completion.fallback_from == "gemini" and cloud.cancelled
    assert runner.on_local is True
    assert any(
        "Switched to Qwen on our server, with your OK" in e.data.get("step", "") for e in bus.history("run_slow")
    )


async def test_f8_keep_waiting_keeps_the_cloud_answer() -> None:
    bus, cloud = EventBus(), SlowCloud(0.3)
    runner, inst = _slow_runner(cloud, bus)
    completion = await runner._complete(REGISTRY["market_scout"], inst, [Message.user("q")], None)
    assert completion.text == "cloud answer" and runner.on_local is False
    assert len([e for e in bus.history("run_slow") if e.type == "agent.slow"]) == 1


async def test_f8_a_quick_cloud_answer_offers_nothing() -> None:
    bus, cloud = EventBus(), SlowCloud(0.0)
    runner, inst = _slow_runner(cloud, bus)
    runner.slow_after_s = 5
    assert (await runner._complete(REGISTRY["market_scout"], inst, [Message.user("q")], None)).text == "cloud answer"
    assert not [e for e in bus.history("run_slow") if e.type == "agent.slow"]


def test_f8_twice_the_usual_time_comes_first(tmp_path: Path) -> None:
    ledger = CostLedger(tmp_path / "calls.jsonl")
    for ms in (8000, 9000, 10000):
        ledger.record(CallRecord(agent_type="market_scout", provider="gemini", model="m", is_cloud=True, latency_ms=ms))
    runner = AgentRunner(LLMRouter(FakeProvider(), ledger=ledger), EventBus(), "r", lambda _a: None)  # type: ignore[arg-type,return-value]
    runner.slow_after_s, runner.slow_min_s = 45, 15
    assert runner.slow_limit("market_scout") == (18.0, 9.0)
    assert runner.slow_limit("devils_advocate") == (45, None)


def test_f8_the_lane_says_the_slow_agent_and_offers_the_choice(client: TestClient) -> None:
    manager = client.app.state.conversation  # type: ignore[attr-defined]
    session = manager.session()
    event = AgentEvent(seq=1, type="agent.slow", run_id="run_x", agent_id="agt_1", data={"reason": "Gemini slow"})
    manager._slow_offer(session, "run_x", event)
    said = [e for e in manager.bus.history() if e.type == "slow.offered"]
    assert said and "Continue" not in said[-1].data["text"] and "Qwen on our server" in said[-1].data["text"]
    assert said[-1].data["agent"] == "agt_1" and said[-1].data["run"] == "run_x"


def test_f8_continue_on_qwen_needs_a_running_agent(client: TestClient) -> None:
    assert client.post("/api/runs/nope/agents/agt_x/continue-local").status_code == 409
    assert client.post("/api/runs/nope/agents/agt_x/keep-waiting").status_code == 409


# --- F12: what a decision cost, in the member's currency -----------------------------------------------------------
def test_f12_money_is_rounded_for_reading() -> None:
    assert money(0.012, "INR", 84.0) == "about ₹1"
    assert money(0.0001, "INR", 84.0) == "less than ₹0.01"
    assert money(0.04, "USD", 1.0) == "about $0.04"
    assert money(1.0, "INR", 84.0) == "about ₹84"
    assert money(0.0, "USD", 1.0) == "nothing"
    assert to_usd(840, 84.0) == 10.0 and from_usd(10, 84.0) == 840.0


def test_f12_the_spend_sentence_names_calls_and_free_qwen_parts() -> None:
    cloud = AgentResult(agent_id="a", type="market_scout", name="MS", brief="b", est_cost_usd=0.012)
    cloud.cloud_calls = {"Gemini": 4}
    local = AgentResult(agent_id="b", type="librarian", name="LB", brief="b", local_calls=2)
    report = spend_of([cloud, local])
    assert report == SpendReport(usd=0.012, cloud_calls={"Gemini": 4}, local_parts=True)
    assert report.sentence("INR", 84.0) == "This decision cost about ₹1: Gemini 4 calls; Qwen parts free."
    assert spend_of([local]).sentence("INR", 84.0).startswith("This decision cost nothing")
    unknown = AgentResult(agent_id="c", type="market_scout", name="MS", brief="b", est_cost_usd=None)
    unknown.cloud_calls = {"Groq": 1}
    assert "unknown amount" in spend_of([unknown]).sentence("USD", 1.0)


async def test_f12_rates_are_fetched_once_a_day_cached_and_fall_back_to_usd(tmp_path: Path) -> None:
    calls: list[str] = []

    async def fetch(url: str) -> dict[str, Any]:
        calls.append(url)
        return {"result": "success", "rates": {"USD": 1, "INR": 84.2, "EUR": 0.9}}

    fx = FxRates(tmp_path, "https://fx.example/latest/USD", fetcher=fetch)
    assert fx.rate("INR") == ("USD", 1.0)  # nothing yet: US dollars
    await fx.refresh()
    await fx.refresh()  # fresh for a day: no second fetch
    assert calls == ["https://fx.example/latest/USD"] and fx.rate("INR") == ("INR", 84.2)
    again = FxRates(tmp_path, "https://fx.example/latest/USD", fetcher=fetch)  # the cached table survives a restart
    assert again.rate("EUR") == ("EUR", 0.9) and again.rate("XYZ") == ("USD", 1.0)
    assert again.info("INR")["symbol"] == "₹"

    async def broken(url: str) -> dict[str, Any]:
        raise httpx.ConnectError("no network")

    offline = FxRates(tmp_path / "other", "https://fx.example/latest/USD", fetcher=broken)
    await offline.refresh()
    assert offline.rate("INR") == ("USD", 1.0)


def test_f12_settings_show_the_member_currency_and_keep_the_cap_in_usd(client: TestClient) -> None:
    view = client.put("/api/settings", json={"member_currency": "INR"}).json()
    assert view["member_currency"] == "INR"
    assert view["fx"]["currency"] == "USD" and view["fx"]["asked"] == "INR"  # no rate in tests: shown in USD
    client.app.state.fx._table.rates = {"INR": 84.0}  # type: ignore[attr-defined]
    client.app.state.fx._table.fetched_at = datetime.now(UTC)  # type: ignore[attr-defined]
    view = client.put("/api/settings", json={"cloud_monthly_cap_usd": to_usd(840, 84.0)}).json()
    assert view["cloud_monthly_cap_usd"] == 10.0 and view["fx"] == {
        "asked": "INR",
        "currency": "INR",
        "symbol": "₹",
        "rate": 84.0,
        "as_of": view["fx"]["as_of"],
        "source": "",
    }
    assert client.put("/api/settings", json={"member_currency": "rupees"}).status_code == 422


def test_f12_the_advisor_says_the_cost_at_the_end_in_the_member_currency(client: TestClient) -> None:
    from types import SimpleNamespace

    orchestrator = client.app.state.orchestrator  # type: ignore[attr-defined]
    manager = client.app.state.conversation  # type: ignore[attr-defined]
    orchestrator.currency_rate = lambda: ("INR", 84.0)
    spend = SpendReport(usd=0.012, cloud_calls={"Gemini": 4}, local_parts=True)
    orchestrator.runs["run_cost"] = SimpleNamespace(result=SimpleNamespace(agents=[object()], spend=spend))
    session = manager.session()
    manager._spend(session, "run_cost")
    said = [e for e in manager.bus.history() if e.type == "spend"]
    assert said[-1].data["text"] == "This decision cost about ₹1: Gemini 4 calls; Qwen parts free."
    assert said[-1].data["spoken"] is True and said[-1].data["usd"] == 0.012
    assert session.narration == [] or "cost" not in session.narration[-1]  # the "ready" line stays the last one


def test_f12_the_memo_says_what_the_decision_cost(client: TestClient) -> None:
    from types import SimpleNamespace

    orchestrator = client.app.state.orchestrator  # type: ignore[attr-defined]
    orchestrator.currency_rate = lambda: ("INR", 84.0)
    vault = orchestrator.ctx_factory("").vault.vault
    vault.write_note("decisions/2026-11-26-dubai.md", frontmatter={"title": "Dubai"}, body="# Dubai\n\nWe propose X.")
    result = SimpleNamespace(
        memo=SimpleNamespace(path="decisions/2026-11-26-dubai.md"),
        spend=SpendReport(usd=0.012, cloud_calls={"Gemini": 4}, local_parts=True),
    )
    orchestrator._note_cost_in_memo(result)
    orchestrator._note_cost_in_memo(result)  # once only
    body = vault.read_note("decisions/2026-11-26-dubai.md")["body"]
    assert body.count("## What this decision cost") == 1
    assert "This decision cost about ₹1: Gemini 4 calls; Qwen parts free. (Estimated: US$0.0120.)" in body
    assert (
        body.startswith("# Dubai")
        and vault.read_note("decisions/2026-11-26-dubai.md")["frontmatter"]["title"] == "Dubai"
    )
