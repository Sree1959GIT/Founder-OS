"""M6 Major gate fix round (founder run 2026-11-18/19, fresh copy): D1 to D4."""

from __future__ import annotations

from typing import Any

from app.agents.decision_frame import parse_inputs
from app.conversation.classifier import by_rules
from tests.test_voice_round2 import finished, lane
from tests.test_voice_round8 import answered, finance  # noqa: F401  (the fixture)

WHAT_IF = "What if we raise prices 10% and churn goes up two points?"


# --- D2: a what-if is its own question, and both levers are applied --------------------------------------------------
def test_churn_points_in_words_are_read() -> None:
    assert parse_inputs(WHAT_IF, "pricing") == {"price": 10.0, "churn": 2.0}


async def test_a_what_if_after_a_decision_is_a_new_question_not_a_change(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)  # the Dubai decision is open
    what_if = await manager.turn(first.session_id, WHAT_IF)
    assert what_if.started_run and "already" not in what_if.reply and what_if.amendment_id is None
    run = await finished(manager, what_if.run_id)
    frame = run.decision_frame
    assert frame is not None and frame.type == "pricing"
    items = {i.key: i for i in frame.cost_model.items}
    assert items["price"].base == 10.0 and items["churn"].base == 2.0  # both levers, the founder's figures
    assert items["price"].basis == items["churn"].basis == "founder"


async def test_the_same_what_if_said_again_while_it_runs_is_not_already_in_it(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await manager.turn(None, WHAT_IF)
    again = await manager.turn(first.session_id, WHAT_IF)
    assert "already assuming" not in again.reply and "Nothing to restart" not in again.reply
    assert again.amendment_id is None
    await finished(manager, first.run_id)


async def test_a_what_if_with_the_decisions_own_numbers_is_still_a_change(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    change = await manager.turn(first.session_id, "What if we hired three instead?")
    assert change.amendment_id is not None and not change.started_run


# --- D3: stop phrases stop and listen ---------------------------------------------------------------------------------
def test_stop_phrases_are_stops() -> None:
    for said in ("Wait, stop there.", "Stop there.", "Wait.", "Hold on.", "Hang on a second.", "Wait, wait."):
        assert by_rules(said) == "stop", said
    assert by_rules("Wait, assume three hires.") == "amendment"
    assert by_rules("Stop hiring contractors?") != "stop"


async def test_wait_stop_there_over_the_summary_is_never_a_change(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    stop = await manager.turn(first.session_id, "Wait, stop there.", spoken=True)
    assert stop.reply == "" and stop.amendment_id is None and not stop.started_run
    session = manager.sessions[first.session_id]
    assert not [a for a in session.amendments.values() if a.status == "offered"]


async def test_the_what_if_answer_says_both_levers(finance: Any) -> None:  # noqa: F811
    from app.voice.spoken import summarise

    manager = lane(finance)
    first = await manager.turn(None, WHAT_IF)
    run = await finished(manager, first.run_id)
    assert "+10 % with churn +2 pts" in run.answer
    assert "+10 % with churn +2 pts" in " ".join(summarise(run).lead)


# --- D1: the memo is built by code from the open decision's latest frame ----------------------------------------------
BAD_MEMO = {
    "title": "Open a Dubai office",
    "chosen": "Travel-led pilot",
    "why_chosen": "It aligns with the goal to extend runway.",
    "context": "You asked about Dubai.",
    "decision": "Proposed: Travel-led pilot. It aligns with the goal to extend runway.",
    "options": [{"name": "Travel-led pilot", "note": "Hire two SDRs to sell from home."}],
    "assumptions": [],
    "predictions": [],
    "kill_criteria": [],
}


def memo_lane(finance: Any, tmp_path: Any) -> Any:  # noqa: F811
    import json

    from app.agents.events import EventBus
    from app.agents.graph import AgentOrchestrator
    from app.agents.tools import ToolContext
    from app.conversation.manager import ConversationManager
    from app.decision.base import DecisionService, FakeDecisionProvider
    from app.llm.fake import FakeProvider
    from app.llm.router import LLMRouter
    from tests.test_past_decisions import make_vault

    vault = make_vault(tmp_path / "vault")

    def reply(messages: Any, tools: Any, schema: Any) -> str:
        wants_memo = isinstance(schema, dict) and "chosen" in (schema.get("properties") or {})
        return json.dumps(BAD_MEMO) if wants_memo else "What would you cut first?"

    orch = AgentOrchestrator(
        LLMRouter(FakeProvider(default=reply)),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, vault, aid),
        approval_policy="never",
        approval_timeout_s=5,
    )
    return ConversationManager(orch), vault


async def test_record_the_decision_writes_the_memo_from_the_latest_frame(finance: Any, tmp_path: Any) -> None:  # noqa: F811
    manager, vault = memo_lane(finance, tmp_path)
    first = await answered(manager)
    change = await manager.turn(first.session_id, "Assume three hires.")
    yes = await manager.turn(first.session_id, "yes")
    assert yes.started_run and change.amendment_id
    amended = await finished(manager, yes.run_id)
    hires = next(i for i in amended.decision_frame.cost_model.items if i.key == "hires")
    assert hires.base == 3 and hires.basis == "founder"

    record = await manager.turn(first.session_id, "Record the decision on the Dubai office.")
    assert record.started_run
    run = manager.orchestrator.runs[record.run_id or ""]
    assert [i.type for i in run.plan_override.team].count("memo_writer") == 1
    result = await finished(manager, record.run_id)
    memo = next(a for a in result.agents if a.type == "memo_writer").memo
    assert memo is not None
    text = (vault.vault.root / memo.path).read_text(encoding="utf-8")
    cost = text.split("## Cost model", 1)[1].split("##", 1)[0]
    assert "Not modelled" not in cost and "3 people (you said)" in cost
    options = text.split("## Options", 1)[1].split("##", 1)[0]
    assert "SDR" not in text and "Travel-led pilot" in options and "Full office" in options
    open_numbers = text.split("## Open numbers to confirm", 1)[1].split("##", 1)[0]
    assert "None." not in open_numbers and open_numbers.count("Give me the real figure.") == 4
    assert "aligns with the goal" not in text
    # the Prioritisation Matrix gets the decision's entry, unscored
    from app.api.priorities import get_priorities

    names = [o["name"] for o in get_priorities(vault)["options"]]
    assert any("Travel-led pilot" in n for n in names)


# --- D4: a source must be a file in this vault; one Qdrant collection per install -------------------------------------
def test_two_installs_never_share_a_collection(tmp_path: Any) -> None:
    from app.vault.service import collection_name

    one = collection_name("default", "ollama:nomic-embed-text", tmp_path / "a" / "vault" / "default")
    two = collection_name("default", "ollama:nomic-embed-text", tmp_path / "b" / "vault" / "default")
    assert one != two and one.startswith("founderos_default_")
    assert one == collection_name("default", "ollama:nomic-embed-text", tmp_path / "a" / "vault" / "default")


def test_a_passage_from_a_file_not_in_this_vault_is_no_source() -> None:
    from app.agents.sources import Evidence

    memo = "decisions/2026-11-06-open-dubai-office.md"
    evidence = Evidence(passages={memo: [2.0]}, exists=lambda path: path != memo)
    assert not evidence.resolves(memo)
    assert evidence.missing_sources(f"You decided this before [{memo}].") == [memo]
    assert Evidence(passages={memo: [2.0]}, exists=lambda path: True).resolves(memo)


def test_citations_keep_only_files_in_this_vault() -> None:
    from app.agents.events import Citation
    from app.agents.runtime import AgentResult, _keep_used_sources

    gone, here = "decisions/2026-11-06-open-dubai-office.md", "decisions/2026-09-hire-two-sdrs.md"
    result = AgentResult(agent_id="a", type="librarian", name="Librarian", brief="b")
    result.retrieved = [Citation(path=gone, heading="", chunk_id="c1"), Citation(path=here, heading="", chunk_id="c2")]
    result.text = f"See [{gone}] and [{here}]."
    _keep_used_sources(result, lambda path: path == here)
    assert [c.path for c in result.citations] == [here]
