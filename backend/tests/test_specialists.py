"""The M3b specialists: who joins a team, waves, what each always carries, the memo, cancel and re-run."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentRunner, advisor_decision_note, plan
from app.agents.specialists import (
    MemoDraft,
    MemoPrediction,
    calls_for_team,
    lens_name,
    memo_slug,
    memo_title,
    risks_from_text,
    team_for_message,
    with_required_fields,
    without_unbacked_figures,
)
from app.agents.tools import ToolContext
from app.agents.verifier import Fact
from app.config import Settings
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.llm.base import LLMUnavailable, ToolCall
from app.llm.costs import CallRecord
from app.llm.fake import FakeProvider, schema_example
from app.llm.router import LLMRouter
from app.main import create_app
from tests.test_agents import FakeVault
from tests.test_past_decisions import make_vault

DUBAI = "Should we open a Dubai office? Write a decision memo."


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


def orchestrator(provider: FakeProvider, finance: Any, vault: Any, **kwargs: Any) -> AgentOrchestrator:
    return AgentOrchestrator(
        LLMRouter(provider),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, vault, aid),
        **kwargs,
    )


def instance(agent_type: str, brief: str = "b") -> AgentInstance:
    spec = REGISTRY[agent_type]
    return AgentInstance(
        id=f"agt_{agent_type}",
        type=agent_type,
        name=spec.title,
        brief=brief,
        tools=list(spec.tools),
        privacy=spec.privacy,
        provider="fake",
        model="m",
        is_cloud=False,
    )


def runner(provider: FakeProvider, finance: Any, vault: Any, bus: EventBus | None = None) -> AgentRunner:
    return AgentRunner(LLMRouter(provider), bus or EventBus(), "run_t", lambda aid: ToolContext(finance, vault, aid))


@pytest.fixture
def empty_vault(tmp_path: Path) -> FakeVault:
    return FakeVault(tmp_path / "empty")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


# --- who joins a team -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (DUBAI, {"market_scout", "regulatory_tax", "devils_advocate", "memo_writer"}),
        ("What is our runway?", set()),
        ("Should we raise prices by 10%?", {"revenue_customer"}),
        ("Rank these three projects", {"prioritiser"}),
        ("How would an investor see this?", {"perspective_lens"}),
        ("Run a pre-mortem on the launch", {"devils_advocate"}),
        ("Is there a key-person problem in sales?", {"people_ops"}),
        ("Do we need a VAT licence?", {"regulatory_tax"}),
    ],
)
def test_the_founders_words_call_for_specialists(message: str, expected: set[str]) -> None:
    assert set(team_for_message(message)) == expected


async def test_a_dubai_team_has_every_specialist_even_when_the_model_leaves_them_out() -> None:
    reply = json.dumps(
        {
            "decision_type": "market",
            "reversibility": "one_way",
            "tasks": [{"agent_type": "librarian", "brief": "Past decisions on new offices"}],
        }
    )
    planned = await plan(DUBAI, LLMRouter(FakeProvider([reply])), DecisionService(FakeDecisionProvider()))
    types = [i.type for i in planned.team]
    assert set(types) >= {
        "librarian",
        "financial_analyst",
        "market_scout",
        "regulatory_tax",
        "devils_advocate",
        "memo_writer",
    }


async def test_the_default_team_includes_them_when_the_model_is_down() -> None:
    planned = await plan(
        DUBAI, LLMRouter(FakeProvider([LLMUnavailable("down")])), DecisionService(FakeDecisionProvider())
    )
    assert {"devils_advocate", "memo_writer", "market_scout"} <= {i.type for i in planned.team}


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What is our churn?", False),
        ("What do my notes say about our pricing?", False),
        ("What does the competitor pricing say?", False),
        ("What is our runway?", False),
        ("What would a discount do to churn?", True),
        ("Who are our competitors in the Dubai market?", True),
        ("Run a pre-mortem on the launch", True),
        ("What do my notes say about risks?", False),
    ],
)
def test_a_plain_lookup_stays_a_lookup(message: str, expected: bool) -> None:
    assert calls_for_team(message) is expected


async def test_a_metric_question_keeps_its_one_agent_team() -> None:
    planned = await plan("What is our churn?", LLMRouter(FakeProvider()), DecisionService(FakeDecisionProvider()))
    assert [i.type for i in planned.team] == ["financial_analyst"]


def test_a_lens_is_named_after_its_viewpoint() -> None:
    assert lens_name("Investor: would you fund this?") == "Investor"
    assert lens_name("how would the largest customer react") == "Largest customer"
    assert lens_name("no viewpoint named") is None


def test_every_specialist_has_a_prompt_and_only_known_stages() -> None:
    for name in (
        "devils_advocate",
        "market_scout",
        "revenue_customer",
        "people_ops",
        "regulatory_tax",
        "prioritiser",
        "memo_writer",
        "perspective_lens",
    ):
        assert REGISTRY[name].prompt().strip() and REGISTRY[name].spawnable
    assert REGISTRY["memo_writer"].stage > REGISTRY["devils_advocate"].stage > REGISTRY["people_ops"].stage
    assert REGISTRY["people_ops"].stage > REGISTRY["financial_analyst"].stage


# --- what each one carries --------------------------------------------------------------------------------------------
def test_a_risk_register_reads_lines_and_survives_prose() -> None:
    risks = risks_from_text(
        "- Risk: nobody buys. Likelihood: High. Impact: high. Mitigation: pilot first.\n- Costs run over."
    )
    assert risks[0] == {"risk": "nobody buys", "likelihood": "high", "impact": "high", "mitigation": "pilot first"}
    assert risks[1]["risk"] == "Costs run over" and risks[1]["likelihood"] == "not rated"
    assert len(risks_from_text("It fails. The team leaves.")) == 2


async def test_the_devils_advocate_gives_a_risk_register(finance: Any, vault: Any) -> None:
    reply = "- Risk: demand is not there. Likelihood: medium. Impact: high. Mitigation: a small pilot."
    result = await runner(FakeProvider([reply]), finance, vault).run(instance("devils_advocate"), DUBAI)
    register = next(a for a in result.artifacts if a.kind == "risk_register")
    assert register.data["risks"][0]["mitigation"] == "a small pilot" and result.verified


async def test_the_devils_advocate_has_no_model_rules_with_no_figures(finance: Any, vault: Any) -> None:
    result = await runner(FakeProvider([LLMUnavailable("down")]), finance, vault).run(
        instance("devils_advocate"), DUBAI
    )
    assert result.provider == "rules" and result.verified and "Risk:" in result.text
    assert len(next(a for a in result.artifacts if a.kind == "risk_register").data["risks"]) == 3


async def test_the_market_scout_says_it_only_had_the_vault_when_cloud_is_off(finance: Any, vault: Any) -> None:
    seen: list[Any] = []

    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        seen.append([t.name for t in tools or []])
        return "The vault has no market data for Dubai."

    result = await runner(FakeProvider(default=respond), finance, vault).run(instance("market_scout"), DUBAI)
    assert "web_search" not in seen[0] and "cloud is off" in result.text


async def test_the_market_scout_uses_web_search_with_a_cloud_key(finance: Any, vault: Any) -> None:
    from app.llm.base import Completion, WebAnswer, WebSource

    class Cloud(FakeProvider):
        supports_web_search = True

        async def web_search(self, query: str) -> WebAnswer:
            return WebAnswer(
                text="Dubai has 3 free zones for software firms.",
                sources=[WebSource(url="https://example.test/zones", title="Zones")],
                completion=Completion(text="", provider="cloud", model="m"),
            )

    cloud = Cloud(
        [
            [ToolCall(name="web_search", arguments={"query": "Dubai software free zones"})],
            "Dubai has 3 free zones for software firms.",
        ],
        name="cloud",
        model="m",
        is_cloud=True,
    )
    router = LLMRouter(FakeProvider(), cloud, cloud_allowed=True)
    result = await AgentRunner(router, EventBus(), "run_t", lambda aid: ToolContext(finance, vault, aid)).run(
        instance("market_scout"), DUBAI
    )
    assert result.verified, result.issues
    assert "https://example.test/zones" in result.text and "cloud is off" not in result.text


async def test_a_web_search_never_runs_on_a_local_only_type(finance: Any, vault: Any) -> None:
    outcome = await runner(FakeProvider(), finance, vault)._search_web(
        REGISTRY["market_scout"], instance("market_scout"), ToolCall(name="web_search", arguments={"query": "x"})
    )
    assert outcome.error and "vault" in outcome.error


async def test_regulatory_always_says_it_is_not_advice(finance: Any, vault: Any) -> None:
    result = await runner(FakeProvider(["Check the free zone licence with a lawyer."]), finance, vault).run(
        instance("regulatory_tax"), DUBAI
    )
    assert "not legal or tax advice" in result.text


async def test_the_prioritiser_is_sent_back_to_the_routine_when_it_ranks_in_prose(finance: Any, vault: Any) -> None:
    scoring = {
        "criteria": [
            {"name": "value", "weight": 1, "axis": "value"},
            {"name": "ease", "weight": 1, "axis": "feasibility"},
        ],
        "options": [
            {"name": "A", "scores": {"value": 5, "ease": 4}},
            {"name": "B", "scores": {"value": 2, "ease": 2}},
        ],
    }
    provider = FakeProvider(
        [
            "A is better than B.",
            [ToolCall(name="weighted_scoring", arguments=scoring)],
            "The routine ranks A first. I used equal weights: how much do value and ease each matter to you?",
        ]
    )
    result = await runner(provider, finance, vault).run(instance("prioritiser"), "Rank A and B")
    assert any(a.kind == "priority_matrix" for a in result.artifacts), result.tool_calls
    assert "equal weights" in result.text


async def test_a_specialists_invented_number_is_still_caught(finance: Any, vault: Any) -> None:
    result = await runner(FakeProvider(["Payroll rises by $91,234.", "Payroll rises by $91,234."]), finance, vault).run(
        instance("people_ops"), "Should we restructure the team?"
    )
    assert not result.verified and result.attempts == 2


async def test_a_specialist_may_use_the_numbers_an_earlier_stage_found(finance: Any, vault: Any) -> None:
    analyst = await runner(
        FakeProvider([[ToolCall(name="get_metric", arguments={"name": "mrr"})], "MRR is known."]), finance, vault
    ).run(instance("financial_analyst"), "MRR?")
    mrr = analyst.artifacts[0].data["value"]
    seen: list[str] = []

    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        seen.append(messages[-1].content)
        return (
            f"- Risk: MRR of ${mrr:,.2f} is too small to fund this. Likelihood: medium. Impact: high. Mitigation: wait."
        )

    result = await runner(FakeProvider(default=respond), finance, vault).run(
        instance("devils_advocate"), DUBAI, [analyst]
    )
    assert "Team findings so far" in seen[0]
    assert result.verified, result.issues


# --- small items from the M3a re-test --------------------------------------------------------------------------------
JOURNAL_QUESTION = "What did my journal say about the logistics customers?"


async def test_asked_about_my_journal_the_answer_uses_the_journal(finance: Any, vault: Any) -> None:
    # Seen live: the search found the journal, the model cited only the churn note.
    calls = [ToolCall(name="search_vault", arguments={"query": JOURNAL_QUESTION})]
    provider = FakeProvider([calls, "Two customers cited budget freezes [notes/customer-churn.md]."])
    result = await runner(provider, finance, vault).run(instance("librarian"), JOURNAL_QUESTION)
    assert "journal/2026-10-28.md" in result.text and "From your journal" in result.text
    assert result.verified, result.issues


async def test_an_answer_that_already_used_the_journal_gets_nothing_added(finance: Any, vault: Any) -> None:
    calls = [ToolCall(name="search_vault", arguments={"query": JOURNAL_QUESTION})]
    provider = FakeProvider([calls, "The follow-up went to the customer success lead [journal/2026-10-28.md]."])
    result = await runner(provider, finance, vault).run(instance("librarian"), JOURNAL_QUESTION)
    assert "From your journal" not in result.text


def test_json_answers_say_they_are_utf8(client: TestClient) -> None:
    assert client.get("/api/agents").headers["content-type"] == "application/json; charset=utf-8"


def test_the_agents_api_shows_cost_and_latency_per_type(client: TestClient) -> None:
    ledger = client.app.state.orchestrator.router.ledger  # type: ignore[attr-defined]
    ledger.record(
        CallRecord(
            agent_type="market_scout",
            provider="anthropic",
            model="claude-sonnet-5-5",
            is_cloud=True,
            input_tokens=1000,
            output_tokens=100,
            latency_ms=1200.0,
            est_cost_usd=0.003,
        )
    )
    body = client.get("/api/agents").json()
    scout = next(a for a in body["agents"] if a["type"] == "market_scout")
    assert scout["this_month"]["cloud_calls"] == 1 and scout["this_month"]["latency_ms_mean"] == 1200.0
    assert body["cloud"]["spent_usd"] == pytest.approx(0.003)


def test_the_cancel_and_rerun_api_refuses_what_is_not_running(client: TestClient) -> None:
    assert client.post("/api/runs/run_nope/agents/agt_x/cancel").status_code == 409
    assert client.post("/api/runs/run_nope/agents/agt_x/rerun", json={"brief": "x"}).status_code == 409


# --- the memo ---------------------------------------------------------------------------------------------------------
SIX_MONTHS = (dt.date.today() + dt.timedelta(days=180)).isoformat()
GOOD_MEMO = {
    "title": "Open a Dubai office",
    "chosen": "Travel-led pilot",
    "why_chosen": "It tests demand before you commit to premises.",
    "context": "You asked about Dubai.",
    "options": [{"name": "Full office", "note": "Hard to undo this early."}],
    "assumptions": ["Two customers would follow"],
    "predictions": [{"metric": "Dubai customers signed", "threshold": ">= 1", "by": SIX_MONTHS, "probability": 0.6}],
    "kill_criteria": [{"metric": "Dubai customers signed", "threshold": "< 1", "by": SIX_MONTHS}],
}


async def test_the_memo_writer_writes_a_memo_with_a_prediction_and_review_date(finance: Any, vault: Any) -> None:
    result = await runner(FakeProvider([json.dumps(GOOD_MEMO)]), finance, vault).run(instance("memo_writer"), DUBAI)
    assert result.verified and result.memo is not None
    review = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    assert result.memo.review_date == review and result.memo.status == "proposed"
    assert result.memo.path == f"decisions/{dt.date.today().isoformat()}-open-dubai-office.md"
    text = (vault.vault.root / result.memo.path).read_text(encoding="utf-8")
    assert f"review_date: '{review}'" in text or f"review_date: {review}" in text
    assert f"60%: Dubai customers signed >= 1 by {SIX_MONTHS}" in text and "status: proposed" in text
    stored = finance.calibration.list()
    assert stored[0].statement.startswith("Dubai customers") and stored[0].decision == result.memo.path
    assert stored[0].resolve_by.isoformat() == SIX_MONTHS
    assert any(a.kind == "decision_memo" for a in result.artifacts)
    assert result.memo.path in result.text and review in result.text


async def test_a_memo_on_record_is_a_proposal_not_a_decision(finance: Any, vault: Any) -> None:
    result = await runner(FakeProvider([json.dumps(GOOD_MEMO)]), finance, vault).run(instance("memo_writer"), DUBAI)
    assert result.memo is not None
    vault.index.refresh([result.memo.path], dense=False)
    record = next(r for r in vault.index.past_decisions("Dubai office") if r.path == result.memo.path)
    assert not record.is_decided and "not decided yet" in record.summary() and " decided 20" not in record.summary()
    assert "You already decided" not in advisor_decision_note("", [SimpleNamespace(past_decisions=[record])])  # type: ignore[list-item]


async def test_a_second_memo_never_overwrites_the_first(finance: Any, vault: Any) -> None:
    run = runner(FakeProvider([json.dumps(GOOD_MEMO), json.dumps(GOOD_MEMO)]), finance, vault)
    first = await run.run(instance("memo_writer"), DUBAI)
    second = await run.run(instance("memo_writer"), DUBAI)
    assert first.memo and second.memo and first.memo.path != second.memo.path
    assert second.memo.path.endswith("-2.md")


async def test_a_memo_with_no_model_is_honest_about_what_is_missing(finance: Any, vault: Any) -> None:
    result = await runner(FakeProvider([LLMUnavailable("down")]), finance, vault).run(instance("memo_writer"), DUBAI)
    assert result.memo is not None and result.provider == "rules"
    assert "starter" in result.memo.predictions[0] and "Dubai pipeline" in result.memo.predictions[0]
    assert all("starter" in k and k.startswith("Stop if") for k in result.memo.kill_criteria)


async def test_a_memo_with_an_invented_figure_goes_back_and_then_lists_it(finance: Any, vault: Any) -> None:
    bad = {**GOOD_MEMO, "context": "An office costs $48,123 a month."}
    result = await runner(FakeProvider([json.dumps(bad), json.dumps(bad)]), finance, vault).run(
        instance("memo_writer"), DUBAI
    )
    assert result.attempts == 2 and not result.verified and result.memo is not None and not result.memo.verified
    text = (vault.vault.root / result.memo.path).read_text(encoding="utf-8")
    body = text.split("## Open numbers to confirm")
    assert "48,123" not in body[0] and "48,123" in body[1].split("## Metrics")[0] and "verified: false" in text
    assert "[figure removed" not in text


async def test_the_memo_lists_the_teams_metrics_with_lineage(finance: Any, vault: Any) -> None:
    analyst = await runner(
        FakeProvider([[ToolCall(name="get_metric", arguments={"name": "arpa"})], "ARPA is known."]), finance, vault
    ).run(instance("financial_analyst"), "ARPA?")
    result = await runner(FakeProvider([json.dumps(GOOD_MEMO)]), finance, vault).run(
        instance("memo_writer"), DUBAI, [analyst]
    )
    assert result.memo is not None
    text = (vault.vault.root / result.memo.path).read_text(encoding="utf-8")
    assert "ARPA is $" in text and "subscriptions.csv" in text and "No metrics were computed" not in text
    assert "- - " not in text and "formula:" not in text


def test_memo_names_and_figures() -> None:
    assert memo_title("Should we open a Dubai office? Write it up.") == "Open a Dubai office"
    assert memo_slug("Open a Dubai office") == "open-dubai-office"
    # What the model wrote on the founder's PC: the file name should not repeat it.
    titled = with_required_fields(MemoDraft(title="Decision Memo: Should We Open a Dubai Office?"), "q")
    assert titled.title == "Open a Dubai Office"
    draft = MemoDraft(
        title="T", context="Costs $9,999 of $1,000.", predictions=[MemoPrediction(statement="s", probability=70)]
    )
    assert draft.predictions[0].probability == pytest.approx(0.7)
    kept = without_unbacked_figures(draft, [Fact(1000.0)], "")
    assert kept.context == "" and kept.open_numbers == ["Costs $9,999 of $1,000."]


def test_a_figure_with_no_source_moves_its_sentence_and_leaves_the_rest() -> None:
    kept = without_unbacked_figures(MemoDraft(context="Revenue was $1,150. Rent is 1,500 more."), [Fact(1150.0)], "")
    assert kept.context == "Revenue was $1,150." and kept.open_numbers == ["Rent is 1,500 more."]
    whole = without_unbacked_figures(MemoDraft(context="$48,123 then $48."), [Fact(48123.0), Fact(48.0)], "")
    assert whole.context == "$48,123 then $48." and whole.open_numbers == []


async def test_a_starter_is_not_stored_as_a_forecast(finance: Any, vault: Any) -> None:
    result = await runner(FakeProvider([LLMUnavailable("down")]), finance, vault).run(instance("memo_writer"), DUBAI)
    assert result.memo is not None and finance.calibration.list() == []


async def test_a_memo_needs_a_vault(finance: Any) -> None:
    result = await runner(FakeProvider([json.dumps(GOOD_MEMO)]), finance, None).run(instance("memo_writer"), DUBAI)
    assert result.status == "failed" and result.memo is None and not result.verified


# --- a whole team -----------------------------------------------------------------------------------------------------
async def test_the_whole_dubai_run_goes_in_waves_and_ends_with_a_memo(finance: Any, vault: Any) -> None:
    order: list[str] = []

    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        if schema is not None and "predictions" in schema.get("properties", {}):
            order.append("memo")
            return json.dumps(GOOD_MEMO)
        if schema is not None:
            return json.dumps(schema_example(schema))
        first = messages[0].content
        for marker, name in (("Devil's Advocate", "devil"), ("Market Scout", "scout"), ("Regulatory", "regulatory")):
            if marker in first:
                order.append(name)
        return "- Risk: it fails. Likelihood: medium. Impact: high. Mitigation: a pilot."

    orch = orchestrator(FakeProvider(default=respond), finance, vault)
    result = await orch.start(DUBAI).task  # type: ignore[misc]
    types = {a.type for a in result.agents}
    assert {"market_scout", "regulatory_tax", "devils_advocate", "memo_writer"} <= types
    assert order.index("scout") < order.index("regulatory") < order.index("devil") < order.index("memo")
    assert result.memo is not None and result.memo.path in result.answer
    assert result.memo.review_date in result.answer
    assert result.est_cost_usd == 0.0


# --- cancel and re-run ------------------------------------------------------------------------------------------------
class Slow(FakeProvider):
    """Agent calls wait until `release` is set; plans and decisions answer at once."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.release = asyncio.Event()
        self.briefs: list[str] = []

    async def _complete(self, messages, tools, json_schema):  # type: ignore[no-untyped-def]
        if json_schema is None and any("Brief:" in m.content for m in messages):
            self.briefs.append(messages[-1].content)
            await self.release.wait()
        return await super()._complete(messages, tools, json_schema)


def slow_provider() -> Slow:
    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        if schema is not None:
            return json.dumps(
                {
                    "decision_type": "x",
                    "reversibility": "two_way",
                    "tasks": [
                        {"agent_type": "financial_analyst", "brief": "first"},
                        {"agent_type": "librarian", "brief": "second"},
                    ],
                }
            )
        return "No numbers here."

    return Slow(default=respond)


async def _until(condition: Any) -> None:
    for _ in range(400):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


async def test_cancelling_one_agent_leaves_the_team_working(finance: Any, empty_vault: FakeVault) -> None:
    provider = slow_provider()
    orch = orchestrator(provider, finance, empty_vault)
    run = orch.start("Should we expand the team this year?")
    await _until(lambda: len(run.agent_tasks) == 2)
    analyst = next(i for i in run.plan.team if i.type == "financial_analyst")  # type: ignore[union-attr]
    assert orch.cancel_agent(run.run_id, analyst.id)
    await _until(lambda: analyst.id not in run.agent_tasks)
    provider.release.set()
    result = await run.task  # type: ignore[misc]
    statuses = {a.type: a.status for a in result.agents}
    assert statuses["financial_analyst"] == "cancelled" and statuses["librarian"] == "done"
    assert not orch.cancel_agent(run.run_id, analyst.id)


async def test_rerun_restarts_a_running_agent_with_the_edited_brief(finance: Any, empty_vault: FakeVault) -> None:
    provider = slow_provider()
    orch = orchestrator(provider, finance, empty_vault)
    run = orch.start("Should we expand the team this year?")
    await _until(lambda: len(run.agent_tasks) == 2)
    analyst = next(i for i in run.plan.team if i.type == "financial_analyst")  # type: ignore[union-attr]
    outcome = orch.rerun_agent(run.run_id, analyst.id, "only payroll")
    assert outcome is not None and outcome.restarted
    await _until(lambda: any("only payroll" in b for b in provider.briefs))
    provider.release.set()
    result = await run.task  # type: ignore[misc]
    rerun = next(a for a in result.agents if a.type == "financial_analyst")
    assert rerun.brief == "only payroll" and rerun.status == "done"
    assert any(e.type == "agent.rerun" for e in orch.bus.history(run.run_id))


async def test_rerun_after_the_run_finished_starts_a_new_run_with_the_edited_brief(
    finance: Any, empty_vault: FakeVault
) -> None:
    provider = slow_provider()
    provider.release.set()
    orch = orchestrator(provider, finance, empty_vault)
    run = orch.start("Should we expand the team this year?")
    await run.task  # type: ignore[misc]
    analyst = next(i for i in run.plan.team if i.type == "financial_analyst")  # type: ignore[union-attr]
    outcome = orch.rerun_agent(run.run_id, analyst.id, "only payroll")
    assert outcome is not None and not outcome.restarted and outcome.run_id != run.run_id
    second = await orch.runs[outcome.run_id].task  # type: ignore[misc]
    briefs = {a.type: a.brief for a in second.agents}
    assert briefs["financial_analyst"] == "only payroll" and briefs["librarian"] == "second"


async def test_rerun_of_a_finished_agent_in_a_running_team_is_refused(finance: Any, empty_vault: FakeVault) -> None:
    provider = slow_provider()
    orch = orchestrator(provider, finance, empty_vault)
    run = orch.start("Should we expand the team this year?")
    await _until(lambda: len(run.agent_tasks) == 2)
    analyst = next(i for i in run.plan.team if i.type == "financial_analyst")  # type: ignore[union-attr]
    orch.cancel_agent(run.run_id, analyst.id)
    await _until(lambda: analyst.id not in run.agent_tasks)
    assert orch.rerun_agent(run.run_id, analyst.id, "x") is None
    assert orch.rerun_agent(run.run_id, "agt_nope", "x") is None
    provider.release.set()
    await run.task  # type: ignore[misc]


async def test_cancelling_the_whole_run_still_cancels(finance: Any, empty_vault: FakeVault) -> None:
    provider = slow_provider()
    orch = orchestrator(provider, finance, empty_vault)
    run = orch.start("Should we expand the team this year?")
    await _until(lambda: len(run.agent_tasks) == 2)
    assert orch.cancel(run.run_id)
    with pytest.raises(asyncio.CancelledError):
        await run.task  # type: ignore[misc]
    assert any(e.type == "run.finished" and e.data["status"] == "cancelled" for e in orch.bus.history(run.run_id))
