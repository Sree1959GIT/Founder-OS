"""A figure must keep its meaning: the founder saw total payroll, "verified", as the cost of a designer."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.events import EventBus
from app.agents.runtime import (
    AgentInstance,
    AgentResult,
    AgentRunner,
    Plan,
    _SentenceGate,
    advise,
    findings_for_advisor,
    hires_in_message,
)
from app.agents.tools import DecisionImpact, ToolContext, _decision_impact, run_tool
from app.agents.verifier import Fact, check_claims, column_fact, fact_for, facts_from_fields, verify
from app.engine.scenario import Adjustments
from app.evals.vault_eval import (
    WRONG_MEANING_ANSWER,
    EvalCase,
    check_live_reply,
    load_cases,
    sample_finance,
    wrong_meaning_llm,
)
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter

FOUNDER_MESSAGE = "Should we hire a designer?"
FACTS = [
    fact_for("headcount_cost", 308437.67, label="Headcount cost (monthly)", unit="USD"),
    fact_for("runway", 10.65, label="Runway (actual burn)", unit="months"),
    fact_for("net_burn", 172280.47, label="Net burn", unit="USD"),
    fact_for("gross_burn", 428612.47, label="Gross burn", unit="USD"),
    fact_for("gross_margin", 0.7213, label="Gross margin", unit="ratio"),
    fact_for("mrr", 255344.27, label="MRR", unit="USD"),
    *facts_from_fields(
        {
            "closing_cash": 1835125.06,
            "base_runway_months": 11.23,
            "scenario_runway_months": 9.81,
            "runway_change_months": -1.42,
            "final_month": {"delta": -137083.41, "base_cash": -120544.65},
            "impact": {"cost_per_hire_monthly": 11423.62, "monthly_cost_delta": 22847.24},
        }
    ),
    Fact(15.0),  # quoted from a note: its citation backs it, and nothing says what it means
]


def problems(text: str, message: str = FOUNDER_MESSAGE) -> list[str]:
    return [issue.message for issue in check_claims(text, FACTS, message)]


# --- the founder's sentence and its relatives ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        WRONG_MEANING_ANSWER,
        "The cost of hiring a designer is $308,437.67 per month.",
        "The monthly cost of a designer is $308,437.67.",
        "A designer would cost $308,437.67.",
        # Review findings: a comma or a sentence break must not lose the claim.
        "The monthly cost of hiring a designer, based on payroll, is $308,437.67.",
        "Hiring a designer: $308,437.67 a month.",
        "A designer is costly. That is $308,437.67 a month.",
        "Hiring a designer adds $308,437.67 a month.",
        "This would reduce runway by that amount.",
        "Your runway is $308,437.67.",
        "Runway is $10.65.",
        "Runway would be $9.81.",
        "The monthly cost of a designer is $137,083.41.",  # the scenario's cash difference at the end of the projection
        "Cash would be lower by $137,083.41 per month.",  # the same balance, as if it were monthly
        "The closing cash is $1,835,125.06 per month.",
        "Net burn is $428,612.47.",  # gross burn
        "Gross burn is $172,280.47.",  # net burn
        "MRR is $172,280.47.",
        "Gross margin is 10.65 months.",
        "Net burn is 172,280.47 months.",
        "Your cash is 10.65 USD.",
    ],
)
def test_a_figure_with_the_wrong_meaning_or_unit_fails(text: str) -> None:
    assert problems(text), text


def test_the_founders_sentence_is_not_verified() -> None:
    report = verify(WRONG_MEANING_ANSWER, FACTS, [], needs_citations=False, context=FOUNDER_MESSAGE)
    assert not report.ok
    assert report.unverified_numbers == []  # the value is real: that was the bug
    assert any("Headcount cost (monthly)" in issue for issue in report.issues)
    assert any("months" in issue for issue in report.issues)


@pytest.mark.parametrize(
    "text",
    [
        "Runway (actual burn) is 10.65 months.",
        "Your runway is 10.65 months.",
        "This would reduce runway by 1.42 months, from 11.23 to 9.81 months.",
        "You will run out of cash 1.42 months earlier.",
        "The cash lasts 10.65 months.",
        "Runway is -1.42 months versus the base case.",
        "Gross margin is 72.13 %.",
        "Gross margin is 72.13%, which is healthy.",
        "The note proposes a 15 % discount.",
        "The current net burn rate is $172,280.47 USD monthly.",
        "The current burn is $172,280.47.",
        "With $1,835,125.06 in cash that gives 10.65 months of runway.",
        "Runway with cash of $1,835,125.06 is 10.65 months.",
        "This is based on the closing cash balance and average net burn.",
        "Headcount cost is $308,437.67 a month.",
        "Total payroll is $308,437.67 per month.",
        "Payroll of $308,437.67 is your largest monthly cost.",
        "At the average loaded cost per hire of $11,423.62 a month, a designer adds $11,423.62.",
        "A designer would cost about $11,423.62 a month on average.",
        "Two hires raise monthly costs by $22,847.24.",
        "Two hires raise burn by $22,847.24 a month.",
        "Net burn rises by $22,847.24 a month.",
        "After the hire, cash at the end of the projection is $137,083.41 lower.",
        "A year from now that is $120,544.65 of cash shortfall.",
    ],
)
def test_a_figure_with_its_own_meaning_still_passes(text: str) -> None:
    assert problems(text) == []


def test_plain_numbers_and_quoted_passages_are_checked_by_value_only() -> None:
    assert check_claims("Runway is $308,437.67.", [308437.67]) == []
    assert verify("Runway is 10.65 months.", [10.65], [], needs_citations=False).ok


def test_the_founders_own_number_means_what_they_say() -> None:
    assert problems("A designer costs $308,437.67 a month.", "What if a designer costs $308,437.67 a month?") == []


def test_a_clause_that_names_nothing_is_only_checked_by_unit() -> None:
    assert problems("That is $172,280.47.", "How is it going?") == []
    assert problems("That is 172,280.47 months.", "How is it going?")


def test_a_field_keeps_its_label_and_unit() -> None:
    cost = next(f for f in FACTS if f.value == 308437.67)
    assert (cost.kind, cost.label, cost.stock) == ("money", "Headcount cost (monthly)", False)
    assert cost.concepts == {"payroll"}
    assert fact_for("runway_change_months", -0.76).kind == "months"
    assert fact_for("closing_cash", 5.0).stock
    assert fact_for("probability_cash_out_within_12_months", 0.4).kind == "ratio"
    assert cost.sentence() == "Headcount cost (monthly): $308,437.67."
    assert fact_for("gross_margin", 0.7213, label="Gross margin", unit="ratio").sentence() == "Gross margin: 72.13 %."


@pytest.mark.parametrize(
    ("message", "count"),
    [
        (FOUNDER_MESSAGE, 1),
        ("Should we hire an engineer?", 1),
        ("Should we hire two SDRs?", 2),
        ("What if we hire 3 more engineers?", 3),
        ("Should we hire another designer?", 1),
        ("Is hiring two more people wise?", 2),
        ("Should we hire?", None),
        ("Should we hire more?", None),
        ("We hired two people last year.", None),
        # Review findings: these do not say how many, or use a number word that was missing.
        ("Should we hire a couple of engineers?", None),
        ("Should we hire a few SDRs?", None),
        ("Is hiring a good idea?", None),
        ("Should we hire 20% more staff?", None),
        ("Should we hire eight SDRs?", 8),
        ("What's our runway?", None),
    ],
)
def test_counting_hires(message: str, count: int | None) -> None:
    assert hires_in_message(message) == count


@pytest.mark.parametrize(
    ("message", "text", "fails"),
    [
        ("Should we hire the designer?", "The headcount cost is $308,437.67 a month.", False),  # "the" is not a role
        ("Should we hire now?", "The headcount cost is $308,437.67 a month.", False),
        ("Should we hire a senior designer?", "The cost of a designer is $308,437.67.", True),  # not only "senior"
        ("Should we hire a senior designer?", "The headcount cost for a designer is $308,437.67.", True),
    ],
)
def test_the_role_comes_from_the_founders_words(message: str, text: str, fails: bool) -> None:
    assert bool(problems(text, message)) is fails


def test_a_query_column_name_proves_no_meaning() -> None:
    facts = [column_fact("churned_mrr", 12000.0), column_fact("total_cost", 900.0)]
    assert check_claims("$12,000 of MRR churned.", facts, "How much churned?") == []
    assert check_claims("Costs are $900 a month.", facts, "What are costs?") == []
    assert check_claims("A designer costs $900 a month.", facts, FOUNDER_MESSAGE)  # still not the cost of this hire


def test_field_names_that_look_alike_keep_their_own_meaning() -> None:
    assert fact_for("churned_mrr", 1.0).kind == "money"
    assert not fact_for("total_payroll", 1.0).stock
    assert check_claims("You paid $5,000 in cash.", [fact_for("total_cash_out", 5000.0)], "What did we pay?") == []
    assert fact_for("active_customers", 120.0, label="Active customers").sentence() == "Active customers: 120."
    assert fact_for("something", 3.0, label="Something").sentence() == "Something: 3.00."


def _scenario(cost: float | None = 11423.62) -> Any:
    assumptions = [] if cost is None else [SimpleNamespace(name="cost_per_hire", value=cost)]
    return SimpleNamespace(
        assumptions=assumptions,
        base_runway_months=11.23,
        scenario_runway_months=10.47,
        as_of="2026-10",
        currency="USD",
        growth_mode="trend",
    )


def test_a_stated_cost_is_not_called_the_average() -> None:
    impact = _decision_impact(_scenario(), Adjustments(new_hires=1, cost_per_hire_monthly=8000), -0.5)
    assert impact is not None
    assert impact.cost_per_hire_monthly == 8000
    assert not impact.cost_is_company_average
    assert "stated cost per hire of $8,000.00" in impact.sentence()
    assert "average" not in impact.sentence()


@pytest.mark.parametrize("cost", [None, 0.0])
def test_no_payroll_to_average_gives_no_impact_rather_than_a_free_hire(cost: float | None) -> None:
    assert _decision_impact(_scenario(cost), Adjustments(new_hires=1), 0.0) is None


def test_another_lever_means_the_runway_change_is_not_the_costs_alone() -> None:
    assert _decision_impact(_scenario(), Adjustments(new_hires=1, price_change_pct=10), 0.5) is None
    assert _decision_impact(_scenario(), Adjustments(new_hires=1), -0.76) is not None
    assert _decision_impact(_scenario(), Adjustments(new_hires=1, growth_mode="flat"), -0.76) is not None


def test_a_reply_in_pieces_does_not_repeat_the_replacement() -> None:
    gate = _SentenceGate(FACTS, FOUNDER_MESSAGE, None, issues := [])
    first = gate.feed("A designer costs $308,437.67 a month. ")
    second = gate.feed("So a designer costs $308,437.67. ") + gate.flush()
    assert first.count("Headcount cost (monthly)") == 1
    assert "Headcount cost" not in second
    assert "308,437.67 a month" not in first
    assert len(issues) == 2


def test_the_advisor_is_not_shown_the_replaced_figure() -> None:
    bad = "wrong meaning: $308,437.67 is Headcount cost (monthly) (money), not hire cost"
    result = AgentResult(
        agent_id="a",
        type="financial_analyst",
        name="Financial Analyst",
        brief="x",
        status="done",
        verified=False,
        text="Fine.",
        issues=[bad, "number without lineage: $5"],
    )
    findings = findings_for_advisor([result])
    assert "308,437.67" not in findings
    assert "replaced by one written in code" in findings
    assert "$5" not in findings


def test_the_code_written_impact_passes_its_own_check() -> None:
    impact = DecisionImpact(
        new_hires=1,
        cost_per_hire_monthly=11423.62,
        monthly_cost_delta=11423.62,
        base_runway_months=11.23,
        scenario_runway_months=10.47,
        runway_change_months=-0.76,
        as_of="2026-10",
        currency="USD",
        growth_mode="flat",
    )
    text = impact.sentence()
    assert "average" in text
    assert "-0.76 months" in text
    assert check_claims(text, facts_from_fields(impact.model_dump()), FOUNDER_MESSAGE) == []


# --- end to end, on the sample data ------------------------------------------------------------------------------
@pytest.fixture
def finance(tmp_path: Path) -> Any:
    fin = sample_finance(tmp_path)
    yield fin


def _runner(provider: FakeProvider, finance: Any) -> AgentRunner:
    return AgentRunner(LLMRouter(provider), EventBus(), "r", lambda aid: ToolContext(finance, None, aid))


ANALYST = AgentInstance(type="financial_analyst", name="Financial Analyst", brief="x", provider="fake")


async def test_the_analyst_runs_the_scenario_for_a_hire(finance: Any) -> None:
    provider = FakeProvider(["At the average cost, a designer moves runway from 11.23 to 10.47 months."])
    result = await _runner(provider, finance).run(ANALYST, FOUNDER_MESSAGE)
    assert result.tool_calls[0]["tool"] == "run_scenario"
    assert result.tool_calls[0]["arguments"] == {"new_hires": 1}
    assert result.decision_impact is not None
    assert result.decision_impact.cost_per_hire_monthly == pytest.approx(11423.62)
    assert result.decision_impact.monthly_cost_delta == pytest.approx(11423.62)
    assert result.decision_impact.runway_change_months == pytest.approx(-0.76)
    assert result.verified


async def test_the_decision_impact_multiplies_in_code(finance: Any) -> None:
    result = await _runner(FakeProvider(["Done."]), finance).run(ANALYST, "Should we hire two SDRs?")
    assert result.decision_impact is not None
    assert result.decision_impact.monthly_cost_delta == pytest.approx(22847.24)
    assert result.decision_impact.runway_change_months == pytest.approx(-1.42)


async def test_the_founders_scenario_is_the_impact_not_the_models_later_one(finance: Any) -> None:
    from app.llm.base import ToolCall

    other = ToolCall(name="run_scenario", arguments={"new_hires": 3})
    result = await _runner(FakeProvider([[other], "Done."]), finance).run(ANALYST, FOUNDER_MESSAGE)
    assert [c["arguments"]["new_hires"] for c in result.tool_calls] == [1, 3]
    assert result.decision_impact is not None
    assert result.decision_impact.new_hires == 1


async def test_a_money_query_is_labelled_by_column(finance: Any) -> None:
    sql = "SELECT CAST(12345.5 AS DOUBLE) AS churned_mrr"
    outcome = await run_tool("run_sql", ToolContext(finance, None, "a"), {"sql": sql}, {"run_sql"})
    assert outcome.facts == [column_fact("churned_mrr", 12345.5)]


async def test_a_question_without_a_hire_runs_no_scenario(finance: Any) -> None:
    result = await _runner(FakeProvider(["Noted."]), finance).run(ANALYST, "What's our runway?")
    assert result.decision_impact is None
    assert result.tool_calls == []


async def test_the_analysts_wrong_sentence_is_sent_back_then_replaced(finance: Any) -> None:
    result = await _runner(wrong_meaning_llm(), finance).run(ANALYST, FOUNDER_MESSAGE)
    assert not result.verified
    assert any("wrong meaning" in issue for issue in result.issues)
    assert "308,437.67" not in result.text
    assert "11,423.62" in result.text
    assert "10.47" in result.text


async def test_the_advisors_wrong_sentence_never_reaches_the_founder(finance: Any) -> None:
    provider = wrong_meaning_llm()
    result = await _runner(provider, finance).run(ANALYST, FOUNDER_MESSAGE)
    plan = Plan(intent="decision", team=[ANALYST], planner="test")
    issues: list[str] = []
    chunks = [c async for c in advise(LLMRouter(provider), FOUNDER_MESSAGE, plan, [result], issues)]
    answer = "".join(c.delta for c in chunks)
    assert "308,437.67" not in answer
    assert "that amount" not in answer
    assert "11,423.62" in answer
    assert issues
    done = [c for c in chunks if c.done]
    assert done[-1].completion is not None
    assert done[-1].completion.text == answer


async def test_the_advisor_keeps_good_sentences_and_states_the_impact_if_it_did_not(finance: Any) -> None:
    good = "Think about what a designer would change for customers. Then decide."
    provider = FakeProvider(["Done.", good])
    result = await _runner(provider, finance).run(ANALYST, FOUNDER_MESSAGE)
    plan = Plan(intent="decision", team=[ANALYST], planner="test")
    issues: list[str] = []
    answer = "".join([c.delta async for c in advise(LLMRouter(provider), FOUNDER_MESSAGE, plan, [result], issues)])
    assert answer.startswith(good)
    assert "11,423.62" in answer
    assert "10.47" in answer
    assert issues == []


async def test_a_stated_cost_per_hire_is_labelled_as_the_average(finance: Any) -> None:
    said = "Hiring a designer costs $11,423.62 per month and reduces runway by 0.76 months."
    provider = FakeProvider(["Done.", said])
    result = await _runner(provider, finance).run(ANALYST, FOUNDER_MESSAGE)
    plan = Plan(intent="decision", team=[ANALYST], planner="test")
    issues: list[str] = []
    answer = "".join([c.delta async for c in advise(LLMRouter(provider), FOUNDER_MESSAGE, plan, [result], issues)])
    assert answer.startswith(said)
    assert "average loaded monthly cost per person, not a quote for this role" in answer
    assert issues == []
    assert check_claims(answer, result.facts, FOUNDER_MESSAGE) == []


# --- the evals ---------------------------------------------------------------------------------------------------
def _designer() -> EvalCase:
    return next(case for case in load_cases() if case.id == "hire-a-designer")


def test_the_designer_question_is_in_the_eval_with_its_impact() -> None:
    case = _designer()
    assert case.impact["cost_per_hire_monthly"] == 11423.62
    assert case.impact["runway_change_months"] == -0.76
    assert "308,437.67" in case.not_in_answer


def test_the_live_check_reads_the_impact() -> None:
    case = _designer()
    good = dict(case.impact)
    reply: dict[str, Any] = {
        "answer": "Runway moves from 11.23 to 10.47 months.",
        "verified": True,
        "decision_impact": good,
    }
    assert check_live_reply(case, reply).passed
    assert not check_live_reply(case, {**reply, "decision_impact": None}).passed
    assert not check_live_reply(case, {**reply, "decision_impact": {**good, "runway_change_months": -2.0}}).passed
    assert not check_live_reply(case, {**reply, "answer": WRONG_MEANING_ANSWER}).passed
