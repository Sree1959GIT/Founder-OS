"""M7a fix round 4 (founder re-test of 2026-11-26: F7c, F8c, F13b, F14, F15, F16, F17). Fakes only: no real key, no
network, no Ollama. The run.bat start path for F8c is in `test_m7a_fix_round4_start.py`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from loguru import logger

from app.agents.graph import AgentOrchestrator, _option_named
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentResult, AgentRunner, honest_status
from app.agents.specialists import SCOUT_LOCAL_NOTE, decision_key, scout_no_web_note, scout_without_web
from app.api.priorities import add_initiative, get_priorities, put_priorities
from app.engine.decision_science import ScoringRequest
from app.llm.ai_model import explain_failure, internet_works, is_timeout
from app.llm.base import LLMUnavailable, Message
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.vault.decisions import DecisionRecord
from tests.test_m6_gate import BAD_MEMO
from tests.test_m7a_fix_round3 import QuickCloud, _frame, _memo
from tests.test_voice_round2 import finished
from tests.test_voice_round8 import DUBAI, finance  # noqa: F401  (the fixture)


# --- F7c: a provider that does not answer in time is slow, not "your internet" -------------------------------------
def test_f7c_a_timeout_says_the_provider_is_slow_not_the_internet() -> None:
    code, line = explain_failure(TimeoutError(), "Gemini", "gemini-3.8-flash", 15)
    assert code == "slow"
    assert line == "Gemini didn't answer in 15 seconds. Google may be slow or limiting your key. Try again later."
    # The HTTP client's own read timeout is the same thing.
    read = LLMUnavailable("gemini not reachable (ReadTimeout: timed out)", network=True)
    assert is_timeout(read) and explain_failure(read, "Gemini", "m", 15)[0] == "slow"


def test_f7c_the_internet_is_named_only_when_no_provider_answers() -> None:
    refused = LLMUnavailable("gemini not reachable (ConnectError: refused)", network=True)
    assert not is_timeout(refused)
    code, line = explain_failure(refused, "Gemini", "m", 15, internet_ok=True)
    assert code == "unreachable" and "internet is fine" in line and "Check your internet" not in line
    assert "Check your internet connection" in explain_failure(refused, "Gemini", "m", 15)[1]


async def test_f7c_the_internet_check_asks_the_other_providers() -> None:
    asked: list[str] = []

    def groq_answers(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.host)
        if request.url.host == "api.groq.com":
            return httpx.Response(401)  # any answer means the connection works
        raise httpx.ConnectError("refused", request=request)

    assert await internet_works("gemini", transport=httpx.MockTransport(groq_answers)) is True
    assert "generativelanguage.googleapis.com" not in asked  # not the provider that failed

    def nothing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    assert await internet_works("gemini", transport=httpx.MockTransport(nothing)) is False


# --- F8c: every slow check says what it found in the backend window ---------------------------------------------------
async def test_f8c_each_slow_check_is_logged() -> None:
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message).strip()), format="{message}", level="INFO")
    try:
        router = LLMRouter(FakeProvider(["qwen answer"]), QuickCloud(0.08), cloud_allowed=True)
        bus = __import__("app.agents.events", fromlist=["EventBus"]).EventBus()
        runner = AgentRunner(router, bus, "run_log", lambda _aid: None)  # type: ignore[arg-type,return-value]
        runner.go_local, runner.slow_after_s, runner.slow_min_s = asyncio.Event(), 0.2, 0.0
        inst = AgentInstance(type="people_ops", name="People & Ops", brief="b", is_cloud=True, provider="groq")
        spec = REGISTRY["people_ops"]
        for _ in range(3):
            await runner._complete(spec, inst, [Message.user("q")], None)
        # A runner with no way to switch says why it does not check.
        plain = AgentRunner(router, bus, "run_log", lambda _aid: None)  # type: ignore[arg-type,return-value]
        await plain._complete(spec, inst, [Message.user("q")], None)
    finally:
        logger.remove(sink)
    checks = [line for line in lines if line.startswith("Slow check: People & Ops")]
    assert any(line.endswith("of 0 s -> not yet") for line in checks), checks
    assert any(line.endswith("-> offer sent") for line in checks), checks
    assert "Slow check: People & Ops skipped (no way to switch for this run)" in checks


# --- F13b: the answer, the frame card and the memo show one proposal --------------------------------------------------
def test_f13b_option_names_match_ignoring_case_and_spacing() -> None:
    names = {"Travel-led pilot", "Partner or distributor"}
    assert _option_named("Partner or Distributor", names) == "Partner or distributor"
    assert _option_named("  partner  or distributor ", names) == "Partner or distributor"
    assert _option_named("Something else", names) == ""


def test_f13b_a_follow_up_with_no_frame_carries_the_open_decisions_frame() -> None:
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    earlier = SimpleNamespace(result=SimpleNamespace(decision_frame=_frame()))
    orchestrator.runs = {"run_1": earlier}  # type: ignore[dict-item]
    memo = AgentResult(agent_id="m", type="memo_writer", name="Memo Writer", brief="b")
    memo.memo = _memo("partner or distributor")
    frame, before = orchestrator._follow_proposal(SimpleNamespace(), None, [memo])  # type: ignore[arg-type]
    assert frame is not None and frame.default_option == "Partner or distributor" and before == "Travel-led pilot"


def _lane(finance: Any, tmp_path: Path, chosen: str, title: str) -> Any:  # noqa: F811
    from app.agents.events import EventBus
    from app.agents.tools import ToolContext
    from app.conversation.manager import ConversationManager
    from app.decision.base import DecisionService, FakeDecisionProvider
    from tests.test_past_decisions import make_vault

    vault = make_vault(tmp_path / "vault")
    memo = {**BAD_MEMO, "chosen": chosen, "title": title, "decision": "", "why_chosen": "Smaller step.", "options": []}

    def reply(messages: Any, tools: Any, schema: Any) -> str:
        wants_memo = isinstance(schema, dict) and "chosen" in (schema.get("properties") or {})
        return json.dumps(memo) if wants_memo else "What would you cut first?"

    orch = AgentOrchestrator(
        LLMRouter(FakeProvider(default=reply)),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, vault, aid),
        approval_policy="never",
        approval_timeout_s=5,
    )
    return ConversationManager(orch), vault, memo


async def test_f13b_the_answer_the_frame_and_the_memo_agree(finance: Any, tmp_path: Path) -> None:  # noqa: F811
    manager, vault, _memo_reply = _lane(finance, tmp_path, "Partner or Distributor", "Dubai Market Entry via Partner")
    first = await manager.turn(None, DUBAI)
    one = await finished(manager, first.run_id)
    assert one.decision_frame.default_option == "Travel-led pilot"  # code's first pick, no memo yet
    record = await manager.turn(first.session_id, "Write the decision memo.")
    two = await finished(manager, record.run_id)
    assert two.memo is not None and two.memo.chosen == "Partner or distributor"
    assert two.decision_frame.default_option == "Partner or distributor"
    assert two.answer.startswith(
        "With Partner or distributor the runway effect is smaller, so I now propose Partner or distributor"
    )
    assert "Proposed: Partner or distributor" in two.answer and "Proposed: Travel-led pilot" not in two.answer
    text = (vault.vault.root / two.memo.path).read_text(encoding="utf-8")
    assert "proposed_option: Partner or distributor" in text


# --- F14: one Prioritisation Matrix entry per open decision -----------------------------------------------------------
def test_f14_a_new_memo_for_the_same_decision_updates_its_entry(tmp_path: Path) -> None:
    from tests.test_past_decisions import make_vault

    vault = make_vault(tmp_path / "vault")
    key = decision_key(_frame())
    assert key == "new_office:dubai office"
    assert add_initiative(
        vault,
        "Dubai Market Entry via Partner or Distributor: Partner or distributor",
        decision=key,
        memo="decisions/2026-11-26-dubai-market-entry.md",
    )
    view = get_priorities(vault)
    # The founder places it on the matrix; that score must survive the next memo.
    options = view["options"]
    options[0]["scores"] = {c["name"]: 5.0 for c in view["criteria"]}
    put_priorities(ScoringRequest(criteria=view["criteria"], options=options), vault)
    assert add_initiative(
        vault,
        "Open Dubai via Partner or Distributor: Partner or distributor",
        decision=key,
        memo="decisions/2026-11-26-open-dubai.md",
    )
    after = get_priorities(vault)["options"]
    assert len(after) == 1
    assert after[0]["name"] == "Open Dubai via Partner or Distributor: Partner or distributor"
    assert after[0]["memo"] == "decisions/2026-11-26-open-dubai.md" and set(after[0]["scores"].values()) == {5.0}
    # Another decision still gets its own entry.
    assert add_initiative(vault, "Hire two engineers", decision="hire:engineers")
    assert len(get_priorities(vault)["options"]) == 2


async def test_f14_two_memos_for_one_decision_leave_one_entry(finance: Any, tmp_path: Path) -> None:  # noqa: F811
    manager, vault, memo = _lane(finance, tmp_path, "Partner or distributor", "Dubai Market Entry via Partner")
    first = await manager.turn(None, DUBAI)
    await finished(manager, first.run_id)
    await finished(manager, (await manager.turn(first.session_id, "Write the decision memo.")).run_id)
    memo["title"] = "Open Dubai via Partner or Distributor"
    again = await manager.turn(first.session_id, "Record the decision on the Dubai office.")
    latest = await finished(manager, again.run_id)
    entries = get_priorities(vault)["options"]
    assert len(entries) == 1 and entries[0]["name"].startswith("Open Dubai via Partner or Distributor")
    assert entries[0]["memo"] == latest.memo.path


# --- F15: a proposal is never called a decision -----------------------------------------------------------------------
def _proposed() -> DecisionRecord:
    return DecisionRecord(
        path="decisions/2026-11-26-dubai-market-entry.md", title="Dubai Market Entry", status="proposed"
    )


def test_f15_a_proposed_memo_is_reported_as_proposed() -> None:
    text = (
        "The earlier memo was decided 2026-11-26 and proposes a partner [decisions/2026-11-26-dubai-market-entry.md]."
    )
    fixed = honest_status(text, [_proposed()])
    assert "decided 2026-11-26" not in fixed and "was proposed on 2026-11-26 (not decided yet)" in fixed
    assert honest_status("It was already decided on 2026-11-26.", [_proposed()]) == (
        "It was proposed on 2026-11-26 (not decided yet)."
    )
    decided = DecisionRecord(path="decisions/hire.md", title="Hire", status="decided", decided="2026-11-26")
    assert honest_status("Decided 2026-11-26.", [decided, _proposed()]) == "Decided 2026-11-26."


def test_f15_the_librarian_note_never_adds_a_decision_date_to_a_proposal() -> None:
    from app.agents.runtime import decision_note

    record = _proposed().model_copy(update={"decided": "2026-11-26"})
    note = decision_note("Dubai Market Entry is on record.", record, needs_path=False, lead="On record:")
    assert "decided 2026-11-26" not in note and "status proposed" in note


# --- F16: the real reason there was no web research -------------------------------------------------------------------
def test_f16_the_scout_names_the_real_reason() -> None:
    assert scout_no_web_note(cloud_on=False) == SCOUT_LOCAL_NOTE
    assert scout_no_web_note(cloud_on=True, provider="Groq") == (
        "Your AI provider (Groq) has no web search, so this comes from your vault only."
    )
    assert "Qwen on our server" in scout_no_web_note(cloud_on=True, provider="Groq", ran_local=True)
    text = scout_without_web("Dubai is busy.", set(), scout_no_web_note(cloud_on=True, provider="Groq"))
    assert "cloud is off" not in text and "Your AI provider (Groq) has no web search" in text


def test_f16_the_runner_says_groq_when_it_ran_on_groq() -> None:
    groq = FakeProvider(name="groq", is_cloud=True)  # FakeProvider has no web search, like Groq
    runner = AgentRunner(LLMRouter(FakeProvider(), groq, cloud_allowed=True), None, "r", lambda _a: None)  # type: ignore[arg-type]
    assert runner._no_web_note(REGISTRY["market_scout"]).startswith("Your AI provider (Groq) has no web search")
    off = AgentRunner(LLMRouter(FakeProvider(), groq, cloud_allowed=False), None, "r", lambda _a: None)  # type: ignore[arg-type]
    assert off._no_web_note(REGISTRY["market_scout"]) == SCOUT_LOCAL_NOTE


# --- F17: one waiting line per agent ---------------------------------------------------------------------------------
async def test_f17_one_waiting_line_per_agent(finance: Any) -> None:  # noqa: F811
    from tests.test_voice_round2 import lane

    cloud = FakeProvider(default=lambda m, t, s: "What would you cut first?", name="groq", is_cloud=True)
    manager = lane(finance)
    manager.orchestrator.router.cloud, manager.orchestrator.router.cloud_allowed = cloud, True
    first = await manager.turn(None, DUBAI)
    session = manager.sessions[first.session_id]
    await finished(manager, first.run_id)
    waiting = [line for line in session.narration if line.endswith("is waiting for a cloud model.")]
    assert waiting, session.narration  # the cloud agents did wait
    assert len(waiting) == len(set(waiting)), waiting  # but each is said once


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def offline(*_a: Any, **_k: Any) -> bool:
        return False

    monkeypatch.setattr("app.api.ai_model.internet_works", offline)
