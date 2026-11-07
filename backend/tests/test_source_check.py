"""The source check (founder's C4 finding): a fabricated figure with a fabricated citation must reach nobody."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest

from app.agents.decision_frame import DecisionFrame, GoalCheck
from app.agents.events import Citation, EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.guards import goal_contradiction
from app.agents.runtime import (
    AgentInstance,
    AgentResult,
    AgentRunner,
    findings_for_advisor,
    probing_question,
    single_metric,
)
from app.agents.sources import (
    REMOVED_NOTE,
    Evidence,
    cited_sources,
    gather,
    masked,
    simple_evidence,
    without_unsupported,
)
from app.agents.specialists import (
    SCOUT_LOCAL_NOTE,
    MemoCriterion,
    MemoDraft,
    MemoPrediction,
    _open_lines,
    scout_without_web,
    with_real_outcomes,
)
from app.agents.tools import ToolContext
from app.agents.verifier import Fact, check_sentence, extract_figures, fact_for
from app.decision.base import DecisionService, FakeDecisionProvider
from app.evals import decision_eval
from app.evals.vault_eval import make_sample_vault, sample_finance
from app.llm.base import LLMUnavailable, ToolCall
from app.llm.fake import FakeProvider, schema_example
from app.llm.router import LLMRouter

DUBAI = "Should we open a Dubai office? Write a decision memo."
FAKE_CLAIM = "Dubai's GDP is approximately $150 billion [notes/economic-overview.md]."
QUESTION = "Are you certain the $150 billion market size figure is verified before proceeding?"


@pytest.fixture
def finance(tmp_path: Any) -> Any:
    return sample_finance(tmp_path / "finance")


@pytest.fixture
def vault(tmp_path: Any) -> Any:
    return make_sample_vault(tmp_path / "vault")


def build_frame_with_a_goal_moved_away() -> DecisionFrame:
    goal = GoalCheck(
        goal="Extend runway past 12 months",
        status="moves_away",
        sentence='This moves you away from your goal "Extend runway past 12 months".',
    )
    return DecisionFrame(type="new_office", subject="s", goals=[goal])


def _on_disk(*paths: str) -> Any:
    return lambda path: path in paths


# --- a source must exist --------------------------------------------------------------------------------------------
def test_a_figure_cited_to_a_note_that_does_not_exist_goes() -> None:
    kept, removed = without_unsupported(f"{FAKE_CLAIM} Keep this line.", Evidence(exists=_on_disk()))
    assert kept == "Keep this line." and removed == [FAKE_CLAIM]


def test_a_claim_cited_to_a_note_that_does_not_exist_goes_even_with_no_figure() -> None:
    kept, removed = without_unsupported("Demand is strong [notes/made-up.md]. Fine.", Evidence(exists=_on_disk()))
    assert kept == "Fine." and len(removed) == 1


def test_a_citation_after_the_full_stop_still_belongs_to_the_sentence() -> None:
    kept, removed = without_unsupported("It is worth $150 billion. [notes/made-up.md] Fine.", Evidence())
    assert kept == "Fine." and "150 billion" in removed[0]


def test_every_form_of_a_citation_is_found() -> None:
    known = {"notes/my pricing note.md"}
    text = (
        "A [notes/a.md, notes/b.md]; see notes/c.pdf, (notes/d) and [notes/my pricing note.md] "
        "and https://example.test/r.pdf. Links [[notes/linked]] are not citations."
    )
    assert cited_sources(text, known) == {
        "notes/a.md",
        "notes/b.md",
        "notes/c.pdf",
        "notes/d",
        "notes/my pricing note.md",
        "https://example.test/r.pdf",
    }


def test_two_folders_named_in_prose_are_not_a_citation() -> None:
    assert cited_sources("Check your notes/journal for this.") == set()


def test_a_real_file_that_was_never_retrieved_backs_no_figure() -> None:
    evidence = Evidence(exists=_on_disk("notes/real.md"))
    assert evidence.supports("Our note has a view [notes/real.md].")
    assert not evidence.supports("It says $500 [notes/real.md].")


def test_a_figure_must_be_in_the_chunks_of_the_file_it_is_cited_to() -> None:
    evidence = Evidence(passages={"notes/a.md": [15.0], "notes/b.md": [99.0]}, quoted=[15.0, 99.0])
    assert evidence.supports("The discount is 15 % [notes/a.md].")
    assert not evidence.supports("The discount is 99 % [notes/a.md].")
    assert evidence.supports("The discount is 99 %.")  # uncited, and it is in a passage this run retrieved


def test_a_figure_with_lineage_stands_whatever_is_cited_beside_it() -> None:
    evidence = Evidence(free=[10.65], passages={"profile/company.md": [12.0]})
    assert evidence.supports("Runway is 10.65 months against the $12 goal [profile/company.md].")


def test_a_page_counts_only_if_a_search_returned_it() -> None:
    evidence = Evidence(passages={"https://example.test/zones": [40.0]})
    assert evidence.supports("There are 40 zones (https://example.test/zones).")
    assert not evidence.supports("There are 40 zones (https://made-up.test/zones).")


def test_a_data_file_a_routine_computed_from_is_a_real_source() -> None:
    assert Evidence(free=[5000.0], data_files={"pnl.csv"}).supports("Burn is $5,000 [pnl.csv].")


# --- figures -----------------------------------------------------------------------------------------------------
def test_a_figure_with_no_source_goes_even_inside_a_question() -> None:
    kept, removed = without_unsupported(f"You should check this. {QUESTION}", Evidence())
    assert kept == "You should check this." and removed == [QUESTION]


def test_the_founders_own_number_and_a_time_span_stay() -> None:
    evidence = simple_evidence([], "Rent is $9,000 a month.")
    text = "With rent at $9,000, run a 90-day pilot and review in 30 days."
    assert without_unsupported(text, evidence) == (text, [])


def test_large_scale_words_are_figures() -> None:
    for text in ("$1.5 trillion", "5 crore", "2 lakh"):
        assert extract_figures(text), text
    assert not without_unsupported("It is worth 1.5 trillion.", Evidence())[0]
    assert not without_unsupported("It is worth 40 crore.", simple_evidence([Fact(40.0)]))[0]


def test_text_that_passes_comes_back_exactly_as_it_was() -> None:
    text = "- Keep this line\n\n  and this. "
    assert without_unsupported(text, Evidence()) == (text, [])


def test_one_bad_line_in_a_list_goes_whole() -> None:
    text = "- Risk: rent. Mitigation: a cap.\n- Risk: the $150 billion market. Mitigation: verify it."
    kept, removed = without_unsupported(text, Evidence())
    assert kept == "- Risk: rent. Mitigation: a cap." and len(removed) == 1


def test_what_is_left_to_confirm_has_no_figure_and_no_source() -> None:
    assert masked(FAKE_CLAIM) == "Dubai's GDP is a figure to confirm"
    assert masked("- Rent is about AED 40,000 [notes/x.md].") == "Rent is a figure to confirm"
    assert not extract_figures(masked("Worth $1.5 trillion, or 40 % of $3 trillion, per https://x.test/a"))


def test_what_is_left_to_confirm_reads_cleanly() -> None:
    line = masked("- **Churn**: keep it under 1.5% a month (from a goal in profile/company.md).")
    assert line == "Churn: keep it under a figure to confirm a month (from a goal)"


def test_a_figure_in_the_founders_own_goal_stands_even_with_its_citation() -> None:
    class Goal:
        goal = "Bring logo churn under 1.5 % a month"
        sentence = "Your goal is open."

    class Frame:
        facts: ClassVar[list[Fact]] = []
        goals: ClassVar[list[Any]] = [Goal()]
        options: ClassVar[list[Any]] = []
        baseline: ClassVar[list[Any]] = []
        cost_model = None
        currency = "USD"

        def for_agents(self) -> str:
            return ""

        def findings_block(self) -> list[str]:
            return []

    evidence = gather("q", [], Frame(), _on_disk("profile/company.md"))
    assert evidence.supports("Keep churn under 1.5% a month [profile/company.md].")
    assert not evidence.supports("Keep churn under 2.5% a month [profile/company.md].")


def test_the_list_to_confirm_claims_nothing_the_goal_check_denies() -> None:
    frame = build_frame_with_a_goal_moved_away()
    draft = MemoDraft(chosen="Go", open_numbers=[])
    lines = _open_lines(
        ["It aligns with the goal to extend runway past 12 months.", "Our rent is a figure to confirm"], draft, frame
    )
    assert lines == ["Your rent is a figure to confirm"]


def test_an_aside_with_if_needed_does_not_hide_a_contradiction() -> None:
    frame = build_frame_with_a_goal_moved_away()
    claim = "It also aligns with the goal of extending runway while keeping the option to scale later if needed."
    assert goal_contradiction(claim, frame) == "Extend runway past 12 months"
    # A real condition is still not a claim.
    assert goal_contradiction("It aligns with the goal only if revenue doubles.", frame) is None


def test_a_flag_for_the_advisor_names_no_figure_and_no_source() -> None:
    result = AgentResult(
        agent_id="a",
        type="market_scout",
        name="Market Scout",
        brief="b",
        text=f"Fine. {REMOVED_NOTE}",
        verified=False,
        issues=[
            "number without lineage: $150 billion",
            "notes/economic-overview.md was not returned by a search",
            "removed: unsupported source (1)",
        ],
    )
    findings = findings_for_advisor([result])
    assert "150" not in findings and "economic-overview" not in findings
    assert "removed: unsupported source" in findings


def test_an_outcome_on_a_removed_figure_or_a_missing_source_is_dropped() -> None:
    draft = MemoDraft(
        predictions=[
            MemoPrediction(statement="Market > $150 billion by 2027-12-31"),
            MemoPrediction(statement="Revenue > $90,000 by 2027-12-31 [notes/made-up.md]"),
            MemoPrediction(statement="Signed customers > 20 by 2027-12-31"),
        ],
        kill_criteria=[MemoCriterion(statement="Stop if market < $150 billion by 2027-12-31")],
    )
    kept = with_real_outcomes(draft, Evidence(), [150e9])
    assert [p.statement for p in kept.predictions] == ["Signed customers > 20 by 2027-12-31"]
    assert kept.kill_criteria == []


# --- the Market Scout with cloud off -------------------------------------------------------------------------------
def test_the_scout_says_what_is_missing_and_gives_no_example_figures() -> None:
    text = scout_without_web("For example, the market could be worth about $5 billion, with strong demand.", set())
    assert "Your vault has no market data" in text and "To find: market size" in text and SCOUT_LOCAL_NOTE in text
    assert not extract_figures(text) and "strong demand" not in text


def test_the_scout_keeps_only_what_a_retrieved_passage_backs() -> None:
    text = scout_without_web("Dubai is booming. The notes name 3 leads [notes/gulf.md].", {"notes/gulf.md"})
    assert text.startswith("The notes name 3 leads [notes/gulf.md].") and "Still to find:" in text
    assert "booming" not in text


# --- through the agents ----------------------------------------------------------------------------------------------
def _agent(provider: FakeProvider, finance: Any, vault: Any) -> AgentRunner:
    return AgentRunner(LLMRouter(provider), EventBus(), "run_t", lambda aid: ToolContext(finance, vault, aid))


def _instance(agent_type: str, brief: str = "brief") -> AgentInstance:
    return AgentInstance(type=agent_type, name=agent_type, brief=brief)


async def test_a_librarian_figure_from_the_wrong_note_goes(finance: Any, vault: Any) -> None:
    provider = FakeProvider(
        default="Annual prepayment gets a 99 % discount [notes/pricing-strategy.md]. See [notes/pricing-strategy.md]."
    )
    result = await _agent(provider, finance, vault).run(
        _instance("librarian", "annual prepayment"), "What do my notes say about annual prepayment?"
    )
    assert "99 %" not in result.text and REMOVED_NOTE not in result.text and result.verified is False
    assert any(i.startswith("removed: unsupported source") for i in result.issues)
    assert result.removed and "99" not in " ".join(result.removed)


async def test_a_librarian_quoting_a_retrieved_note_is_untouched(finance: Any, vault: Any) -> None:
    provider = FakeProvider(default="Annual prepayment gets a 15 % discount [notes/pricing-strategy.md].")
    result = await _agent(provider, finance, vault).run(
        _instance("librarian", "annual prepayment"), "What do my notes say about annual prepayment?"
    )
    assert "15 % discount" in result.text and REMOVED_NOTE not in result.text and result.verified


async def test_the_cloud_scout_keeps_the_page_a_search_really_returned(finance: Any, vault: Any) -> None:
    from app.llm.base import Completion, WebAnswer, WebSource

    class Cloud(FakeProvider):
        supports_web_search = True

        async def web_search(self, query: str) -> WebAnswer:
            return WebAnswer(
                text="Dubai has 40 free zones.",
                sources=[WebSource(url="https://example.test/zones", title="Zones")],
                completion=Completion(text="", provider="cloud", model="m"),
            )

    written = "Dubai has 40 free zones (https://example.test/zones). Rent is $900 (https://made-up.test/rent)."
    cloud = Cloud(
        [[ToolCall(name="web_search", arguments={"query": "Dubai free zones"})], written, written],
        name="cloud",
        model="m",
        is_cloud=True,
    )
    router = LLMRouter(FakeProvider(), cloud, cloud_allowed=True)
    result = await AgentRunner(router, EventBus(), "run_t", lambda aid: ToolContext(finance, vault, aid)).run(
        _instance("market_scout"), DUBAI
    )
    assert "40 free zones" in result.text and "https://example.test/zones" in result.text
    assert "$900" not in result.text and "made-up" not in result.text and "cloud is off" not in result.text


def _planted(seen: list[str]) -> Any:
    """The C4 run: the Scout fabricates, later stages repeat whatever reaches them, and the Advisor asks about it."""

    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        system = str(messages[0].content)
        shown = " ".join(str(m.content) for m in messages[1:])
        if schema is not None:
            if "chosen" in schema.get("properties", {}):
                # A repair turn shows the Memo Writer its own draft: only the first turn shows what came before it.
                if not any(m.role == "assistant" for m in messages):
                    seen.append(shown)
                return json.dumps(
                    {
                        "title": "Dubai",
                        "chosen": "Travel-led pilot",
                        "why_chosen": f"A market this size is worth testing. {QUESTION}",
                        "context": f"{FAKE_CLAIM} You have one sales lead there.",
                        "options": [{"name": "Travel-led pilot", "note": "Easy to undo."}],
                        "assumptions": ["The market is worth $150 billion [notes/economic-overview.md]."],
                        "predictions": [{"statement": "Market > $150 billion by 2030-01-01", "probability": 0.5}],
                        "kill_criteria": ["Stop if spend is over $500,000 by 2030-01-01"],
                    }
                )
            return json.dumps(schema_example(schema))
        if system.startswith("You are the Market Scout"):
            return f"{FAKE_CLAIM} It has many free zones."
        if "Devil's Advocate" in system:
            seen.append(shown)
            if "150 billion" in shown:
                return "- Risk: the $150 billion market. Likelihood: high. Impact: high. Mitigation: verify it."
            return "- Risk: demand. Likelihood: medium. Impact: high. Mitigation: a small pilot."
        if "Advisor" in system or "advisor" in system:
            seen.append(shown)
            return f"You should run the pilot first. {QUESTION}"
        return "A note. See [notes/economic-overview.md] for the $150 billion figure."

    return respond


async def _run(finance: Any, vault: Any, seen: list[str]) -> Any:
    orchestrator = AgentOrchestrator(
        LLMRouter(FakeProvider(default=_planted(seen))),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )
    return await orchestrator.start(DUBAI).task  # type: ignore[misc]


async def test_the_fabricated_figure_reaches_no_later_stage(finance: Any, vault: Any) -> None:
    seen: list[str] = []
    await _run(finance, vault, seen)
    assert len(seen) >= 3  # the Devil's Advocate, the Memo Writer and the Advisor
    for shown in seen:
        assert "150 billion" not in shown and "economic-overview" not in shown


async def test_the_answer_and_the_memo_never_hold_it(finance: Any, vault: Any) -> None:
    result = await _run(finance, vault, [])
    memo = (vault.vault.root / result.memo.path).read_text(encoding="utf-8")
    for text in (result.answer, memo, *(a.text for a in result.agents)):
        assert "150 billion" not in text and "economic-overview" not in text
    assert "Are you certain" not in result.answer and REMOVED_NOTE not in result.answer
    assert result.verification.removed_claims >= 1
    assert "You should run the pilot first." in result.answer
    assert REMOVED_NOTE in memo.split("## Open numbers to confirm")[1].split("## Metrics")[0]
    assert "Dubai's GDP is a figure to confirm" in memo
    assert "You have one sales lead there." in memo  # the rest of the sentence's section stays
    scout = next(a for a in result.agents if a.type == "market_scout")
    assert "Your vault has no market data" in scout.text and "To find:" in scout.text
    assert not extract_figures(scout.text.split("To find:")[0])
    risks = next(a for a in result.artifacts if a.kind == "risk_register").data["risks"]
    assert risks and not any("150" in str(risk) for risk in risks)
    assert not result.verified and any("removed: unsupported source" in i for i in result.issues)


async def test_nothing_the_advisor_wrote_could_be_backed_and_the_findings_still_answer(
    finance: Any, vault: Any
) -> None:
    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        if "Advisor" in str(messages[0].content):
            return "Your runway is 99.5 months."
        raise LLMUnavailable("down")

    orchestrator = AgentOrchestrator(
        LLMRouter(FakeProvider(default=respond)),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )
    result = await orchestrator.start("Walk me through our runway.").task  # type: ignore[misc]
    assert "99.5" not in result.answer and REMOVED_NOTE not in result.answer and "10.65" in result.answer
    assert result.verification.removed_claims == 1 and result.verification.state == "not_verified"


# --- the evals -------------------------------------------------------------------------------------------------------
def _reply(answer: str, memo: str = "") -> dict[str, Any]:
    return {
        "answer": answer,
        "message": DUBAI,
        "agents": [],
        "citations": [],
        "artifacts": [{"kind": "decision_memo", "data": {"markdown": memo}, "lineage": []}],
        "memo": {"status": "proposed"},
    }


def test_the_rubric_catches_a_fabricated_citation_and_a_figure_in_a_question() -> None:
    case = decision_eval.load_cases()[0]
    cited = decision_eval.check_decision(case, "t", _reply("Fine.", FAKE_CLAIM), exists=lambda path: False).problems
    assert any("fabricated" in p for p in cited)
    assert any("notes/economic-overview.md, which does not exist" in p for p in cited)
    asked = decision_eval.check_decision(case, "t", _reply(QUESTION), exists=lambda path: False).problems
    assert any("a question in the answer has the unsupported figure" in p for p in asked)


def test_the_rubric_allows_saying_it_helps_a_goal_the_check_says_it_helps() -> None:
    case = decision_eval.load_cases()[1]
    memo = "## Decision\nThis aligns with the goal to extend runway past 12 months without new financing.\n"
    towards = {"goal": "Extend runway past 12 months without new financing", "status": "moves_towards"}
    reply = {**_reply("Fine.", memo), "decision_frame": {"goals": [towards]}}
    problems = decision_eval.check_decision(case, "t", reply, exists=lambda path: False).problems
    assert not any("contradicts" in p for p in problems)
    reply["decision_frame"] = {"goals": [{**towards, "status": "moves_away"}]}
    problems = decision_eval.check_decision(case, "t", reply, exists=lambda path: False).problems
    assert any("contradicts" in p for p in problems)


def test_the_rubric_catches_a_scout_with_an_example_figure() -> None:
    reply = {"agents": [{"type": "market_scout", "text": "The market may be $5 billion.", "tool_calls": []}]}
    problems = decision_eval._scout_problems(reply)
    assert any("does not list what to find" in p for p in problems)
    assert any("figure with no source" in p for p in problems)


def test_citation_objects_are_still_what_a_run_retrieved() -> None:
    # A run's `retrieved` paths resolve even when no vault is at hand, as in a direct call to `advise`.
    result = AgentResult(
        agent_id="a",
        type="librarian",
        name="Librarian",
        brief="b",
        retrieved=[Citation(path="notes/a.md", heading="h", chunk_id="c")],
    )
    assert gather("q", [result]).supports("Our note has a view [notes/a.md].")


# ---- single-metric questions (founder note, M4): code writes the number; at most one short question from the model
@pytest.mark.parametrize(
    ("question", "metric"),
    [
        ("What's our runway?", "runway"),
        ("what is our net burn", "net_burn"),
        ("How much runway do we have?", "runway"),
        ("Show me MRR", "mrr"),
        ("What is our gross margin?", "gross_margin"),
        ("What's our LTV:CAC?", "ltv_cac"),
    ],
)
def test_a_plain_metric_question_is_a_lookup(question: str, metric: str) -> None:
    assert single_metric(question) == metric


@pytest.mark.parametrize(
    "question",
    [
        "Why is our runway so short?",
        "What's our runway if we hire two people?",
        "What's our burn and churn?",
        "What was our runway in March 2026?",
        "What is CAC by channel?",
        "Is our runway enough?",
        "What's the weather?",
        "Compare MRR with ARR",
    ],
)
def test_anything_more_than_a_number_goes_to_the_model(question: str) -> None:
    assert single_metric(question) is None


@pytest.mark.parametrize(
    ("wrote", "expected"),
    [
        ("What does that burn rest on?", "What does that burn rest on?"),
        ("Will revenue hold?", "Will revenue hold?"),
        ("Is $150 billion right?", ""),
        ("Does that rest on 3 months?", ""),
        ("Does that rest on three months?", ""),
        ("Your runway is short.", ""),
        ("Is it short? Are you sure?", ""),
        ("", ""),
        ("Could this " + "very " * 30 + "long question run on?", ""),
    ],
)
def test_the_models_one_question_holds_no_figure(wrote: str, expected: str) -> None:
    assert probing_question(wrote) == expected


def test_months_at_this_burn_is_a_true_claim_about_runway() -> None:
    # Seen live, one run in five: a correct answer came back unverified, and code replaced the sentence.
    facts = [fact_for("runway", 10.65, "Runway (actual burn)", "months")]
    for sentence in (
        "Your burn gives you 10.65 months.",
        "At the current burn you have 10.65 months.",
        "Your current runway is 10.65 months based on the trailing three months of burn.",
    ):
        assert check_sentence(sentence, facts) == [], sentence
    # Still wrong: the same figure as an amount of money.
    assert check_sentence("Your burn is $10.65.", facts)


def test_a_figure_of_the_wrong_quantity_in_months_still_fails() -> None:
    facts = [fact_for("cac_payback", 4.2, "CAC payback", "months")]
    assert check_sentence("Your runway is 4.2 months.", facts)
