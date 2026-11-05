"""Decision quality: the frame (type, costs, options, goals), the guards on any answer, and the memo code enforces."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.decision_frame import (
    build_frame,
    classify_decision,
    goals_from_note,
    inputs_question,
    names_goal,
    parse_inputs,
    starter_outcomes_for,
)
from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.guards import (
    NOTHING_ON_RECORD,
    goal_contradiction,
    guarded,
    in_one_voice,
    in_role,
    role_problems,
    unbacked_decision_claim,
    without_contradictions,
)
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentRunner, _analyst_on_a_cost_model, advisor_memo_note
from app.agents.specialists import (
    RULE_TEXT,
    MemoCriterion,
    MemoDraft,
    MemoOption,
    MemoPrediction,
    _goal_lines,
    _kill_fits_the_model,
    _limit_in,
    _option_lines,
    in_your_words,
    with_required_fields,
)
from app.agents.tools import ToolContext, _is_a_written_memo
from app.conversation.manager import ConversationManager
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import Adjustments, ScenarioEngine
from app.evals.decision_eval import _down, _sloppy, check_decision, load_cases, run_offline
from app.llm.base import ToolCall
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.vault.decisions import DecisionRecord
from tests.test_past_decisions import make_vault
from tests.test_specialists import _until

DUBAI = "Should we open a Dubai office? Write a decision memo."
TODAY = dt.date(2026, 11, 5)


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


@pytest.fixture
def vault(tmp_path: Path) -> Any:
    return make_vault(tmp_path / "vault")


@pytest.fixture
def ctx(finance: Any, vault: Any) -> ToolContext:
    return ToolContext(finance, vault, "")


def orchestrator(provider: FakeProvider, finance: Any, vault: Any) -> AgentOrchestrator:
    return AgentOrchestrator(
        LLMRouter(provider),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )


# --- type ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (DUBAI, "new_office"),
        ("Should we open an office in Berlin?", "new_office"),
        ("Should we expand into Germany?", "new_office"),
        ("Decide whether to open a second sales region", "new_office"),
        ("Should we open a Dubai office and hire two reps?", "new_office"),
        ("Should we hire two SDRs?", "hire"),
        ("Should we hire two people to launch a new product?", "hire"),
        ("Should we raise our prices by 10%?", "pricing"),
        ("What would a discount do to churn?", "pricing"),
        ("Should we launch a new product line?", "new_product"),
        ("Should we spend $20k more on marketing?", "spend"),
        ("Should we cut costs by $10k a month?", "spend"),
        ("Should we raise a seed round of $2M?", "fundraise"),
        ("Should we rewrite our company values?", "other"),
    ],
)
def test_a_decision_is_typed_from_the_founders_words(message: str, expected: str) -> None:
    assert classify_decision(message) == expected


def test_the_planners_label_is_only_a_fallback() -> None:
    assert classify_decision("What about the Gulf?", "market expansion") == "new_office"
    assert classify_decision(DUBAI, "hiring") == "new_office"
    assert classify_decision("What about the Gulf?", None) == "other"


# --- the founder's inputs --------------------------------------------------------------------------------------------
def test_the_founders_figures_are_read_for_this_type_only() -> None:
    said = "Assume 3 local hires, rent $4,000 a month, setup $25k."
    assert parse_inputs(said, "new_office") == {"hires": 3, "rent": 4000, "setup": 25000}
    assert parse_inputs("two hires and travel of $1,500", "new_office") == {"hires": 2, "travel": 1500}
    assert parse_inputs("Should we raise our prices by 15%?", "pricing") == {"price": 15}
    assert parse_inputs("What is our runway?", "new_office") == {}
    assert parse_inputs(said, "other") == {}


def test_a_later_figure_replaces_an_earlier_one() -> None:
    assert parse_inputs("rent $4,000 a month\nThe founder then added: rent $6,000", "new_office")["rent"] == 6000


def test_the_founders_figure_replaces_the_assumption(ctx: ToolContext) -> None:
    frame = build_frame(f"{DUBAI} Rent is $4,000 a month, 3 local hires.", ctx)
    assert frame.cost_model is not None
    rent = next(i for i in frame.cost_model.items if i.key == "rent")
    hires = next(i for i in frame.cost_model.items if i.key == "hires")
    assert (rent.low, rent.base, rent.high, rent.basis) == (4000, 4000, 4000, "founder")
    assert hires.base == 3 and "you said" in frame.cost_model.item_line(rent)
    setup = next(i for i in frame.cost_model.items if i.key == "setup")
    assert setup.basis == "assumption" and "assumption, confirm" in frame.cost_model.item_line(setup)


# --- the cost model --------------------------------------------------------------------------------------------------
def test_a_one_off_cost_is_paid_once(finance: Any) -> None:
    result = finance.scenario.run(Adjustments(one_off_cost=1000.0), horizon=6)
    assert {float(p.delta) for p in result.points} == {-1000.0}
    later = finance.scenario.run(Adjustments(one_off_cost=1000.0, start_month=3), horizon=6)
    assert [float(p.delta) for p in later.points] == [0.0, 0.0, -1000.0, -1000.0, -1000.0, -1000.0]


def test_an_office_is_many_costs_not_one_hire(ctx: ToolContext, finance: Any) -> None:
    frame = build_frame(DUBAI, ctx)
    assert frame.type == "new_office" and frame.subject == "A full Dubai office"
    model = frame.cost_model
    assert model is not None and {"setup", "rent", "hires", "travel", "compliance"} == {i.key for i in model.items}
    base = model.case("base")
    each = float(next(a.value for a in finance.scenario.run(Adjustments()).assumptions if a.name == "cost_per_hire"))
    assert base.one_off == 30000 and base.monthly == pytest.approx(2 * each + 5000 + 3000 + 1500, abs=0.01)
    # From the routine, not arithmetic in a sentence: and the cases differ in the right order.
    direct = finance.scenario.run(Adjustments(one_off_cost=30000, spend_change_monthly=9500, new_hires=2), horizon=12)
    assert base.scenario_runway_months == pytest.approx(float(direct.scenario_runway_months))
    changes = [model.case(c).runway_change_months for c in ("low", "base", "high")]
    assert changes[0] > changes[1] > changes[2]
    sentence = model.sentence()
    assert "assumption, confirm" in sentence and "1 hire" not in sentence and "no new revenue" in sentence


def test_every_other_type_gets_its_own_model(ctx: ToolContext) -> None:
    pricing = build_frame("Should we raise our prices by 10%? Write a memo.", ctx)
    assert pricing.subject == "A +10 % price change"
    assert pricing.cost_model and pricing.cost_model.case("base").runway_change_months > 0
    assert "no new revenue" not in pricing.cost_model.sentence()
    cut = build_frame("Should we offer a 20% discount?", ctx)
    assert cut.cost_model and next(i for i in cut.cost_model.items if i.key == "price").base == -20
    raise_ = build_frame("Should we raise a seed round of $2M?", ctx)
    assert raise_.type == "fundraise" and raise_.cost_model
    assert "net cash in of $1,970,000.00" in raise_.cost_model.sentence()
    assert "dilution" in raise_.cost_model.sentence()
    spend = build_frame("Should we spend $20,000 more a month on marketing?", ctx)
    assert spend.cost_model and spend.cost_model.case("base").monthly == 20000 and not spend.assumption_count
    other = build_frame("Should we rewrite our company values?", ctx)
    assert other.type == "other" and other.cost_model is None and "not modelled" in other.cost_sentence()
    assert other.predictions and other.kill_criteria


def test_a_hire_keeps_its_own_path_and_a_count_is_needed(ctx: ToolContext) -> None:
    frame = build_frame("Should we hire two SDRs?", ctx)
    assert frame.type == "hire" and frame.hires == 2 and not frame.questions
    assert frame.options[0].basis == "your payroll data"
    vague = build_frame("Should we hire more people?", ctx)
    assert vague.type == "hire" and vague.cost_model is None and "how many" in vague.questions[0]


def test_no_data_means_a_smaller_frame_not_a_failed_run(vault: Any) -> None:
    frame = build_frame(DUBAI, ToolContext(None, vault, ""))
    assert frame.type == "new_office" and frame.cost_model is None and frame.goals
    assert build_frame(DUBAI, ToolContext(None, None, "")).goals == []


def test_options_are_realistic_alternatives_with_costs(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    names = [o.name for o in frame.options]
    assert names == ["Travel-led pilot", "One remote rep", "Partner or distributor", "Free-zone desk", "Full office"]
    assert frame.default_option == "Travel-led pilot"
    assert all("$" in o.line("USD") for o in frame.options)
    full = next(o for o in frame.options if o.name == "Full office")
    assert full.monthly == frame.cost_model.case("base").monthly  # type: ignore[union-attr]
    assert frame.options[0].runway_change_months > full.runway_change_months  # type: ignore[operator]
    fixed_term = build_frame("Should we hire two SDRs?", ctx).options[2]
    assert "cost not modelled" in fixed_term.line("USD") and "$0.00" not in fixed_term.line("USD")


# --- goals -----------------------------------------------------------------------------------------------------------
def test_goals_come_from_the_list_under_their_heading() -> None:
    note = "# Co\n\n## Goals for the next 12 months\n1. Grow (see [[churn]]).\n- Decide [[a|b]] now.\n\n## Other\n- no"
    assert goals_from_note(note) == ["Grow", "Decide b now"]
    assert goals_from_note("# Co\n- not a goal") == []


def test_the_goal_check_says_plainly_when_a_decision_moves_away(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    status = {g.goal: g.status for g in frame.goals}
    assert status["Extend runway past 12 months without new financing"] == "moves_away"
    assert status["Decide whether to open a second sales region"] == "open_question"
    assert status["Bring logo churn under 1.5 % a month"] == "not_affected"
    lead = frame.goal_sentences()[0]
    assert lead.startswith("This moves you away from your goal") and "10.65 months today" in lead
    assert "12-month target" in lead


def test_a_price_rise_can_help_one_goal_and_hurt_another(ctx: ToolContext) -> None:
    status = {g.goal: g.status for g in build_frame("Should we raise our prices by 10%?", ctx).goals}
    assert status["Extend runway past 12 months without new financing"] == "moves_towards"
    assert status["Bring logo churn under 1.5 % a month"] == "moves_away"


def test_a_raise_is_against_a_goal_of_no_new_financing(ctx: ToolContext) -> None:
    frame = build_frame("Should we raise a seed round of $2M?", ctx)
    assert any(g.status == "moves_away" and "new financing" in g.sentence for g in frame.goals)


# --- guards ----------------------------------------------------------------------------------------------------------
def test_a_goal_is_never_reported_as_a_decision(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    said = guarded("The founder has decided to expand into a second sales region. Runway is short.", frame)
    assert "decided to expand" not in said and "still an open question" in said and "Runway is short." in said


@pytest.mark.parametrize(
    "line",
    [
        "You decided to expand.",
        "Your decision to expand is sound.",
        "The company has committed to a second region.",
        "We have already chosen Dubai.",
    ],
)
def test_claims_of_a_decision_go_when_nothing_backs_them(line: str) -> None:
    assert guarded(line, None) == NOTHING_ON_RECORD


@pytest.mark.parametrize(
    "line",
    ["You have not decided yet.", "Once you have decided, tell me.", "Decide whether to open it.", "Have you decided?"],
)
def test_other_mentions_of_deciding_are_left_alone(line: str) -> None:
    assert guarded(line, None) == line


def test_a_real_past_decision_can_still_be_stated() -> None:
    record = DecisionRecord(path="decisions/a.md", title="Hire two SDRs", status="decided", decision="Hire two SDRs")
    assert guarded("You already decided to hire two SDRs.", None, [record]) == "You already decided to hire two SDRs."
    assert guarded("You already decided this.", None, [record]) == "You already decided this."
    proposed = record.model_copy(update={"status": "proposed"})
    assert guarded("You already decided to hire two SDRs.", None, [proposed]) == NOTHING_ON_RECORD
    assert guarded("You decided to open Dubai.", None, [record]) == NOTHING_ON_RECORD


def test_a_one_hire_cost_is_never_the_cost_of_something_else(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    each = frame.cost_model.cost_per_person_monthly  # type: ignore[union-attr]
    for line in (
        "This is 1 hire at that rate.",
        "The cost per hire is what matters, not a quote for this role.",
        f"The office costs ${each:,.2f} a month.",
    ):
        said = guarded(line, frame)
        assert said == frame.cost_sentence(), line
    kept = f"Each local hire costs about ${each:,.2f} a month."
    assert guarded(kept, frame) == kept
    hire = build_frame("Should we hire a designer?", ctx)
    assert guarded("This is 1 hire at that rate.", hire) == "This is 1 hire at that rate."


def test_one_voice_is_you_and_your_adviser() -> None:
    assert in_one_voice("The founder should ask the Legal Team.") == "You should ask your adviser."
    assert in_one_voice("Ask your tax team and the legal department.") == "Ask your adviser and your adviser."
    assert in_one_voice("The Legal and Tax teams can confirm.") == "Your adviser can confirm."
    assert in_one_voice("Their tax position.") == "Their tax position."


def test_a_specialist_stays_in_role() -> None:
    wrote = "# Decision Memo\nDecision: go ahead.\nOwner: you. Stop hiring SDRs. Protect the roadmap."
    problems = role_problems("people_ops", wrote, DUBAI)
    assert len(problems) == 2
    assert in_role("people_ops", wrote, DUBAI) == "Owner: you. Protect the roadmap."
    # Asked about hiring, the advice is in scope, and the Memo Writer and Librarian keep their jobs.
    assert not role_problems("people_ops", "Pause hiring until March.", "Should we hire two SDRs?")
    assert in_role("people_ops", "Pause hiring until March.", "Should we hire two SDRs?") == "Pause hiring until March."
    assert not role_problems("librarian", "Decision: hire two SDRs. [decisions/a.md]", DUBAI)
    assert not role_problems("memo_writer", "# Decision Memo", DUBAI)
    assert not role_problems("people_ops", "The decision needs an owner.", DUBAI)


# --- the memo --------------------------------------------------------------------------------------------------------
def final(draft: MemoDraft, ctx: ToolContext, message: str = DUBAI) -> MemoDraft:
    return with_required_fields(draft, message, build_frame(message, ctx, today=TODAY), TODAY)


def test_exactly_one_option_is_chosen_and_it_is_not_rejected(ctx: ToolContext) -> None:
    memo = final(MemoDraft(chosen="Free-zone desk", why_chosen="It tests demand."), ctx)
    assert memo.chosen == "Free-zone desk"
    assert memo.decision.startswith("Proposed: Free-zone desk. It tests demand.")
    assert "You have not decided yet" in memo.decision
    assert not any(line.startswith("Free-zone desk") for line in memo.rejected)
    assert len(memo.rejected) == len(memo.options) - 1


def test_a_choice_off_the_list_falls_back_and_says_so(ctx: ToolContext) -> None:
    memo = final(MemoDraft(chosen="Delay until research is finished", why_chosen="Wait."), ctx)
    assert memo.chosen == "Travel-led pilot" and "Chosen by rule" in memo.decision
    assert len(memo.options) == 5


def test_a_near_miss_finds_its_option(ctx: ToolContext) -> None:
    assert final(MemoDraft(chosen="the full office"), ctx).chosen == "Full office"
    assert final(MemoDraft(why_chosen="A partner or distributor is safest."), ctx).chosen == "Partner or distributor"


def test_a_reason_for_another_option_does_not_go_in_the_decision(ctx: ToolContext) -> None:
    memo = final(MemoDraft(chosen="Travel-led pilot", why_chosen="A full office gives the best presence."), ctx)
    assert memo.chosen == "Travel-led pilot" and "best presence" not in memo.decision


def test_the_models_own_options_are_still_made_consistent(vault: Any) -> None:
    frameless = with_required_fields(
        MemoDraft(chosen="Go", options=["Go: fast", "Stop: safe"], rejected=["Go: too early"]), "q", None, TODAY
    )
    assert frameless.chosen == "Go" and frameless.rejected == ["Stop: safe"]
    other = build_frame("Should we rewrite our values?", ToolContext(None, vault, ""), today=TODAY)
    generic = with_required_fields(MemoDraft(), "Should we rewrite our values?", other, TODAY)
    assert generic.chosen == "Run a small pilot first" and len(generic.options) == 3


@pytest.mark.parametrize(
    "statement",
    [
        "Research done in 30 days",
        "The market study is complete by 2027-01-01",
        "Complete the licence application by 2027-01-01 at >= 1",
        "Things go well",
        "Pipeline >= 5",
        "Pipeline >= 5 by 2020-01-01",
    ],
)
def test_a_task_or_a_vague_hope_is_not_an_outcome(statement: str, ctx: ToolContext) -> None:
    memo = final(MemoDraft(predictions=[MemoPrediction(statement=statement, probability=0.9)]), ctx)
    assert len(memo.predictions) >= 1 and all(p.starter for p in memo.predictions)
    assert all(">=" in p.text() and "Research" not in p.text() for p in memo.predictions)


@pytest.mark.parametrize(
    "fields",
    [
        {"metric": "Qualified Gulf pipeline", "threshold": ">= 200000", "by": "2027-05-01"},
        {"statement": "At least 3 Dubai customers signed by May 2027"},
        {"statement": "Gulf pipeline over $200,000 within 6 months"},
    ],
)
def test_an_outcome_has_a_metric_a_threshold_and_a_date(fields: dict[str, str], ctx: ToolContext) -> None:
    memo = final(MemoDraft(predictions=[MemoPrediction(probability=0.6, **fields)]), ctx)
    assert len(memo.predictions) == 1 and not memo.predictions[0].starter
    assert memo.predictions[0].line().startswith("60%: ")


def test_kill_criteria_are_measurable_and_fit_the_cost_model(ctx: ToolContext) -> None:
    vague = final(MemoDraft(kill_criteria=[MemoCriterion(statement="It does not work")]), ctx)
    assert vague.kill_criteria and all(k.starter for k in vague.kill_criteria)
    assert all(k.line().startswith("Stop if ") for k in vague.kill_criteria)
    # The plan itself spends more than this, so the rule would fire at once.
    cheap = MemoCriterion(metric="Total spend", threshold="> $1,000", by="2027-05-01")
    assert final(MemoDraft(kill_criteria=[cheap]), ctx).kill_criteria[0].starter
    # Runway is 10.65, so this floor has already been passed.
    passed = MemoCriterion(metric="Runway", threshold="< 11 months", by="2027-05-01")
    assert final(MemoDraft(kill_criteria=[passed]), ctx).kill_criteria[0].starter
    fine = MemoCriterion(metric="Runway", threshold="< 8 months", by="2027-05-01")
    assert not final(MemoDraft(kill_criteria=[fine]), ctx).kill_criteria[0].starter


def test_starters_follow_the_option_proposed_not_the_full_model(ctx: ToolContext) -> None:
    pilot = final(MemoDraft(chosen="Travel-led pilot"), ctx)
    full = final(MemoDraft(chosen="Full office"), ctx)
    spent = [k.threshold for k in pilot.kill_criteria if k.metric.startswith("Total spent")]
    assert spent == ["> $27,000.00"]
    assert [k.threshold for k in full.kill_criteria if k.metric.startswith("Total spent")] == ["> $391,625.16"]
    runway = next(p.threshold for p in pilot.predictions if p.metric.startswith("Runway"))
    assert runway == ">= 10.44 months"


def test_a_stop_rule_tied_to_the_cost_is_always_there(ctx: ToolContext) -> None:
    off_topic = MemoCriterion(metric="Logo churn", threshold=">= 2.5%", by="2027-05-01")
    kills = final(MemoDraft(chosen="Travel-led pilot", kill_criteria=[off_topic]), ctx).kill_criteria
    assert kills[0].metric == "Logo churn" and kills[1].metric == "Total spent on this" and kills[1].starter


def test_a_reason_comes_from_the_numbers_when_the_model_only_repeats_the_description(ctx: ToolContext) -> None:
    repeated = MemoDraft(
        chosen="Travel-led pilot",
        options=[{"name": "Full office", "note": "The full model above; the hardest to undo."}],
    )  # type: ignore[list-item]
    memo = final(repeated, ctx)
    full = next(line for line in memo.rejected if line.startswith("Full office"))
    assert "Takes more runway than Travel-led pilot: -2.07 against -0.21 months." in full
    assert next(o.note for o in memo.options if o.name == "Full office") == ""


def test_an_empty_model_answer_is_sent_back_then_falls_back(finance: Any, vault: Any) -> None:
    async def go() -> Any:
        runner = AgentRunner(
            LLMRouter(FakeProvider(["", ""])), EventBus(), "run", lambda agent_id: ToolContext(finance, vault, agent_id)
        )
        return await runner.run(instance("regulatory_tax"), DUBAI)

    result = asyncio.run(go())
    assert result.attempts == 2 and "nothing specific was checked" in result.text


def test_the_analyst_never_restates_the_cases_in_its_own_words(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    text = _analyst_on_a_cost_model("This extends the low-case runway. Net burn is the thing to watch.", frame)
    assert text.startswith(frame.cost_sentence()) and "extends" not in text and "Net burn" in text


def test_a_tool_name_never_reaches_the_founder() -> None:
    text = "Check the licence with your adviser. Use the web_search tool to confirm it."
    assert role_problems("regulatory_tax", text, DUBAI)
    assert in_role("regulatory_tax", text, DUBAI) == "Check the licence with your adviser."


def test_the_rule_text_for_regulatory_names_points_and_your_adviser() -> None:
    text = RULE_TEXT["regulatory_tax"]
    assert (
        "your adviser" in text
        and text.count(
            "\
- "
        )
        == 4
    )


def test_a_note_the_line_already_holds_is_not_said_twice(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    full = next(o for o in frame.options if o.is_full)
    draft = MemoDraft(chosen=full.name, options=[MemoOption(name=full.name, note=full.note)])
    line = _option_lines(draft, frame)[0]
    assert line.count(full.note.strip(" .")) == 1


def test_the_memo_never_contradicts_the_goal_check_or_says_we(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    draft = MemoDraft(
        chosen="Travel-led pilot",
        why_chosen="It is cheap. It aligns with the goal of extending runway. It allows us to test our market.",
        context="The goal of extending runway is still within reach. Sales are steady.",
        assumptions=["Cost model assumptions for the pilot are confirmed.", "Demand exists in Dubai."],
    )
    out = in_your_words(draft, frame, [])
    assert out.why_chosen == "It is cheap. It allows you to test your market."
    assert out.context == "Sales are steady."
    assert out.assumptions == ["Demand exists in Dubai."]


def test_US_the_place_is_not_turned_into_you(ctx: ToolContext) -> None:
    out = in_your_words(MemoDraft(chosen="x", context="Most of your customers are in the US."), None, [])
    assert out.context == "Most of your customers are in the US."


def test_the_goal_check_leads_with_the_option_proposed(ctx: ToolContext) -> None:
    lines = _goal_lines(build_frame(DUBAI, ctx), "Travel-led pilot")
    assert lines[0].startswith("The proposed option, Travel-led pilot, changes projected runway by -0.21 months.")
    assert lines[1].startswith("This moves you away")


def test_the_reply_gives_the_cost_of_the_option_proposed(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    memo = SimpleNamespace(path="decisions/x.md", review_date="2026-12-05", chosen="Travel-led pilot")
    note = advisor_memo_note("A full office costs more.", [SimpleNamespace(memo=memo)], frame)  # type: ignore[list-item]
    assert "The memo proposes Travel-led pilot: $0.00 up front, $3,000.00 a month, runway -0.21 months" in note
    assert note.endswith("It is at decisions/x.md, for review on 2026-12-05.")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Should we expand into a new product line?", "new_product"),
        ("Should we expand into Germany?", "new_office"),
    ],
)
def test_expanding_into_something_else_is_not_an_office(message: str, expected: str) -> None:
    assert classify_decision(message) == expected


def test_a_passing_word_does_not_count_as_telling_the_founder_about_a_goal() -> None:
    goal = "Bring logo churn under 1.5 % a month"
    assert not names_goal(goal, "Logo churn would rise, likely under pressure.")
    assert names_goal(goal, "This works against your goal of bringing logo churn under 1.5 % a month.")
    assert not names_goal("Decide whether to open a second sales region", "This region is hard.")


def test_a_smaller_option_does_not_inherit_the_full_changes_results(ctx: ToolContext) -> None:
    frame = build_frame("Should we raise our prices by 10%? Write a decision memo.", ctx)
    full = next(o for o in frame.options if o.is_full)
    other = next(o for o in frame.options if not o.is_full)
    assert any(p.metric == "MRR" for p in starter_outcomes_for(frame, full.name)[0])
    assert not any(p.metric == "MRR" for p in starter_outcomes_for(frame, other.name)[0])


def test_a_spend_limit_is_judged_against_the_option_proposed(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    rule = MemoCriterion(metric="Total spent on this", threshold="> $30,000", by="2027-05-01")
    assert _kill_fits_the_model(rule, frame, "Travel-led pilot")
    assert not _kill_fits_the_model(rule, frame, "Full office")


@pytest.mark.parametrize(
    ("threshold", "limit"), [("> $400k", 400_000.0), ("< 9.50 months", 9.5), ("> $1.5 million", 1_500_000.0)]
)
def test_a_stop_rule_limit_is_read_with_its_scale(threshold: str, limit: float) -> None:
    assert _limit_in(MemoCriterion(metric="x", threshold=threshold, by="2027-05-01")) == limit


def test_the_codes_own_runway_stop_rule_is_kept(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    rule = MemoCriterion(metric="Runway (actual burn)", threshold="< 9.50 months", by="2027-05-01")
    assert _kill_fits_the_model(rule, frame, "Full office")


def test_a_churn_stop_rule_already_passed_today_is_dropped(ctx: ToolContext) -> None:
    frame = build_frame("Should we launch a new product line? Write a decision memo.", ctx)
    today = next(b.value for b in frame.baseline if b.metric == "logo_churn") * 100
    low = MemoCriterion(metric="Logo churn", threshold=f"Above {today - 0.1:.2f}%", by="2027-05-01")
    high = MemoCriterion(metric="Logo churn", threshold=f"Above {today + 1:.2f}%", by="2027-05-01")
    assert not _kill_fits_the_model(low, frame) and _kill_fits_the_model(high, frame)


def test_only_false_comfort_goes_from_the_memo(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    draft = MemoDraft(chosen="Travel-led pilot", why_chosen="This does not help your goal. It is easy to stop.")
    assert in_your_words(draft, frame, []).why_chosen == "This does not help your goal. It is easy to stop."


def test_founders_with_no_the_is_second_person_too() -> None:
    assert in_one_voice("Founder\u2019s time is short. It needs the founder's time.") == (
        "Your time is short. It needs your time."
    )


def test_ordinary_advice_about_a_tool_is_not_tool_talk() -> None:
    assert not role_problems("people_ops", "Use a CRM tool to log these leads.", DUBAI)


def test_the_analysts_true_figures_stay_and_only_the_restated_model_goes(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    text = "Your runway on actual burn is 10.65 months. This office costs less in the high case. Net burn is high."
    out = _analyst_on_a_cost_model(text, frame)
    assert "10.65 months" in out and "Net burn is high." in out and "costs less" not in out


def test_a_proposed_memo_backs_nothing_but_a_decided_one_does(vault: Any) -> None:
    def note(status: str) -> str:
        return (
            f"---\ntitle: Pilot\nstatus: {status}\nproposed_option: Pilot\nreview_date: 2027-01-01\n---\n"
            "# Pilot\n\n## Decision\nProposed: Pilot.\n\n## Predictions\n- Pipeline >= 73,219 by 2027-05-01\n"
        )

    path = "decisions/2026-01-01-pilot.md"
    target = vault.vault.root / path
    target.write_text(note("proposed"), encoding="utf-8")
    ctx = ToolContext(None, vault, "a")
    assert _is_a_written_memo(ctx, path)
    target.write_text(note("decided"), encoding="utf-8")
    assert not _is_a_written_memo(ctx, path)


def test_starter_stop_rules_never_fire_at_once(ctx: ToolContext) -> None:
    for message in (DUBAI, "Should we raise our prices by 10%?", "Should we hire two SDRs?"):
        frame = build_frame(message, ctx, today=TODAY)
        runway = next(b.value for b in frame.baseline if b.metric == "runway")
        floors = [k for k in frame.kill_criteria if k.metric.startswith("Runway")]
        forecasts = [p for p in frame.predictions if p.metric.startswith("Runway")]
        for kill in floors:
            assert float(kill.threshold.split()[1]) < runway, message
            for forecast in forecasts:
                assert float(kill.threshold.split()[1]) < float(forecast.threshold.split()[1]), message


# --- whole runs ------------------------------------------------------------------------------------------------------
def instance(agent_type: str) -> AgentInstance:
    return AgentInstance(id=f"agt_{agent_type}", type=agent_type, name=REGISTRY[agent_type].title, brief="b")


def test_the_decision_eval_passes_with_no_llm_and_with_a_sloppy_one() -> None:
    results = run_offline()
    assert len(results) == 8
    assert [r.line() for r in results if not r.passed] == []


def test_the_rubric_catches_the_memo_the_founder_saw() -> None:
    case = load_cases()[0]
    memo = """# Open a Dubai office

## Decision
Delay until research is done.

## Goal check
No goals found in profile/company.md.

## Cost model
- Adding 1 hire at $11,423.62 a month.

## Options
- Open now
- Delay

## Rejected alternatives
- Open now: too early
- Delay: too slow

## Metrics
- Payroll 308,437.67 (formula: sum)

## Predictions
- 90%: Research done in 30 days

## Kill criteria
- It does not work

## Team findings
- The founder has decided to expand [figure removed: no lineage]
"""
    reply = {
        "decision_type": "hiring",
        "answer": "1 hire at $11,423.62.",
        "memo": {"chosen": "Open now", "verified": True},
        "artifacts": [{"kind": "decision_memo", "data": {"markdown": memo}}],
    }
    problems = " | ".join(check_decision(case, "test", reply, TODAY).problems)
    for wanted in (
        "decision type",
        "no cost component",
        "assumptions are not labelled",
        "no low, base and high",
        "shown as verified",
        "one-hire framing in the answer",
        "no goal check",
        "does not say it moves away",
        "only 2 options",
        "0 proposed",
        "does not match the chosen",
        "also rejected",
        "predictions are not outcomes",
        "kill criteria are not measurable",
        "a scar",
        "dumps a formula",
        "payroll total",
        "third person in the memo",
    ):
        assert wanted in problems, wanted


async def test_the_analyst_is_not_offered_a_what_if_for_an_office(finance: Any, vault: Any) -> None:
    offered: list[list[str]] = []

    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        offered.append([t.name for t in tools or []])
        return "It costs what the model says."

    frame = build_frame(DUBAI, ToolContext(finance, vault, ""))
    runner = AgentRunner(
        LLMRouter(FakeProvider(default=respond)),
        EventBus(),
        "run",
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )
    result = await runner.run(instance("financial_analyst"), DUBAI, [], frame)
    assert "run_scenario" not in offered[0] and "get_metric" in offered[0]
    assert result.decision_impact is None and frame.cost_sentence() in result.text
    assert any(a.kind == "cost_model" for a in result.artifacts)
    assert result.verified


async def test_a_model_call_to_a_what_if_is_never_the_decisions_impact(finance: Any, vault: Any) -> None:
    frame = build_frame(DUBAI, ToolContext(finance, vault, ""))
    provider = FakeProvider([[ToolCall(name="run_scenario", arguments={"new_hires": 1})], "Done."])
    runner = AgentRunner(LLMRouter(provider), EventBus(), "run", lambda agent_id: ToolContext(finance, vault, agent_id))
    result = await runner.run(instance("financial_analyst"), DUBAI, [], frame)
    assert result.decision_impact is None


async def test_a_real_hire_still_gets_its_impact(finance: Any, vault: Any) -> None:
    question = "Should we hire a designer?"
    frame = build_frame(question, ToolContext(finance, vault, ""))
    runner = AgentRunner(
        LLMRouter(FakeProvider(["It costs what the tool says."])),
        EventBus(),
        "run",
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )
    result = await runner.run(instance("financial_analyst"), question, [], frame)
    assert result.decision_impact is not None and result.decision_impact.new_hires == 1


async def test_the_reply_states_the_real_cost_and_the_goal_whatever_the_model_says(finance: Any, vault: Any) -> None:
    run = orchestrator(FakeProvider(default=_sloppy), finance, vault).start(DUBAI)
    result = await run.task  # type: ignore[misc]
    assert result.decision_type == "new_office" and result.decision_impact is None
    assert result.decision_frame.cost_model is not None and result.assumptions_to_confirm == 5
    assert "A full Dubai office is modelled at" in result.answer
    assert "moves you away from your goal" in result.answer
    assert "assumptions to confirm" in " ".join(result.issues) and not result.verified
    people = (
        next(a for a in result.agents if a.type != "memo_writer" and "Decision Memo" in a.text)
        if any("Decision Memo" in a.text for a in result.agents if a.type != "memo_writer")
        else None
    )
    assert people is None


async def test_a_memo_is_never_verified_while_it_rests_on_assumptions(finance: Any, vault: Any) -> None:
    run = orchestrator(FakeProvider(default=_down), finance, vault).start(DUBAI)
    result = await run.task  # type: ignore[misc]
    assert result.memo is not None and not result.memo.verified and result.memo.assumptions_to_confirm == 5
    text = (vault.vault.root / result.memo.path).read_text(encoding="utf-8")
    assert "verified: false" in text and "proposed_option:" in text and "decision_type: new_office" in text


async def test_an_unconfirmed_figure_in_one_memo_is_not_a_source_for_the_next(finance: Any, vault: Any) -> None:
    run = orchestrator(FakeProvider(default=_sloppy), finance, vault)
    first = await run.start(DUBAI).task  # type: ignore[misc]
    assert first.memo is not None and any("73,219" in line for line in first.memo.open_numbers)
    second = await run.start(DUBAI).task  # type: ignore[misc]
    assert second.memo is not None
    text = (vault.vault.root / second.memo.path).read_text(encoding="utf-8")
    assert "73,219" not in text.split("## Open numbers to confirm")[0]
    assert any("73,219" in line for line in second.memo.open_numbers)


def test_the_memos_metrics_are_for_a_founder(tmp_path: Path, finance: Any, vault: Any) -> None:
    async def go() -> Any:
        return await orchestrator(FakeProvider(default=_down), finance, vault).start(DUBAI).task  # type: ignore[misc]

    result = asyncio.run(go())
    markdown = next(a for a in result.artifacts if a.kind == "decision_memo").data["markdown"]
    metrics = markdown.split("## Metrics")[1].split("## Predictions")[0]
    assert "Runway (actual burn) is 10.65 months as of" in metrics and "bank_balance.csv" in metrics
    assert "formula" not in metrics and "308,437.67" not in metrics


# --- the lane --------------------------------------------------------------------------------------------------------
class Held(FakeProvider):
    """Holds every reply until released, so a turn can arrive mid-run."""

    def __init__(self) -> None:
        super().__init__(default=_down)
        self.release = asyncio.Event()

    async def complete(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        if "the Planner of" not in str(messages[0].content):
            await self.release.wait()
        return await super().complete(messages, *args, **kwargs)


def lane(finance: Any, vault: Any, provider: FakeProvider | None = None) -> tuple[ConversationManager, Any]:
    provider = provider or Held()
    return ConversationManager(orchestrator(provider, finance, vault)), provider


async def test_the_lane_asks_for_this_decisions_own_inputs(finance: Any, vault: Any) -> None:
    manager, provider = lane(finance, vault)
    started = await manager.turn("s", DUBAI)
    await _until(lambda: any("tell me" in line for line in manager.sessions["s"].narration))
    question = next(line for line in manager.sessions["s"].narration if "tell me" in line)
    assert "full Dubai office" in question and "local hires" in question and "rent" in question
    assert not any(c.isdigit() for c in question)
    provider.release.set()
    await manager.orchestrator.runs[started.run_id].task


async def test_figures_mid_run_offer_a_rerun_that_uses_them(finance: Any, vault: Any) -> None:
    manager, provider = lane(finance, vault)
    started = await manager.turn("s", DUBAI)
    await _until(lambda: manager.orchestrator.runs[started.run_id].plan is not None)
    outcome = await manager.turn("s", "Rent is $4,000 a month, 3 local hires")
    assert outcome.kind == "amendment" and outcome.amendment_id and "your figures" in outcome.reply
    answer = manager.answer_amendment("s", outcome.amendment_id, True)
    provider.release.set()
    result = await manager.orchestrator.runs[answer["run_id"]].task
    rent = next(i for i in result.decision_frame.cost_model.items if i.key == "rent")
    assert rent.base == 4000 and rent.basis == "founder"
    assert result.memo is not None


async def test_figures_after_a_run_start_it_again_with_them(finance: Any, vault: Any) -> None:
    manager, _ = lane(finance, vault, FakeProvider(default=_down))
    started = await manager.turn("s", DUBAI)
    await manager.orchestrator.runs[started.run_id].task
    await _until(lambda: not manager.sessions["s"].narrators)
    again = await manager.turn("s", "Setup is $20,000")
    assert again.kind == "amendment" and again.run_id != started.run_id and "your figures" in again.reply
    result = await manager.orchestrator.runs[again.run_id].task
    assert result.decision_frame.cost_model.case("base").one_off == 20000
    # A question or a new request is still just that.
    await _until(lambda: not manager.sessions["s"].narrators)
    other = await manager.turn("s", "What is our runway?")
    assert other.kind is None and "runway" in manager.orchestrator.runs[other.run_id].message
    await manager.orchestrator.runs[other.run_id].task


async def test_narration_groups_a_wave_and_counts_what_is_left(finance: Any, vault: Any) -> None:
    question = "Should we hire two SDRs? Run a pre-mortem."
    reply = json.dumps(
        {
            "decision_type": "hiring",
            "reversibility": "one_way",
            "tasks": [
                {"agent_type": "financial_analyst", "brief": "Cost"},
                {"agent_type": "librarian", "brief": "Past"},
                {"agent_type": "devils_advocate", "brief": "Risks"},
            ],
        }
    )
    provider = FakeProvider([reply], default=_down)
    manager, _ = lane(finance, vault, provider)
    started = await manager.turn("s", question)
    await manager.orchestrator.runs[started.run_id].task
    await _until(lambda: not manager.sessions["s"].narrators)
    said = manager.sessions["s"].narration
    joined = " | ".join(said)
    assert "Financial Analyst and Librarian are done; one to go." in joined, joined
    assert "Devil's Advocate is done; writing your answer now." in joined, joined
    assert not any(line.endswith(" finished.") for line in said)
    assert not any(c.isdigit() for line in said for c in line)


def test_the_question_names_no_figure_and_a_clear_hire_has_none(ctx: ToolContext) -> None:
    assert inputs_question(build_frame("Should we hire two SDRs?", ctx)) == ""
    assert "price change" in inputs_question(build_frame("Should we raise our prices by 10%?", ctx))


# --- M3b -> M3c, first task: the prose never contradicts the frame ---------------------------------------------------
_RUNWAY_GOAL_TEXT = "Extend runway past 12 months without new financing"


def test_a_sentence_that_helps_a_goal_the_frame_moves_away_from_is_a_contradiction(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    # Seen live. "without new financing" inside the goal used to read as a negation.
    live = f"The Travel-led pilot aligns with the goal of {_RUNWAY_GOAL_TEXT.lower()}."
    assert goal_contradiction(live, frame, "Travel-led pilot") == _RUNWAY_GOAL_TEXT
    for wrong in (
        "This supports your goal.",
        "This is on track for the goal.",
        "It extends your runway.",
        "It has no impact on runway.",
        "It moves you closer to your goal of extending runway.",
    ):
        assert goal_contradiction(wrong, frame) == _RUNWAY_GOAL_TEXT, wrong


def test_what_is_true_about_a_goal_is_left_alone(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    for right in (
        "This does not align with your goal of extending runway.",
        "It moves you away from your goal.",
        "A pilot uses less runway than a full office.",
        "To meet the goal you would need to cut burn.",
        "If you cut burn, this would align with the goal.",
        "Check the licence with your adviser.",
    ):
        assert goal_contradiction(right, frame) is None, right
    for sentence in frame.goal_sentences():
        assert goal_contradiction(sentence, frame) is None


def test_an_option_that_gives_runway_back_may_help_the_goal(ctx: ToolContext) -> None:
    frame = build_frame("Should we raise our prices by 10%?", ctx)
    assert (
        goal_contradiction(
            "This keeps you on track for your goal of bringing logo churn down.", frame, "No price change"
        )
        is None
    )


def test_the_memo_drops_the_contradiction_and_the_answer_replaces_it(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    mixed = "It is cheap. It aligns with your goal of extending runway. It is easy to stop."
    assert without_contradictions(mixed, frame, "Travel-led pilot") == "It is cheap. It is easy to stop."
    answer = guarded(mixed, frame, [], chosen="Travel-led pilot")
    assert "aligns" not in answer
    assert "moves you away from your goal" in answer


def test_the_rule_memo_decision_never_says_it_helps(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    draft = MemoDraft(
        chosen="Travel-led pilot",
        why_chosen=f"It aligns with the goal: {_RUNWAY_GOAL_TEXT}. It is the easiest to undo.",
    )
    fixed = with_required_fields(in_your_words(draft, frame, []), DUBAI, frame)
    assert "aligns" not in fixed.decision
    assert "easiest to undo" in fixed.decision


def test_a_cheaper_option_not_proposed_says_why(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    chosen = "Free-zone desk"
    fixed = with_required_fields(MemoDraft(chosen=chosen), DUBAI, frame)
    cheaper = [r for r in fixed.rejected if r.startswith(("Travel-led pilot:", "Partner or distributor:"))]
    assert len(cheaper) == 2
    for line in cheaper:
        assert "Takes no more runway" in line
        assert any(word in line for word in ("control", "slower", "slowly", "learn")), line
    assert not any("Not proposed, though" in r for r in fixed.rejected)
    # The model's line without a reason does not count; one with a reason does.
    empty = MemoDraft(chosen=chosen, options=[MemoOption(name="Travel-led pilot", note="Another idea.")])
    assert "Another idea" not in with_required_fields(empty, DUBAI, frame).rejected[0]
    reasoned = MemoDraft(chosen=chosen, options=[MemoOption(name="Travel-led pilot", note="Too slow for this year.")])
    assert "Too slow for this year." in with_required_fields(reasoned, DUBAI, frame).rejected[0]


def test_every_option_of_every_type_has_a_trade_off(ctx: ToolContext) -> None:
    for message in (
        DUBAI,
        "Should we raise our prices by 10%?",
        "Should we launch a new product line?",
        "Should we spend $20,000 more a month on marketing?",
        "Should we raise a priced round?",
        "Should we hire two SDRs?",
    ):
        frame = build_frame(message, ctx)
        assert frame.options, message
        assert all(o.trade_off for o in frame.options), [o.name for o in frame.options if not o.trade_off]


def test_off_brief_agent_wording_seen_live(ctx: ToolContext) -> None:
    frame = build_frame(DUBAI, ctx)
    # People & Ops
    travel = "Own this yourself. Stop non-essential travel. Start with one market."
    assert role_problems("people_ops", travel, DUBAI, frame)
    assert in_role("people_ops", travel, DUBAI, frame) == "Own this yourself. Start with one market."
    assert not role_problems("people_ops", "Own this yourself.", DUBAI, frame)
    assert in_one_voice("It depends on one person: you, the founder.") == "It depends on one person: you."
    # Regulatory & Tax
    office = "Check the lease and the physical office licence with your adviser."
    assert role_problems("regulatory_tax", office, DUBAI, frame)
    fixed = in_role("regulatory_tax", office, DUBAI, frame)
    assert fixed.startswith(office) and "Travel-led pilot" in fixed
    both = "For a travel-led pilot check visas. For a full office check the lease."
    assert not role_problems("regulatory_tax", both, DUBAI, frame)
    # Librarian
    assert unbacked_decision_claim('You have already decided to "Decide whether to open a second sales region".', [])
    assert not unbacked_decision_claim("Whether you have decided is not on record.", [])
    # Devil's Advocate
    vault = "- Risk: no demand. Likelihood: high. Impact: high. Mitigation: use the vault for market data."
    assert role_problems("devils_advocate", vault, DUBAI, frame)
    assert "outside source" in in_role("devils_advocate", vault, DUBAI, frame)
    assert not role_problems("librarian", "Use the vault for market data.", DUBAI, frame)


def test_agents_are_told_the_options(ctx: ToolContext) -> None:
    text = build_frame(DUBAI, ctx).for_agents()
    assert "Travel-led pilot" in text and "not only the largest" in text
