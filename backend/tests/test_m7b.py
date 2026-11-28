"""M7b backend parts (founder F19): a cloud call that falls back to Qwen is said, and only real cloud calls cost."""

from __future__ import annotations

from typing import Any

from app.agents.events import EventBus
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentResult, AgentRunner, fallback_sentence
from app.llm.base import Completion, LLMError, LLMProvider, LLMUnavailable, Message, ToolSpec
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter, fallback_reason
from app.llm.spend import spend_of


class LimitedCloud(LLMProvider):
    """Groq after its free 8,000 tokens a minute ran out: every call is a 429."""

    name = "groq"
    model = "openai/gpt-oss-120b"
    is_cloud = True

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        raise LLMError("groq HTTP 429", status=429, detail="rate limit reached: tokens per minute")


def test_f19_the_reason_is_named_from_the_error() -> None:
    assert fallback_reason(LLMError("x", status=429)) == "rate_limit"
    assert fallback_reason(LLMError("x", status=503)) == "busy"
    assert fallback_reason(LLMUnavailable("x", network=True)) == "unreachable"
    assert fallback_reason(LLMError("bad json")) == "error"
    assert (
        fallback_sentence("groq", "slow", "People & Ops")
        == "Groq was slow and you chose Qwen, so People & Ops finished on Qwen on our server."
    )
    assert (
        fallback_sentence("groq", "rate_limit", "People & Ops")
        == "Groq hit its per-minute limit, so People & Ops finished on Qwen on our server."
    )


async def test_f19_a_429_fallback_is_said_once_and_costs_nothing() -> None:
    bus = EventBus()
    router = LLMRouter(FakeProvider(["qwen answer"]), LimitedCloud(), cloud_allowed=True)
    runner = AgentRunner(router, bus, "run_429", lambda _aid: None)  # type: ignore[arg-type,return-value]
    inst = AgentInstance(type="people_ops", name="People & Ops", brief="b", is_cloud=True, provider="groq")
    result = AgentResult(agent_id=inst.id, type="people_ops", name=inst.name, brief="b")
    for _ in range(3):
        completion = await runner._complete(REGISTRY["people_ops"], inst, [Message.user("q")], None)
        assert completion.fallback_from == "groq" and completion.fallback_reason == "rate_limit"
        runner._account(result, completion, inst)
    said = [e for e in bus.history("run_429") if e.type == "agent.fallback"]
    assert len(said) == 1
    assert said[0].data["text"] == "Groq hit its per-minute limit, so People & Ops finished on Qwen on our server."
    assert said[0].data["provider"] == "Groq" and said[0].data["reason"] == "rate_limit"
    # Only real cloud calls are counted: the failed 429s are not, and the Qwen answers are free.
    assert result.cloud_calls == {} and result.local_calls == 3
    spend = spend_of([result])
    assert not spend.cloud_used and spend.usd == 0.0
    assert spend.sentence("INR", 84.0) == "This decision cost nothing: all of it ran on Qwen on our server."


async def test_f19_the_advisor_line_is_the_sentence() -> None:
    from app.agents.events import AgentEvent
    from app.conversation.manager import ConversationManager

    manager = ConversationManager.__new__(ConversationManager)
    manager._agent_name = lambda _run, _agent: "People & Ops"  # type: ignore[method-assign]
    event = AgentEvent(
        seq=1, type="agent.fallback", run_id="r", agent_id="a", data={"text": "Groq hit its per-minute limit, so …"}
    )
    assert manager._line_for("r", event) == "Groq hit its per-minute limit, so …"


# --- F18: one memo per open decision; earlier versions are kept outside the vault ---------------------------------
def _memo_ctx(tmp_path: Any) -> Any:
    from types import SimpleNamespace

    from app.config import Settings
    from tests.test_past_decisions import make_vault

    vault = make_vault(tmp_path / "vault")
    vault.settings = Settings(data_dir=tmp_path / "data")
    vault.workspace_id = "default"
    return SimpleNamespace(vault=vault, finance=None)


def test_f18_a_new_memo_for_the_same_decision_replaces_it_and_keeps_the_old_one(tmp_path: Any) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.agents.specialists import MemoDraft, memo_versions_dir, write_memo
    from app.api import vault as vault_api
    from app.deps import get_vault
    from tests.test_m7a_fix_round3 import _frame
    from tests.test_specialists import GOOD_MEMO

    ctx = _memo_ctx(tmp_path)
    frame = _frame()
    draft = MemoDraft.model_validate(GOOD_MEMO)
    first, _ = write_memo(ctx, draft, [], verified=True, agent_id="m1", frame=frame)
    second_draft = draft.model_copy(update={"chosen": "Partner or distributor"})
    second, _ = write_memo(ctx, second_draft, [], verified=True, agent_id="m2", frame=frame)
    assert first.path == second.path and not second.path.endswith("-2.md")
    note = ctx.vault.vault.read_note(second.path)
    assert note["frontmatter"]["proposed_option"] == "Partner or distributor"
    assert note["frontmatter"]["decision"] == "new_office:dubai office" and note["frontmatter"]["written_at"]
    root = memo_versions_dir(ctx)
    assert root is not None and not str(root).startswith(str(tmp_path / "vault"))
    from app.vault.memo_versions import list_versions, read_version

    versions = list_versions(root, second.path)
    assert len(versions) == 1 and versions[0]["proposed_option"] == draft.chosen
    assert read_version(root, second.path, versions[0]["id"])["frontmatter"]["proposed_option"] == draft.chosen
    # Another decision still gets its own memo.
    other = frame.model_copy(update={"subject": "Riyadh office"})
    third, _ = write_memo(ctx, draft, [], verified=True, agent_id="m3", frame=other)
    assert third.path != second.path or third.path.endswith("-2.md")
    assert len(list_versions(root, second.path)) == 1
    # The API lists and reads them; a path outside decisions/ or a made-up id is refused.
    app = FastAPI()
    app.include_router(vault_api.router, prefix="/api")
    app.dependency_overrides[get_vault] = lambda: ctx.vault
    client = TestClient(app)
    listed = client.get("/api/memos/versions", params={"path": second.path}).json()
    assert [v["id"] for v in listed["versions"]] == [versions[0]["id"]]
    got = client.get(f"/api/memos/versions/{versions[0]['id']}", params={"path": second.path})
    assert got.status_code == 200 and got.json()["frontmatter"]["proposed_option"] == draft.chosen
    assert client.get("/api/memos/versions", params={"path": "notes/x.md"}).status_code == 400
    assert client.get("/api/memos/versions/../../x", params={"path": second.path}).status_code in (400, 404)


def test_f18_a_rewritten_memo_replaces_its_open_predictions(tmp_path: Any) -> None:
    from types import SimpleNamespace

    from app.agents.specialists import MemoDraft, write_memo
    from app.engine.calibration import CalibrationStore
    from tests.test_m7a_fix_round3 import _frame
    from tests.test_specialists import GOOD_MEMO

    ctx = _memo_ctx(tmp_path)
    ctx.finance = SimpleNamespace(calibration=CalibrationStore(tmp_path / "cal"))
    draft = MemoDraft.model_validate(GOOD_MEMO)
    first, _ = write_memo(ctx, draft, [], verified=True, agent_id="m1", frame=_frame())
    once = [p for p in ctx.finance.calibration.list() if p.decision == first.path]
    assert once
    ctx.finance.calibration.resolve(once[0].id, True)  # a scored prediction stays
    write_memo(ctx, draft, [], verified=True, agent_id="m2", frame=_frame())
    after = [p for p in ctx.finance.calibration.list() if p.decision == first.path]
    assert len(after) == len(once) + 1  # the resolved one, plus the new memo's open ones
    assert sum(p.outcome is not None for p in after) == 1


async def test_f19_the_memo_writer_says_its_switch_too() -> None:
    from app.agents.specialists import MemoDraft  # noqa: F401  (the memo schema the draft uses)

    bus = EventBus()
    router = LLMRouter(FakeProvider(["{}"]), LimitedCloud(), cloud_allowed=True)
    runner = AgentRunner(router, bus, "run_memo", lambda _aid: None)  # type: ignore[arg-type,return-value]
    inst = AgentInstance(type="memo_writer", name="Memo Writer", brief="b", is_cloud=True, provider="groq")
    result = AgentResult(agent_id=inst.id, type="memo_writer", name=inst.name, brief="b")
    await runner._draft_memo(REGISTRY["memo_writer"], [Message.user("q")], "q", result, inst=inst)
    said = [e for e in bus.history("run_memo") if e.type == "agent.fallback"]
    assert len(said) == 1 and said[0].data["text"].endswith("so Memo Writer finished on Qwen on our server.")
