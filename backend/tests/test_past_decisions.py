"""Founder feedback [M3a]: the Librarian missed a past decision on the same topic and cited what it did not use."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentRunner, Plan, advise, decision_covered, plan, rule_intent
from app.agents.tools import ToolContext, passage, run_tool
from app.agents.verifier import verify_numbers
from app.config import PROJECT_ROOT
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.chunking import ApproxTokenizer
from app.engine.embeddings import FakeEmbedder
from app.engine.hybrid_rag import HybridIndex, stem
from app.evals.vault_eval import EvalCase, check_live_reply, load_cases, run_offline, score
from app.llm.base import LLMUnavailable, ToolCall
from app.llm.fake import FakeProvider, schema_example
from app.llm.router import LLMRouter
from app.vault.decisions import DecisionRecord, build_record
from app.vault.manager import VaultManager
from app.vault.parsers import parse_markdown

SDR_PATH = "decisions/2026-09-hire-two-sdrs.md"
SDR_QUESTION = "Should we hire two more SDRs next quarter?"
KILL = "if qualified meetings per SDR stay under eight a month by December, pause the second seat"
# What the model said on the founder's PC.
BLIND_ANSWER = "No specific SDR performance metrics or conversion rates are available."


def make_vault(root: Path) -> Any:
    shutil.copytree(PROJECT_ROOT / "sample_data" / "vault", root)
    manager = VaultManager(root)
    index = HybridIndex(manager, FakeEmbedder(), None, ApproxTokenizer())
    index.refresh(dense=False)
    return SimpleNamespace(vault=manager, index=index, ensure_started=lambda: None, wait_ready=lambda: True)


@pytest.fixture
def vault(tmp_path: Path) -> Any:
    return make_vault(tmp_path / "vault")


def write_note(vault: Any, path: str, text: str) -> None:
    target = vault.vault.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    vault.index.refresh([path], dense=False)


def runner(provider: FakeProvider, vault: Any) -> AgentRunner:
    return AgentRunner(LLMRouter(provider), EventBus(), "run_test", lambda aid: ToolContext(None, vault, aid))


def librarian(brief: str = SDR_QUESTION) -> AgentInstance:
    return AgentInstance(type="librarian", name="Librarian", brief=brief, provider="fake")


# --- root cause 1: frontmatter never reached the chunks, the search results or read_note ---------------------------
def test_frontmatter_is_searchable_and_returned_with_the_result(vault: Any) -> None:
    results = vault.index.search("review date prediction", mode="bm25")["results"]
    top = next(r for r in results if r["path"] == SDR_PATH)
    assert "Review date: 2026-12-15" in top["text"] and "70% chance" in top["text"]
    assert top["metadata"]["status"] == "decided" and top["metadata"]["review_date"] == "2026-12-15"
    assert top["decision"].kill_criteria == [KILL]


def test_a_note_with_only_a_name_and_tags_gets_no_record_chunk(vault: Any) -> None:
    pricing = [p for p in vault.index._snapshot.parents.values() if p.path == "notes/pricing-strategy.md"]
    assert all(c.heading != "Record" for p in pricing for c in p.children)


async def test_read_note_returns_the_frontmatter(vault: Any) -> None:
    ctx = ToolContext(None, vault, "a")
    note = await run_tool("read_note", ctx, {"path": SDR_PATH}, REGISTRY["librarian"].tools)
    assert note.content["frontmatter"]["review_date"] == "2026-12-15"
    assert 70.0 in note.numbers  # the model may quote the prediction


# --- root cause 2: no stemming, so the Planner's "SDR" did not find "SDRs" -----------------------------------------
@pytest.mark.parametrize(
    ("word", "same_as"),
    [("SDRs", "sdr"), ("hiring", "hire"), ("hired", "hire"), ("prices", "pricing"), ("running", "run")],
)
def test_stemmer_joins_word_forms(word: str, same_as: str) -> None:
    assert stem(word.lower()) == stem(same_as)


@pytest.mark.parametrize("word", ["business", "analysis", "2026", "mrr"])
def test_stemmer_leaves_other_words_alone(word: str) -> None:
    assert stem(word) == word


def test_keyword_search_for_sdr_finds_every_note_on_sdrs(vault: Any) -> None:
    paths = {r["path"] for r in vault.index.search("SDR performance metrics", mode="bm25")["results"]}
    assert {SDR_PATH, "sources/board-update-2026-q3.md"} <= paths


def test_question_words_do_not_outrank_the_topic(vault: Any) -> None:
    results = vault.index.search("What do my notes say about annual prepayment?", k=2, mode="bm25")["results"]
    assert "notes/pricing-strategy.md" in {r["path"] for r in results}


# --- root cause 3: the 900-character cut hid matches at the end of a long note -------------------------------------
def test_passage_is_centred_on_the_match() -> None:
    text = "x" * 3000 + " the kill criterion is here " + "y" * 3000
    cut = passage(text, "the kill criterion is here", 1200)
    assert "the kill criterion is here" in cut and len(cut) == 1200
    assert passage("short", "short", 1200) == "short"
    assert passage("a" * 50, "not in the text", 10) == "a" * 10


async def test_a_match_at_the_end_of_a_long_note_reaches_the_model(vault: Any) -> None:
    filler = " ".join(f"Sentence number {i} about nothing at all." for i in range(60))
    write_note(vault, "notes/long.md", f"# Long\n\n{filler}\n\nThe zebra budget ends in spring.\n")
    ctx = ToolContext(None, vault, "a")
    found = await run_tool("search_vault", ctx, {"query": "zebra budget"}, REGISTRY["librarian"].tools)
    assert "zebra budget" in found.content["results"][0]["text"]


# --- decision records -----------------------------------------------------------------------------------------------
def record_for(path: str, text: str) -> DecisionRecord | None:
    return build_record(path, parse_markdown(text, "note"))


def test_record_of_the_sample_decision(vault: Any) -> None:
    record = vault.index.past_decisions(SDR_QUESTION, today=dt.date(2026, 11, 4))[0]
    assert record.path == SDR_PATH and record.status == "decided"
    assert record.decided == "2026-09-15" and record.review_date == "2026-12-15" and record.review_state == "upcoming"
    assert record.predictions == ["70% chance outbound pipeline grows by at least 30% within 90 days"]
    assert record.kill_criteria == [KILL] and record.decision.startswith("Hire two SDRs")
    summary = record.summary()
    for fact in ("status decided", "2026-09-15", "2026-12-15", "70% chance", KILL, SDR_PATH):
        assert fact in summary
    assert "[[" not in summary


def test_review_state_is_computed_from_today(vault: Any) -> None:
    after = vault.index.past_decisions(SDR_QUESTION, today=dt.date(2027, 1, 1))[0]
    assert after.review_state == "overdue" and "has passed" in after.follow_up_question()
    assert "before the 2026-12-15 review" in vault.index.past_decisions(SDR_QUESTION)[0].follow_up_question()


def test_kill_criteria_from_frontmatter_and_from_a_heading() -> None:
    string = record_for("decisions/a.md", "---\nkill_criterion: if CAC rises, stop\n---\n# A\n")
    assert string is not None and string.kill_criteria == ["if CAC rises, stop"]
    many = record_for("decisions/a.md", "---\nkill_criteria: [one, two]\n---\n# A\n")
    assert many is not None and many.kill_criteria == ["one", "two"]
    heading = record_for("decisions/a.md", "# A\n\n## Kill criteria\n- CAC above plan\n- [[Churn|churn]] above 3 %\n")
    assert heading is not None and heading.kill_criteria == ["CAC above plan", "churn above 3 %"]


def test_a_note_without_fields_still_gives_a_record() -> None:
    record = record_for("decisions/2026-03-pause-ads.md", "# Pause ads\n\nWe paused them.\n")
    assert record is not None and record.status == "unknown" and record.decided == "2026-03"
    assert record.review_date is None and record.review_state == "unknown" and record.kill_criteria == []
    assert "what has changed" in record.follow_up_question().lower()


def test_only_decision_notes_have_records() -> None:
    assert record_for("notes/a.md", "---\nstatus: draft\n---\n# A\n") is None
    tagged = record_for("notes/a.md", "---\ntags: [decision]\n---\n# A\n")
    assert tagged is not None


@pytest.mark.parametrize(
    "question",
    [SDR_QUESTION, "What did we decide about SDRs?", "Is outbound working?", "Should we pause the second SDR seat?"],
)
def test_past_decision_is_found_on_the_same_topic(vault: Any, question: str) -> None:
    assert [r.path for r in vault.index.past_decisions(question)] == [SDR_PATH]


@pytest.mark.parametrize(
    "question",
    [
        "Should we hire a designer?",
        "Should we change our pricing?",  # the note only links to the pricing note in passing
        "What do my notes say about annual prepayment?",
        "What's our runway?",
        "Hello",
    ],
)
def test_past_decision_is_not_claimed_on_another_topic(vault: Any, question: str) -> None:
    assert vault.index.past_decisions(question) == []


def test_asking_what_was_decided_lists_the_decisions(vault: Any) -> None:
    assert [r.path for r in vault.index.past_decisions("What have we decided so far?")] == [SDR_PATH]


def test_the_best_match_comes_first_and_the_list_is_capped(vault: Any) -> None:
    for month in ("10", "11", "12"):
        write_note(
            vault,
            f"decisions/2026-{month}-outbound.md",
            f"---\ndate: 2026-{month}-01\n---\n# Outbound hiring {month}\n",
        )
    found = vault.index.past_decisions("Should we hire SDRs for outbound?")
    assert found[0].path == SDR_PATH and len(found) == 3


def test_a_new_decision_note_is_picked_up_and_a_deleted_one_goes(vault: Any) -> None:
    write_note(vault, "decisions/2026-10-open-emea.md", "---\nstatus: proposed\n---\n# Open an EMEA sales region\n")
    assert [r.status for r in vault.index.past_decisions("Should we open a sales region in EMEA?")] == ["proposed"]
    (vault.vault.root / "decisions/2026-10-open-emea.md").unlink()
    vault.index.refresh(["decisions/2026-10-open-emea.md"], dense=False)
    assert vault.index.past_decisions("Should we open a sales region in EMEA?") == []


# --- the Verifier and dates ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("date", ["15 Dec", "Dec 15", "December 15th", "15th of December", "Sep. 15"])
def test_a_written_date_is_not_a_financial_figure(date: str) -> None:
    assert verify_numbers(f"Review it by {date}.", []) == []


def test_a_number_next_to_a_month_is_still_checked() -> None:
    assert verify_numbers("In May we had 15 customers and 40 % churn.", []) == ["15", "40 %"]
    assert verify_numbers("December 40 % churn", []) == ["40 %"]


# --- the founder's bug, end to end ----------------------------------------------------------------------------------
async def test_a_model_that_ignores_the_decision_cannot_hide_it(vault: Any) -> None:
    provider = FakeProvider([[ToolCall(name="search_vault", arguments={"query": "SDR metrics"})], BLIND_ANSWER])
    result = await runner(provider, vault).run(librarian("Find SDR metrics and conversion rates"), SDR_QUESTION)
    assert result.text.startswith(BLIND_ANSWER) and result.attempts == 1 and result.verified
    for fact in ("2026-09-15", "2026-12-15", "70% chance", KILL, f"[{SDR_PATH}]"):
        assert fact in result.text
    assert {c.path for c in result.citations} == {SDR_PATH}
    assert result.tool_calls[0]["tool"] == "past_decisions"


async def test_the_model_is_told_about_the_decision_before_it_answers(vault: Any) -> None:
    provider = FakeProvider(["ok"])
    await runner(provider, vault).run(librarian(), SDR_QUESTION)
    system = provider.calls[0]["messages"][0].content
    assert "on record for this topic" in system and "2026-12-15" in system and KILL in system
    assert "`decisions`" in system  # the prompt asks for the folder search
    assert all(t.name != "past_decisions" for t in provider.calls[0]["tools"])  # code runs it, not the model
    assert {t.name for t in provider.calls[0]["tools"]} == {"search_vault", "read_note", "write_note"}


async def test_an_answer_that_states_the_decision_is_left_as_it_is(vault: Any) -> None:
    answer = (
        f"You already decided this on 2026-09-15 [{SDR_PATH}]: {KILL}. "
        "The prediction is 70%, and the review is on 15 Dec."
    )
    result = await runner(FakeProvider([answer]), vault).run(librarian(), SDR_QUESTION)
    assert result.text == answer and result.verified


async def test_the_librarian_on_another_topic_is_not_told_about_it(vault: Any) -> None:
    provider = FakeProvider(["ok"])
    result = await runner(provider, vault).run(librarian("annual prepayment"), "What is annual prepayment?")
    assert result.past_decisions == [] and "on record for this topic" not in provider.calls[0]["messages"][0].content


async def test_rules_fallback_also_surfaces_the_decision(vault: Any) -> None:
    down = FakeProvider(default=lambda m, t, s: LLMUnavailable("Ollama not reachable"))
    result = await runner(down, vault).run(librarian(), SDR_QUESTION)
    assert result.provider == "rules" and result.verified and KILL in result.text and "2026-12-15" in result.text


async def test_a_missing_vault_does_not_break_the_librarian() -> None:
    result = await runner(FakeProvider(["No vault here."]), None).run(librarian(), SDR_QUESTION)
    assert result.past_decisions == [] and result.text == "No vault here." and result.status == "done"


# --- step 8: citations list only the sources the answer used --------------------------------------------------------
async def test_citations_are_only_the_sources_the_answer_names(vault: Any) -> None:
    question = "What do my notes say about annual prepayment?"
    provider = FakeProvider(
        [
            [ToolCall(name="search_vault", arguments={"query": "SDR hiring annual prepayment", "k": 8})],
            "Annual prepayment would get a 15 % discount [notes/pricing-strategy.md].",
        ]
    )
    result = await runner(provider, vault).run(librarian(question), question)
    assert {c.path for c in result.citations} == {"notes/pricing-strategy.md"} and result.verified
    assert SDR_PATH in {c.path for c in result.retrieved}  # returned by the search, but not used
    cards = [a for a in result.artifacts if a.kind == "citation"]
    assert cards and all(c.path == "notes/pricing-strategy.md" for a in cards for c in a.citations)


async def test_an_answer_with_no_source_cites_nothing(vault: Any) -> None:
    provider = FakeProvider(
        [[ToolCall(name="search_vault", arguments={"query": "annual"})], "Nothing useful.", "Nothing useful."]
    )
    result = await runner(provider, vault).run(librarian("annual"), "annual")
    assert result.citations == [] and result.retrieved and not result.verified


# --- the Advisor ------------------------------------------------------------------------------------------------------
async def _team_result(vault: Any) -> Any:
    return await runner(FakeProvider([BLIND_ANSWER]), vault).run(librarian(), SDR_QUESTION)


async def _advice(reply: str, results: list[Any]) -> tuple[str, Any, FakeProvider]:
    provider = FakeProvider([reply])
    chunks = [c async for c in advise(LLMRouter(provider), SDR_QUESTION, Plan(intent="decision", planner="t"), results)]
    done = chunks[-1]
    assert done.done and done.completion is not None
    return "".join(c.delta for c in chunks), done.completion, provider


async def test_advisor_that_ignores_the_decision_gets_it_added(vault: Any) -> None:
    text, completion, provider = await _advice("Hiring two SDRs costs runway.", [await _team_result(vault)])
    assert text.startswith("Hiring two SDRs costs runway. You already decided this:")
    assert "2026-09-15" in text and KILL in text and text.endswith("before the 2026-12-15 review?")
    assert completion.text == text
    assert "Past decisions on this topic" in provider.calls[0]["messages"][-1].content
    assert "kill criteria" in provider.calls[0]["messages"][0].content


async def test_advisor_that_states_the_decision_is_left_as_it_is(vault: Any) -> None:
    reply = (
        f"You already hired two SDRs in September at 70% confidence, with a kill criterion: {KILL}. "
        "Did they beat it before the 15 Dec review?"
    )
    text, _, _ = await _advice(reply, [await _team_result(vault)])
    assert text == reply


async def test_advisor_saying_by_december_has_not_stated_the_review_date(vault: Any) -> None:
    """Seen live: "a kill criterion ... by December" passed as the 15 December review, which the founder never saw."""
    reply = f"You already decided in September at 70%, with a kill criterion: {KILL}."
    text, _, _ = await _advice(reply, [await _team_result(vault)])
    assert text == f'{reply} On record for "Hire two SDRs for outbound": review date 2026-12-15.'


async def test_naming_a_kill_criterion_without_its_condition_is_not_enough(vault: Any) -> None:
    reply = "You already decided in September at 70%, with a kill criterion, and review on 15 Dec."
    text, _, _ = await _advice(reply, [await _team_result(vault)])
    assert text == f'{reply} On record for "Hire two SDRs for outbound": kill criteria: {KILL}.'


async def test_advisor_that_misses_one_fact_gets_only_that_fact(vault: Any) -> None:
    """Seen live: a good reply without the decision month got the whole record repeated after it."""
    reply = (
        f"You already hired two SDRs at 70%, with a kill criterion: {KILL}. Is that on track for the 2026-12-15 review?"
    )
    text, _, _ = await _advice(reply, [await _team_result(vault)])
    assert text == f'{reply} On record for "Hire two SDRs for outbound": decided 2026-09-15.'


async def test_librarian_that_misses_only_the_path_gets_only_the_path(vault: Any) -> None:
    answer = f"You decided this on 2026-09-15 at 70%; {KILL}; the 15 Dec review stands."
    result = await runner(FakeProvider([answer]), vault).run(librarian(), SDR_QUESTION)
    assert result.text == f'{answer} On record for "Hire two SDRs for outbound" [{SDR_PATH}].' and result.verified


def test_a_date_inside_the_file_name_does_not_count_as_stating_it() -> None:
    record = DecisionRecord(path="decisions/2026-09-hire.md", title="Hire", decided="2026-09-15")
    assert not decision_covered("See [decisions/2026-09-hire.md].", record, needs_path=True)
    assert not decision_covered("See [[2026-09-hire]] [decisions/2026-09-hire.md].", record, needs_path=True)
    assert decision_covered("Decided in September [decisions/2026-09-hire.md].", record, needs_path=True)


def test_a_note_with_no_fields_counts_as_covered_when_named() -> None:
    record = DecisionRecord(path="decisions/a.md", title="Pause ads")
    assert decision_covered("We chose to pause ads.", record, needs_path=False)
    assert not decision_covered("We chose nothing.", record, needs_path=False)


async def test_advisor_without_a_past_decision_adds_nothing(vault: Any) -> None:
    result = await runner(FakeProvider(["ok"]), vault).run(librarian("annual"), "annual prepayment")
    text, _, provider = await _advice("Annual prepayment pulls cash forward.", [result])
    assert text == "Annual prepayment pulls cash forward."
    # Seen live: told about past decisions in general, the model invented one ("you decided this in August").
    assert "kill criteria" not in provider.calls[0]["messages"][0].content


def test_coverage_needs_each_date_and_the_kill_criteria() -> None:
    record = DecisionRecord(
        path="decisions/a.md",
        title="A",
        decided="2026-09-15",
        review_date="2026-12-15",
        kill_criteria=["CAC above plan"],
        predictions=["70% chance of growth"],
    )
    full = "September, CAC above plan, 70 %, December 15th"
    assert decision_covered(full, record, needs_path=False)
    assert decision_covered("2026-09-15, CAC above plan, 70 percent, the 15th of December", record, needs_path=False)
    assert not decision_covered("CAC above plan, 70 %, 15 Dec", record, needs_path=False)  # no decision date
    assert not decision_covered("September, CAC above plan, 70 %", record, needs_path=False)  # no review date
    assert not decision_covered("September, CAC above plan, 170 %, 15 Dec", record, needs_path=False)  # no prediction
    assert not decision_covered("September, a kill criterion, 70 %, 15 Dec", record, needs_path=False)  # no condition
    assert not decision_covered(full, record, needs_path=True)  # no path


async def test_the_model_always_has_the_results_for_the_question_as_asked(vault: Any) -> None:
    """Seen live: the model searched only `decisions` and then invented what the board update asks."""
    question = "What does the board update ask of the board?"
    provider = FakeProvider(["ok"])
    result = await runner(provider, vault).run(librarian("Something narrower"), question)
    assert [c["tool"] for c in result.tool_calls] == ["past_decisions", "search_vault"]
    assert result.tool_calls[1]["arguments"] == {"query": question}
    last = next(m for m in provider.calls[0]["messages"] if m.role == "tool")
    assert last.role == "tool" and "sources/board-update-2026-q3.md" in last.content and "Introductions" in last.content


async def test_only_the_librarian_searches_first(vault: Any) -> None:
    analyst = AgentInstance(type="financial_analyst", name="Financial Analyst", brief="x", provider="fake")
    finance = SimpleNamespace(metrics=SimpleNamespace(available_months=lambda: []))
    provider = FakeProvider(["ok"])
    the_runner = AgentRunner(LLMRouter(provider), EventBus(), "r", lambda aid: ToolContext(finance, vault, aid))
    assert (await the_runner.run(analyst, SDR_QUESTION)).tool_calls == []


# --- routing ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("What do my notes say about churn reasons?", "knowledge"),  # seen live: went to the Analyst, who has no notes
        ("What did we decide about SDRs?", "knowledge"),
        ("What does the board update ask of the board?", "knowledge"),
        ("What did my journal say about the logistics customers?", "knowledge"),
        ("Should we follow what my notes say about churn?", "decision"),
        ("What's our churn?", "finance"),
        ("What's our runway?", "finance"),
    ],
)
def test_naming_the_notes_goes_to_the_librarian(message: str, intent: str) -> None:
    assert rule_intent(message) == intent


# --- the Planner ------------------------------------------------------------------------------------------------------
async def _team_types(tasks: list[dict[str, str]]) -> list[str]:
    reply = json.dumps({"decision_type": "hiring", "reversibility": "one_way", "tasks": tasks})
    the_plan = await plan(SDR_QUESTION, LLMRouter(FakeProvider([reply])), DecisionService(FakeDecisionProvider()))
    return [i.type for i in the_plan.team]


async def test_a_decision_team_always_has_a_librarian() -> None:
    analyst = {"agent_type": "financial_analyst", "brief": "Numbers"}
    assert await _team_types([analyst, analyst]) == ["financial_analyst", "financial_analyst", "librarian"]
    assert await _team_types([analyst] * 4) == ["financial_analyst"] * 3 + ["librarian"]
    assert await _team_types([analyst, {"agent_type": "librarian", "brief": "Notes"}]) == [
        "financial_analyst",
        "librarian",
    ]


async def test_the_whole_run_answers_with_the_past_decision(vault: Any, loaded_db: Any, tmp_path: Path) -> None:
    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        return json.dumps(schema_example(schema)) if schema else BLIND_ANSWER

    orchestrator = AgentOrchestrator(
        LLMRouter(FakeProvider(default=respond)),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(None, vault, aid),
    )
    run = orchestrator.start(SDR_QUESTION)
    assert run.task is not None
    result = await run.task
    assert result.intent == "decision" and [d.path for d in result.past_decisions] == [SDR_PATH]
    assert "You already decided this" in result.answer and KILL in result.answer and "2026-12-15" in result.answer
    assert result.verified, result.issues
    assert {c.path for c in result.citations} == {SDR_PATH}
    payload = result.model_dump(mode="json")
    assert payload["past_decisions"][0]["review_date"] == "2026-12-15"


# --- the eval ---------------------------------------------------------------------------------------------------------
def test_the_offline_eval_passes_on_the_sample_vault() -> None:
    cases = load_cases()
    assert 5 <= len(cases) <= 8
    results = run_offline(cases)
    assert len(results) == 2 * len(cases)
    assert [r.line() for r in results if not r.passed] == []


def test_the_eval_catches_the_founders_bug() -> None:
    case = EvalCase(
        "x",
        SDR_QUESTION,
        cited=[SDR_PATH],
        facts=[["2026-12-15"]],
        past_decisions=[SDR_PATH],
        not_cited=["notes/customer-churn.md"],
    )
    problems = score(case, answer=BLIND_ANSWER, cited={"notes/customer-churn.md"}, past_decisions=set())
    assert len(problems) == 4


def test_check_live_reply_reads_the_chat_response() -> None:
    case = load_cases()[0]
    reply = {
        "answer": "You hired two SDRs on 2026-09-15; 70% prediction; under eight a month; review 15 Dec.",
        "citations": [{"path": SDR_PATH}],
        "past_decisions": [{"path": SDR_PATH}],
        "agents": [],
        "verified": True,
        "elapsed_ms": 40000,
    }
    good = check_live_reply(case, reply)
    assert good.passed and "40 s" in good.line()
    bad = check_live_reply(case, {**reply, "answer": "Hire them.", "verified": False, "issues": ["x"]})
    assert not bad.passed and "not verified" in bad.line()
