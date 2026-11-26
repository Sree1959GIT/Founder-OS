"""M7a fix round 3 (founder F4b, F7b, F8b, F12b, F13, 2026-11-26). Fakes only: no real key, no network, no Ollama.

F4b Remove key turns cloud off (saved); F7b the 15 s running out after a 429/503 is still "busy", a used-up Gemini free
quota is said as such; F8b the slow check is for the agent as a whole, and the env var reaches the backend run.bat
starts; F12b costs in the member's currency everywhere, US$ to 2 decimals; F13 one proposal on screen, and why.
"""

from __future__ import annotations

import asyncio
import functools
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.api.ai_model as ai_api
from app.agents.decision_frame import DecisionFrame, GoalCheck, OptionCost
from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentResult, AgentRunner, proposal_change_line
from app.agents.setup import build_orchestrator
from app.agents.specialists import MemoRef
from app.config import Settings
from app.llm.ai_model import build_provider, explain_failure, is_busy, is_free_limit, list_models, retry_when_busy
from app.llm.base import Completion, LLMError, LLMProvider, LLMUnavailable, Message, ToolSpec
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.llm.spend import usd_text
from app.main import create_app

SECRET = Fernet.generate_key().decode()
AQ_KEY = "AQ.Ab8RN6LfakeFAKEfake-0000000000000000"
GEMINI_LIST = {"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]}]}
# What Google answers when the free tier is used up (shortened): a 429 that asking again in a second does not help.
FREE_TIER_429 = {
    "error": {
        "code": 429,
        "message": "You exceeded your current quota, please check your plan and billing details. Quota exceeded for "
        "metric: generativelanguage.googleapis.com/generate_content_free_tier_requests",
        "status": "RESOURCE_EXHAUSTED",
    }
}


class Google:
    """A fake Gemini: the model list always answers; each model call answers with the next queued reply."""

    def __init__(self) -> None:
        self.posts: list[tuple[int, dict[str, Any]]] = []
        self.seen = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=GEMINI_LIST)
        self.seen += 1
        status, body = self.posts.pop(0) if self.posts else (200, {})
        if status != 200:
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> Google:
    fake = Google()
    transport = httpx.MockTransport(fake.handle)
    monkeypatch.setattr(ai_api, "build_provider", functools.partial(build_provider, transport=transport))
    monkeypatch.setattr(ai_api, "list_models", functools.partial(list_models, transport=transport))
    waits: list[float] = []

    async def instant(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("app.llm.ai_model._sleep", instant)
    fake.waits = waits  # type: ignore[attr-defined]
    return fake


@pytest.fixture
def secured(settings: Settings) -> Settings:
    return settings.model_copy(update={"founderos_secret_key": SecretStr(SECRET)})


@pytest.fixture
def client(secured: Settings) -> Any:
    with TestClient(create_app(secured)) as c:
        yield c


def _test(client: TestClient, **body: Any) -> dict[str, Any]:
    return client.post("/api/settings/ai-model/test", json=body).json()  # type: ignore[no-any-return]


# --- F4b: Remove key turns cloud off, saved, so the box greys out again ----------------------------------------------
def test_f4b_remove_key_turns_cloud_off_and_saves_it(client: TestClient, google: Google, secured: Settings) -> None:
    assert _test(client, api_key=AQ_KEY)["ok"] is True
    assert client.get("/api/settings").json()["cloud_allowed"] is True
    client.delete("/api/settings/ai-model/key")
    view = client.get("/api/settings").json()
    assert view["cloud_allowed"] is False and view["cloud_usable"] is False  # greyed, with "Test and save a key"
    assert client.app.state.orchestrator.router.cloud_allowed is False  # type: ignore[attr-defined]
    assert '"cloud_allowed": false' in (secured.workspace_data_dir() / "ui_settings.json").read_text(encoding="utf-8")
    health = client.get("/api/health").json()
    assert health.get("ai_model") in (None, "") or "cloud" not in str(health.get("ai_model")).lower()
    refused = client.put("/api/settings", json={"cloud_allowed": True})
    assert refused.status_code == 422  # cannot be ticked on again until a key passes


def test_f4b_after_remove_an_env_key_no_longer_counts(secured: Settings, google: Google) -> None:
    # Once the card was used the router ignores `.env` keys, so they cannot keep the box enabled either.
    with TestClient(create_app(secured.model_copy(update={"gemini_api_key": SecretStr("k")}))) as client:
        assert _test(client, api_key=AQ_KEY)["ok"] is True
        client.delete("/api/settings/ai-model/key")
        view = client.get("/api/settings").json()
        assert view["cloud_allowed"] is False and view["cloud_usable"] is False


# --- F7b: the time running out after a 429/503 is "busy", never "check your internet" --------------------------------
async def test_f7b_a_timeout_after_a_busy_answer_is_still_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.llm.ai_model._sleep", instant)
    answers: list[BaseException] = [LLMUnavailable("x", status=429, detail="Too many requests"), TimeoutError()]

    async def attempt(_left: float) -> None:
        raise answers.pop(0)

    deadline = asyncio.get_running_loop().time() + 15
    with pytest.raises(LLMError) as raised:
        await retry_when_busy(attempt, deadline, 2)
    assert raised.value.status == 429 and is_busy(raised.value)
    code, line = explain_failure(raised.value, "Gemini", "m", 15, key_ok=True)
    assert code == "busy" and "internet" not in line
    assert line == "Gemini is busy right now (Google error 429). Your key is fine. Try again in a minute."


async def test_f7b_a_network_error_after_a_503_is_still_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.llm.ai_model._sleep", instant)
    answers: list[BaseException] = [
        LLMUnavailable("x", status=503, detail="overloaded"),
        LLMUnavailable("reset", network=True),
    ]

    async def attempt(_left: float) -> None:
        raise answers.pop(0)

    with pytest.raises(LLMError) as raised:
        await retry_when_busy(attempt, asyncio.get_running_loop().time() + 15, 2)
    assert raised.value.status == 503 and explain_failure(raised.value, "Gemini", "m", 15)[0] == "busy"


async def test_f7b_a_timeout_with_no_busy_answer_before_is_still_unreachable() -> None:
    async def attempt(_left: float) -> None:
        raise TimeoutError

    with pytest.raises(TimeoutError):
        await retry_when_busy(attempt, asyncio.get_running_loop().time() + 15, 2)


def test_f7b_used_up_free_quota_is_said_plainly_and_keeps_the_green_chip(client: TestClient, google: Google) -> None:
    assert _test(client, api_key=AQ_KEY)["ok"] is True
    google.posts = [(429, FREE_TIER_429)]
    before = google.seen
    body = _test(client, preset="gemini", model="gemini-3.8-flash")  # Test again with the saved key
    assert body["ok"] is False and body["code"] == "free_limit"
    assert body["message"] == (
        "Your Gemini key has reached its free limit for now. Try again later, or add billing in Google AI Studio."
    )
    assert google.seen - before == 1 and google.waits == []  # type: ignore[attr-defined]  # not asked again
    assert body["view"]["in_use"]["verified"] is True  # the green chip stays


def test_f7b_a_busy_minute_is_not_the_free_limit() -> None:
    minute = LLMError("x", status=429, detail="Resource has been exhausted (e.g. check quota).")
    assert not is_free_limit(minute) and explain_failure(minute, "Gemini", "m", 15)[0] == "busy"
    quota = LLMError("x", status=429, detail='{"error": {"status": "RESOURCE_EXHAUSTED"}}')
    assert is_free_limit(quota) and explain_failure(quota, "Gemini", "m", 15)[0] == "free_limit"
    other = explain_failure(quota, "Groq", "m", 15)
    assert other[0] == "free_limit" and "Groq" in other[1] and "internet" not in other[1]


# --- F8b: the limit reaches the backend run.bat starts, and is for the agent as a whole ------------------------------
def test_f8b_the_powershell_env_var_beats_the_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # run.bat: `$env:CLOUD_SLOW_AFTER_S="3"` in PowerShell, then `start ... uvicorn --factory app.main:create_app`,
    # which inherits the variable; `.env` (copied from .env.example) still says 45 and 15.
    env_file = tmp_path / ".env"
    env_file.write_text("CLOUD_SLOW_AFTER_S=45\nCLOUD_SLOW_MIN_S=15\n", encoding="utf-8")
    monkeypatch.setenv("CLOUD_SLOW_AFTER_S", "3")
    monkeypatch.setenv("CLOUD_SLOW_MIN_S", "0")
    settings = Settings(_env_file=env_file, data_dir=tmp_path / "data", llm_provider="fake")  # type: ignore[call-arg]
    assert (settings.cloud_slow_after_s, settings.cloud_slow_min_s) == (3.0, 0.0)
    orchestrator = build_orchestrator(settings, SimpleNamespace(), SimpleNamespace())
    assert (orchestrator.slow_after_s, orchestrator.slow_min_s) == (3.0, 0.0)


async def test_f8b_each_agent_runner_gets_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    seen: dict[str, Any] = {}

    async def run(self: AgentRunner, *_args: Any) -> AgentResult:
        seen.update(after=self.slow_after_s, min=self.slow_min_s, switch=self.go_local)
        return AgentResult(agent_id="a", type="people_ops", name="People & Ops", brief="b")

    monkeypatch.setattr(AgentRunner, "run", run)
    orchestrator.router = LLMRouter(FakeProvider())
    orchestrator.bus, orchestrator.ctx_factory, orchestrator.max_steps = EventBus(), lambda _a: None, 2
    orchestrator.cloud_slots = orchestrator.local_slots = asyncio.Semaphore(2)
    orchestrator.slow_after_s, orchestrator.slow_min_s = 3.0, 0.0
    orchestrator.runs = {"run_1": SimpleNamespace(go_local={})}  # type: ignore[dict-item]
    inst = AgentInstance(type="people_ops", name="People & Ops", brief="b", is_cloud=True, provider="groq")
    state = {"run_id": "run_1", "message": "q", "results": [], "plan": SimpleNamespace(frame=None)}
    await orchestrator._in_a_slot(inst, state)  # type: ignore[arg-type]
    assert seen["after"] == 3.0 and seen["min"] == 0.0 and seen["switch"] is not None


class QuickCloud(LLMProvider):
    """Groq: every call answers quickly; an agent of several calls still takes long in all."""

    name = "groq"
    model = "openai/gpt-oss-120b"
    is_cloud = True

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        await asyncio.sleep(self.seconds)
        return Completion(text="cloud answer", provider=self.name, model=self.model)


async def test_f8b_an_agent_of_quick_calls_passes_the_limit_mid_run() -> None:
    bus = EventBus()
    router = LLMRouter(FakeProvider(["qwen answer"]), QuickCloud(0.08), cloud_allowed=True)
    runner = AgentRunner(router, bus, "run_groq", lambda _aid: None)  # type: ignore[arg-type,return-value]
    runner.go_local, runner.slow_after_s, runner.slow_min_s = asyncio.Event(), 0.2, 0.0  # "3 s", scaled down
    inst = AgentInstance(type="people_ops", name="People & Ops", brief="b", is_cloud=True, provider="groq")
    spec = REGISTRY["people_ops"]
    for _ in range(2):  # two quick calls: each well under the limit, 0.16 s in all
        assert (await runner._complete(spec, inst, [Message.user("q")], None)).text == "cloud answer"
    assert not [e for e in bus.history("run_groq") if e.type == "agent.slow"]
    # The third call passes the agent's limit while it is running: the Advisor is told, nothing switches.
    assert (await runner._complete(spec, inst, [Message.user("q")], None)).text == "cloud answer"
    slow = [e for e in bus.history("run_groq") if e.type == "agent.slow"]
    assert len(slow) == 1 and slow[0].data["reason"].startswith("Groq has taken 0 s so far (expected under 0 s)")
    assert runner.on_local is False
    await runner._complete(spec, inst, [Message.user("q")], None)  # one offer per agent
    assert len([e for e in bus.history("run_groq") if e.type == "agent.slow"]) == 1


async def test_f8b_the_ok_mid_run_switches_the_next_call_to_qwen() -> None:
    bus = EventBus()
    router = LLMRouter(FakeProvider(["qwen answer"]), QuickCloud(0.05), cloud_allowed=True)
    runner = AgentRunner(router, bus, "run_ok", lambda _aid: None)  # type: ignore[arg-type,return-value]
    runner.go_local, runner.slow_after_s, runner.slow_min_s = asyncio.Event(), 0.08, 0.0
    inst = AgentInstance(type="people_ops", name="People & Ops", brief="b", is_cloud=True, provider="groq")
    spec = REGISTRY["people_ops"]
    await runner._complete(spec, inst, [Message.user("q")], None)
    await runner._complete(spec, inst, [Message.user("q")], None)
    assert [e for e in bus.history("run_ok") if e.type == "agent.slow"]
    assert runner.go_local is not None
    runner.go_local.set()  # "Continue on Qwen on our server", clicked between two calls
    completion = await runner._complete(spec, inst, [Message.user("q")], None)
    assert completion.text == "qwen answer" and completion.fallback_from == "groq" and runner.on_local is True


# --- F12b: the member's currency everywhere; US$ only in small print, to 2 decimals -----------------------------------
def test_f12b_us_dollars_in_small_print_have_2_decimals() -> None:
    assert usd_text(0.2850) == "US$0.29"
    assert usd_text(0.24) == "US$0.24"
    assert usd_text(0.001) == "less than US$0.01"
    assert usd_text(0.0) == "US$0.00"


def test_f12b_the_run_cost_is_in_the_member_currency(settings: Settings) -> None:
    with TestClient(create_app(settings.model_copy(update={"auto_load_sample_data": True}))) as client:
        client.app.state.orchestrator.currency_rate = lambda: ("INR", 89.0)  # type: ignore[attr-defined]
        body = client.post("/api/chat", json={"message": "What's our runway?", "stream": False}).json()
        assert body["est_cost_usd"] == 0 and body["cost_shown"] == "free"  # all on Qwen

    from app.llm.spend import money

    assert money(0.285, "INR", 89.0) == "about ₹25"  # what the Activity header shows instead of "≈ $0.29"


# --- F13: one proposal on screen, and the Advisor says why it changed -------------------------------------------------
def _frame() -> DecisionFrame:
    return DecisionFrame(
        type="new_office",
        subject="Dubai office",
        options=[
            OptionCost(name="Full Dubai office", one_off=60000, monthly=25000, runway_change_months=-3.1, is_full=True),
            OptionCost(name="Travel-led pilot", one_off=5000, monthly=8000, runway_change_months=-1.2),
            OptionCost(name="Partner or distributor", one_off=2000, monthly=3000, runway_change_months=-0.4),
        ],
        default_option="Travel-led pilot",
        goals=[GoalCheck(goal="18 months of runway", status="moves_away", sentence="s")],
    )


def _memo(chosen: str) -> MemoRef:
    return MemoRef(
        path="decisions/dubai.md",
        title="Dubai",
        status="proposed",
        review_date="2027-01-15",
        chosen=chosen,
        predictions=[],
        kill_criteria=[],
        verified=True,
    )


def _orchestrator() -> AgentOrchestrator:
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.runs = {}
    return orchestrator


def test_f13_the_frame_marks_what_the_memo_proposes() -> None:
    result = AgentResult(agent_id="m", type="memo_writer", name="Memo Writer", brief="b")
    result.memo = _memo("Partner or distributor")
    run = SimpleNamespace()
    frame, before = _orchestrator()._follow_proposal(run, _frame(), [result])  # type: ignore[arg-type]
    assert frame is not None and frame.default_option == "Partner or distributor" and before == "Travel-led pilot"
    assert _frame().default_option == "Travel-led pilot"  # the plan's frame is copied, not changed in place


def test_f13_a_later_run_that_proposes_another_option_says_so() -> None:
    orchestrator = _orchestrator()
    earlier = SimpleNamespace(result=SimpleNamespace(decision_frame=_frame()))
    orchestrator.runs = {"run_1": earlier}  # type: ignore[dict-item]
    later = _frame().model_copy(update={"default_option": "Partner or distributor"})
    frame, before = orchestrator._follow_proposal(SimpleNamespace(), later, [])  # type: ignore[arg-type]
    assert frame is not None and frame.default_option == "Partner or distributor" and before == "Travel-led pilot"


def test_f13_nothing_changed_says_nothing() -> None:
    result = AgentResult(agent_id="m", type="memo_writer", name="Memo Writer", brief="b")
    result.memo = _memo("Travel-led pilot")
    frame, before = _orchestrator()._follow_proposal(SimpleNamespace(), _frame(), [result])  # type: ignore[arg-type]
    assert frame is not None and frame.default_option == "Travel-led pilot" and before == ""
    result.memo = _memo("Something not in the frame")
    assert _orchestrator()._follow_proposal(SimpleNamespace(), _frame(), [result])[1] == ""  # type: ignore[arg-type]


def test_f13_the_why_is_one_sentence_by_code_without_figures() -> None:
    line = proposal_change_line(_frame(), "Travel-led pilot", "Partner or distributor")
    assert line == (
        "With Partner or distributor the runway effect is smaller, so I now propose Partner or distributor "
        "instead of Travel-led pilot."
    )
    assert not any(ch.isdigit() for ch in line)
    back = proposal_change_line(_frame(), "Partner or distributor", "Full Dubai office")
    assert back == "Weighing the options again, I now propose Full Dubai office instead of Partner or distributor."
    assert proposal_change_line(_frame(), "Travel-led pilot", "Travel-led pilot") == ""
