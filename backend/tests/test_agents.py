from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.registry import REGISTRY, spawnable_types
from app.agents.runtime import AgentInstance, AgentRunner, plan, rule_intent, rule_metric
from app.agents.tools import TOOLS, ToolContext, run_tool
from app.config import PROJECT_ROOT
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.chunking import ApproxTokenizer
from app.engine.duckdb_engine import FinanceDB
from app.engine.embeddings import FakeEmbedder
from app.engine.hybrid_rag import HybridIndex
from app.engine.metrics import MetricsEngine
from app.engine.scenario import Adjustments, ScenarioEngine
from app.engine.vector_store import InMemoryVectorStore
from app.llm.base import Completion, LLMUnavailable, Message, ToolCall
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.vault.manager import VaultManager

RUNWAY_ANSWER = "Runway (actual burn) is 10.65 months as of 2026-10, at the trailing 3-month net burn."


class FakeVault:
    """The parts of VaultService the tools use."""

    def __init__(self, root: Path) -> None:
        shutil.copytree(PROJECT_ROOT / "sample_data" / "vault", root)
        self.vault = VaultManager(root)
        self.index = HybridIndex(self.vault, FakeEmbedder(), InMemoryVectorStore(), ApproxTokenizer())
        self.index.refresh()
        self.changed: list[set[str]] = []

    def ensure_started(self) -> None: ...

    def wait_ready(self) -> bool:
        return True

    def apply_changes(self, paths: set[str]) -> None:
        self.changed.append(paths)
        self.index.refresh(paths)


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


@pytest.fixture
def vault(tmp_path: Path) -> FakeVault:
    return FakeVault(tmp_path / "vault")


def ctx(finance: Any, vault: Any) -> ToolContext:
    return ToolContext(finance=finance, vault=vault, agent_id="agt_test")


def make_runner(provider: FakeProvider, finance: Any, vault: Any, bus: EventBus | None = None) -> AgentRunner:
    return AgentRunner(
        LLMRouter(provider), bus or EventBus(), "run_test", lambda aid: ToolContext(finance, vault, aid), max_steps=3
    )


def inst(agent_type: str, brief: str = "What's our runway?") -> AgentInstance:
    return AgentInstance(type=agent_type, name=REGISTRY[agent_type].title, brief=brief, provider="fake")


# --- registry and tools ----------------------------------------------------------------------------------------
def test_registry_has_the_five_core_agents_with_prompts() -> None:
    core = {"advisor", "planner", "financial_analyst", "librarian", "verifier"}
    assert core <= set(REGISTRY)
    assert set(spawnable_types()) == set(REGISTRY) - {"advisor", "planner", "verifier"}
    for spec in REGISTRY.values():
        assert spec.prompt().strip()
        assert all(tool in TOOLS for tool in spec.tools)
    assert all(REGISTRY[name].privacy == "local" for name in core)
    # Only the Financial Analyst may touch numbers (PRD F3).
    finance_tools = {"get_metric", "run_scenario", "run_monte_carlo", "run_sql"}
    assert [n for n, s in REGISTRY.items() if finance_tools & set(s.tools)] == ["financial_analyst"]


async def test_get_metric_tool_returns_runway_with_lineage(finance: Any) -> None:
    outcome = await run_tool("get_metric", ctx(finance, None), {"name": "runway"}, REGISTRY["financial_analyst"].tools)
    assert outcome.error is None and outcome.content["value"] == 10.65 and outcome.content["unit"] == "months"
    card = outcome.artifacts[0]
    assert card.kind == "metric_card" and card.data["lineage"]["sql"] and card.lineage[0].metric == "runway"
    assert 10.65 in outcome.numbers and "net_burn" in str(outcome.content["lineage"]["formula"]).lower().replace(
        " ", "_"
    )


async def test_tools_report_errors_instead_of_raising(finance: Any, vault: FakeVault) -> None:
    allowed = REGISTRY["financial_analyst"].tools
    sql = await run_tool("run_sql", ctx(finance, None), {"sql": "DROP TABLE pnl"}, allowed)
    assert sql.error and "SqlGuardError" in sql.error
    unknown = await run_tool("get_metric", ctx(finance, None), {"name": "happiness"}, allowed)
    assert unknown.error is not None
    not_allowed = await run_tool("search_vault", ctx(finance, vault), {"query": "x"}, allowed)
    assert not_allowed.error and "not available to this agent" in not_allowed.error


async def test_scenario_and_monte_carlo_tools(finance: Any) -> None:
    allowed = REGISTRY["financial_analyst"].tools
    scenario = await run_tool("run_scenario", ctx(finance, None), {"growth_mode": "none"}, allowed)
    assert scenario.error is None and scenario.content["base_runway_months"] == 9.69
    assert scenario.artifacts[0].kind == "scenario" and scenario.artifacts[0].lineage
    mc = await run_tool("run_monte_carlo", ctx(finance, None), {"runs": 200}, allowed)
    assert mc.error is None and mc.content["runs"] == 200 and mc.artifacts[0].kind == "monte_carlo"
    summary = await run_tool("metrics_summary", ctx(finance, None), {}, allowed)
    assert {m["metric"] for m in summary.content["metrics"]} >= {"runway", "mrr"} and len(summary.artifacts) >= 5


async def test_scenario_deltas_come_from_code_and_unseen_numbers_do_not_verify(finance: Any) -> None:
    """Live run: the model subtracted 11.23 - 9.81 itself and the answer still verified, because the Verifier
    accepted any number anywhere in the full scenario payload. Deltas now come from code, and only numbers the
    model was shown count as lineage-backed."""
    from app.agents.verifier import verify_numbers

    allowed = REGISTRY["financial_analyst"].tools
    outcome = await run_tool("run_scenario", ctx(finance, None), {"new_hires": 2}, allowed)
    c = outcome.content
    assert (c["base_runway_months"], c["scenario_runway_months"], c["runway_change_months"]) == (11.23, 9.81, -1.42)
    assert verify_numbers("Two hires cut runway by 1.42 months, to 9.81.", outcome.numbers) == []
    mid_point = outcome.artifacts[0].data["points"][5]["scenario_cash"]  # in the artifact, never shown to the model
    assert mid_point not in outcome.numbers
    assert verify_numbers(f"Cash in month 6 is ${mid_point:,.2f}.", outcome.numbers) == [f"${mid_point:,.2f}"]


async def test_librarian_tools_search_cite_and_write_only_decisions(finance: Any, vault: FakeVault) -> None:
    allowed = REGISTRY["librarian"].tools
    found = await run_tool("search_vault", ctx(finance, vault), {"query": "annual prepayment discount"}, allowed)
    assert found.content["results"][0]["path"] == "notes/pricing-strategy.md"
    assert found.citations[0].path == "notes/pricing-strategy.md" and found.artifacts[0].kind == "citation"
    note = await run_tool("read_note", ctx(finance, vault), {"path": "notes/pricing-strategy.md"}, allowed)
    assert note.error is None and note.citations[0].path == "notes/pricing-strategy.md"
    blocked = await run_tool("write_note", ctx(finance, vault), {"path": "profile/company.md", "content": "x"}, allowed)
    assert blocked.error and "decisions/" in blocked.error
    written = await run_tool(
        "write_note", ctx(finance, vault), {"path": "journal/2026-11-03.md", "content": "# Note\nzebra"}, allowed
    )
    assert written.content == {"written": "journal/2026-11-03.md"} and vault.changed == [{"journal/2026-11-03.md"}]


# --- runner ----------------------------------------------------------------------------------------------------
async def test_financial_analyst_calls_the_tool_and_is_verified(finance: Any) -> None:
    bus = EventBus()
    provider = FakeProvider([[ToolCall(name="get_metric", arguments={"name": "runway"})], RUNWAY_ANSWER])
    result = await make_runner(provider, finance, None, bus).run(inst("financial_analyst"), "What's our runway?")
    assert result.text == RUNWAY_ANSWER and result.verified and result.attempts == 1
    assert result.lineage[0].metric == "runway" and result.tool_calls[0]["tool"] == "get_metric"
    # The second call sent the tool result back to the model.
    tool_msg = provider.calls[1]["messages"][-1]
    assert tool_msg.role == "tool" and '"value": 10.65' in tool_msg.content
    types = [e.type for e in bus.history()]
    assert {"agent.status", "agent.step", "agent.tool_call", "agent.artifact", "agent.done"} <= set(types)
    steps = [e.data["step"] for e in bus.history() if e.type == "agent.step"]
    assert steps == ['running get_metric(name="runway")']


async def test_verifier_sends_invented_numbers_back_once(finance: Any) -> None:
    provider = FakeProvider(
        [[ToolCall(name="get_metric", arguments={"name": "runway"})], "Runway is 14.2 months.", RUNWAY_ANSWER]
    )
    result = await make_runner(provider, finance, None).run(inst("financial_analyst"), "What's our runway?")
    assert result.verified and result.attempts == 2 and result.text == RUNWAY_ANSWER
    assert "Verifier rejected" in provider.calls[2]["messages"][-1].content


async def test_verifier_flags_after_the_retry(finance: Any) -> None:
    provider = FakeProvider(["Runway is 14.2 months.", "Still 14.2 months."])
    result = await make_runner(provider, finance, None).run(inst("financial_analyst"), "What's our runway?")
    assert result.verified is False and result.attempts == 2
    assert result.issues == ["number without lineage: 14.2", "removed: unsupported source (1)"]
    assert "14.2" not in result.text


async def test_llm_down_falls_back_to_rules(finance: Any, vault: FakeVault) -> None:
    down = FakeProvider(default=lambda m, t, s: LLMUnavailable("Ollama not reachable"))
    result = await make_runner(down, finance, vault).run(inst("financial_analyst"), "What's our runway?")
    assert result.provider == "rules" and result.verified and "10.65 months" in result.text
    assert result.lineage[0].metric == "runway"
    lib = await make_runner(down, finance, vault).run(inst("librarian", "annual prepayment discount"), "x")
    assert lib.provider == "rules" and "[notes/pricing-strategy.md]" in lib.text and lib.verified


async def test_librarian_must_cite_returned_sources(finance: Any, vault: FakeVault) -> None:
    provider = FakeProvider(
        [
            [ToolCall(name="search_vault", arguments={"query": "annual discount"})],
            "Annual plans get a discount [notes/invented.md].",
            "Annual plans get a discount [notes/pricing-strategy.md].",
        ]
    )
    result = await make_runner(provider, finance, vault).run(inst("librarian", "annual discount"), "x")
    assert result.verified and result.attempts == 2
    assert "notes/pricing-strategy.md" in {c.path for c in result.citations}


async def test_numbers_in_a_planner_brief_are_not_lineage(finance: Any) -> None:
    """Review finding: the Planner (an LLM) wrote "$14,500/month" into a brief, and the analyst could repeat it."""
    provider = FakeProvider(["Each hire costs $14,500 a month.", "Each hire costs $14,500 a month."])
    brief = "Check if we can afford 3 hires at $14,500/month each"
    result = await make_runner(provider, finance, None).run(inst("financial_analyst", brief), "Can we hire?")
    assert result.verified is False and result.issues[0] == "number without lineage: $14,500"
    assert "14,500" not in result.text
    # The founder's own numbers may be repeated.
    ok = FakeProvider(["You asked about $14,500 a month per hire; I need data to check it."])
    founder = await make_runner(ok, finance, None).run(inst("financial_analyst", "b"), "Can we pay $14,500 each?")
    assert founder.verified


def test_rule_intent_and_metric() -> None:
    assert rule_intent("What's our runway?") == "finance"
    assert rule_intent("Should we hire two SDRs?") == "decision"
    assert rule_intent("I want to open a Dubai office") == "decision"
    assert rule_intent("What did my notes say about Fabrikam?") == "knowledge"
    assert rule_intent("hello!") == "chitchat"
    assert rule_intent("Tell me about Fabrikam") is None
    assert rule_metric("What's our runway?") == "runway"
    assert rule_metric("how is gross margin") == "gross_margin"
    assert rule_metric("LTV:CAC please") == "ltv_cac"
    assert rule_metric("weather") is None


# --- planner ---------------------------------------------------------------------------------------------------
async def test_planner_uses_rules_then_decision_model() -> None:
    router = LLMRouter(FakeProvider())
    decisions = DecisionService(
        FakeDecisionProvider(
            lambda state, q, options: ("knowledge" if "Fabrikam" in state["message"] else options[0], 0.9)
        )
    )
    finance_plan = await plan("What's our runway?", router, decisions)
    assert finance_plan.intent == "finance" and finance_plan.planner == "rules"
    assert [i.type for i in finance_plan.team] == ["financial_analyst"] and finance_plan.team[0].provider == "fake"
    fuzzy = await plan("Tell me about Fabrikam", router, decisions)
    assert fuzzy.intent == "knowledge" and fuzzy.planner.startswith("decision model")
    assert fuzzy.intent_decision_id is not None  # review finding: the id was dropped for finance/knowledge
    assert (await plan("hi", router, decisions)).team == []


async def test_low_confidence_intent_gets_the_default_team() -> None:
    """Review finding: DECISION_MIN_CONFIDENCE had no effect; a p=0.3 "chitchat" produced an empty team."""
    unsure = DecisionService(FakeDecisionProvider({}, probability=0.3), min_confidence=0.75)
    p = await plan("Tell me about Fabrikam", LLMRouter(FakeProvider()), unsure)
    assert p.intent == "decision" and [i.type for i in p.team] == ["financial_analyst", "librarian"]
    assert "unsure" in p.planner and p.intent_decision_id is not None


async def test_planner_survives_non_object_json() -> None:
    """Review finding: a JSON array from the planner raised AttributeError and failed the whole run."""
    p = await plan(
        "Should we hire?",
        LLMRouter(FakeProvider(['[{"agent_type": "librarian"}]'])),
        DecisionService(FakeDecisionProvider()),
    )
    assert p.planner.endswith("default team") and len(p.team) == 2


async def test_advisor_stream_cut_off_is_not_padded_with_a_template() -> None:
    """Review finding: a stream that broke mid-reply got the whole template answer appended."""
    from app.agents.runtime import Plan, advise
    from app.llm.base import LLMError, StreamChunk

    class Breaking(FakeProvider):
        async def _stream(self, messages, tools, json_schema):  # type: ignore[no-untyped-def]
            yield StreamChunk(delta="Your runway is")
            raise LLMError("connection dropped")

    chunks = [c async for c in advise(LLMRouter(Breaking()), "q", Plan(intent="finance", planner="rules"), [])]
    text = "".join(c.delta for c in chunks)
    assert text == "Your runway is (The reply was cut off; see the findings.)"
    assert chunks[-1].completion is not None and chunks[-1].completion.provider == "fake"
    assert "assembled without" not in text


async def test_planner_decision_team_from_llm_and_default() -> None:
    reply = (
        '{"decision_type": "hiring", "reversibility": "one_way", "tasks": ['
        '{"agent_type": "financial_analyst", "brief": "Runway after two SDR hires"},'
        '{"agent_type": "financial_analyst", "brief": "Monte Carlo of the hire"},'
        '{"agent_type": "fortune_teller", "brief": "ignored: not registered"},'
        '{"agent_type": "librarian", "brief": "Past SDR decision"}]}'
    )
    p = await plan(
        "Should we hire two SDRs?", LLMRouter(FakeProvider([reply])), DecisionService(FakeDecisionProvider())
    )
    assert p.decision_type == "hiring" and p.reversibility == "one_way"
    assert [(i.type, i.name) for i in p.team] == [
        ("financial_analyst", "Financial Analyst"),
        ("financial_analyst", "Financial Analyst #2"),
        ("librarian", "Librarian"),
    ]
    fallback = await plan(
        "Should we hire two SDRs?",
        LLMRouter(FakeProvider([LLMUnavailable("down")])),
        DecisionService(FakeDecisionProvider()),
    )
    assert fallback.planner.endswith("default team") and [i.type for i in fallback.team] == [
        "financial_analyst",
        "librarian",
    ]


# --- orchestrator (LangGraph) ----------------------------------------------------------------------------------
def orchestrator(provider: FakeProvider, finance: Any, vault: Any, **kwargs: Any) -> AgentOrchestrator:
    return AgentOrchestrator(
        LLMRouter(provider, kwargs.pop("cloud", None), cloud_allowed=kwargs.pop("cloud_allowed", False)),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, vault, aid),
        **kwargs,
    )


async def test_graph_runs_runway_end_to_end(finance: Any) -> None:
    provider = FakeProvider(
        [
            [ToolCall(name="get_metric", arguments={"name": "runway"})],
            RUNWAY_ANSWER,
            "Your runway is 10.65 months. What would you cut first if growth stalls?",
        ]
    )
    orch = orchestrator(provider, finance, None)
    run = orch.start("Walk me through our runway.")
    result = await run.task  # type: ignore[misc]
    assert result.answer.startswith("Your runway is 10.65 months") and result.verified and result.intent == "finance"
    assert result.metrics[0].value == 10.65 and result.metrics[0].lineage["metric"] == "runway"
    assert result.metrics[0].lineage["sql"] and result.metrics[0].label == "Runway (actual burn)"
    assert set(result.timings_ms) >= {"plan", "agents", "advise"} and result.elapsed_ms > 0
    deltas = []
    while (d := run.deltas.get_nowait()) is not None:
        deltas.append(d)
    assert "".join(deltas) == result.answer
    types = [e.type for e in orch.bus.history(run.run_id)]
    assert types[0] == "run.started" and types[-1] == "run.finished"
    assert types.index("team.proposed") < types.index("team.approved") < types.index("agent.spawned")


async def test_advisor_invented_number_is_flagged(finance: Any) -> None:
    provider = FakeProvider(
        [[ToolCall(name="get_metric", arguments={"name": "runway"})], RUNWAY_ANSWER, "You have 24 months of runway."]
    )
    result = await orchestrator(provider, finance, None).start("Walk me through our runway.").task  # type: ignore[misc]
    assert not result.verified and result.issues == ["advisor: removed: unsupported source (1)"]
    assert "24 months" not in result.answer and "10.65" in result.answer


async def test_fan_out_respects_the_local_cap(finance: Any) -> None:
    active = 0
    peak = 0

    async def slow(messages: list[Message], tools: Any, schema: Any) -> str:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.5)  # longer than the staggered start (each agent reads the month range from DuckDB)
        active -= 1
        return "No numbers here."

    tasks = ",".join(f'{{"agent_type": "financial_analyst", "brief": "b{i}"}}' for i in range(4))
    plan_reply = '{"decision_type": "x", "reversibility": "two_way", "tasks": [' + tasks + "]}"

    class SlowFake(FakeProvider):
        """Plans from the script; every agent call takes 0.5 s so overlapping calls can be counted."""

        async def _complete(self, messages, tools, json_schema):  # type: ignore[no-untyped-def]
            if json_schema is not None or not tools:
                return await super()._complete(messages, tools, json_schema)
            return Completion(text=await slow(messages, tools, None), provider="fake", model="m")

    orch = orchestrator(SlowFake([plan_reply]), finance, None, max_local=2)
    result = await orch.start("Should we expand?").task  # type: ignore[misc]
    assert [a.type for a in result.agents] == ["financial_analyst"] * 4 + ["librarian"] and peak == 2


async def test_team_approval_policy(finance: Any) -> None:
    orch = orchestrator(FakeProvider(), finance, None, approval_policy="always", approval_timeout_s=5)
    run = orch.start("Walk me through our runway trend over the last year.")  # 63: a plain lookup needs no approval
    for _ in range(100):
        if any(e.type == "team.proposed" for e in orch.bus.history(run.run_id)):
            break
        await asyncio.sleep(0.01)
    proposed = next(e for e in orch.bus.history(run.run_id) if e.type == "team.proposed")
    assert proposed.data["needs_approval"] is True and not run.task.done()  # type: ignore[union-attr]
    assert orch.approve(run.run_id, approved=False) and not orch.approve(run.run_id)
    result = await run.task  # type: ignore[misc]
    assert result.status == "rejected" and result.agents == [] and "not approved" in result.answer
    assert result.verification.state == "not_run"  # 51: held back, so no "Verified" badge
    assert any(e.type == "team.rejected" for e in orch.bus.history(run.run_id))


async def test_cloud_only_policy_waits_only_for_cloud_teams(finance: Any) -> None:
    cloud = FakeProvider(name="anthropic", is_cloud=True)
    local_only = orchestrator(FakeProvider(), finance, None, cloud=cloud, cloud_allowed=True)
    # Core agents are local-only, so even with cloud allowed the team starts at once (PRD R2).
    assert not local_only.needs_approval([inst("financial_analyst")])
    cloud_team = [inst("financial_analyst").model_copy(update={"is_cloud": True})]
    assert local_only.needs_approval(cloud_team)
    never = orchestrator(FakeProvider(), finance, None, approval_policy="never")
    assert not never.needs_approval(cloud_team)


async def test_approval_timeout_rejects(finance: Any) -> None:
    orch = orchestrator(FakeProvider(), finance, None, approval_policy="always", approval_timeout_s=0.05)
    run = orch.start("Walk me through our runway trend over the last year.")  # 63: a plain lookup needs no approval
    result = await run.task  # type: ignore[misc]
    assert result.status == "rejected"
    # Review finding: a timed-out approval still looked open and /approve answered 200.
    assert run.approval.is_set() and not orch.approve(run.run_id)


async def test_cancel_a_run(finance: Any) -> None:
    gate = asyncio.Event()

    async def wait(messages: Any, tools: Any, schema: Any) -> str:
        await gate.wait()
        return "never"

    class Blocking(FakeProvider):
        async def _complete(self, messages, tools, json_schema):  # type: ignore[no-untyped-def]
            from app.llm.base import Completion

            return Completion(text=await wait(messages, tools, json_schema), provider="fake", model="m")

    orch = orchestrator(Blocking(), finance, None)
    run = orch.start("What's our runway?")
    await asyncio.sleep(0.05)
    assert orch.cancel(run.run_id) and not orch.cancel("run_missing")
    with pytest.raises(asyncio.CancelledError):
        await run.task  # type: ignore[misc]
    assert orch.bus.history(run.run_id)[-1].data["status"] == "cancelled"


async def test_event_stream_survives_keepalive_timeouts() -> None:
    """Review finding: the /api/events keep-alive cancelled the generator; the stream died after 15 quiet seconds."""
    bus = EventBus()
    stream = bus.stream(keepalive_s=0.01).__aiter__()
    assert await stream.__anext__() is None
    assert await stream.__anext__() is None
    bus.emit("run.started", "r1")
    event = await stream.__anext__()
    while event is None:
        event = await stream.__anext__()
    assert event.type == "run.started"
    await stream.aclose()


async def test_event_bus_replays_and_filters() -> None:
    bus = EventBus()
    bus.emit("run.started", "r1")
    bus.emit("run.started", "r2")
    got: list[str] = []

    async def consume() -> None:
        async for event in bus.subscribe(run_id="r1"):
            got.append(f"{event.seq}:{event.type}")
            if event.type == "run.finished":
                return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    bus.emit("agent.status", "r2", "a", status="thinking")
    bus.emit("run.finished", "r1")
    await asyncio.wait_for(task, 1)
    assert got == ["1:run.started", "4:run.finished"]
    assert [e.seq for e in bus.history(since=2)] == [3, 4]


@pytest.mark.parametrize(
    "question",
    ["What's our MRR for January?", "What's our burn this quarter?", "How much runway do we need?"],
)
def test_a_question_about_another_period_or_a_target_is_not_a_lookup(question: str) -> None:
    from app.agents.runtime import single_metric

    assert single_metric(question) is None


@pytest.mark.parametrize(
    ("question", "metric"),
    [
        ("What is our runway?", "runway"),
        ("What's our net burn?", "net_burn"),
        ("Tell me our MRR", "mrr"),
        ("How long is our runway?", "runway"),
    ],
)
def test_a_plain_lookup_still_takes_the_fast_path(question: str, metric: str) -> None:
    from app.agents.runtime import single_metric

    assert single_metric(question) == metric


# --- founder review 49: a figure only for a period the projection covers -----------------------------------


def test_the_asked_period_is_read_from_the_question() -> None:
    from app.agents.horizon import asked_period

    assert asked_period("What will our MRR be in 2031?", "2026-10").end == "2031-12"  # type: ignore[union-attr]
    assert asked_period("What will MRR be next year?", "2026-10").end == "2027-12"  # type: ignore[union-attr]
    assert asked_period("Where is cash in 5 years?", "2026-10").end == "2031-10"  # type: ignore[union-attr]
    assert asked_period("MRR in March 2027?", "2026-10").end == "2027-03"  # type: ignore[union-attr]
    assert asked_period("What is our runway?", "2026-10") is None


@pytest.mark.parametrize(
    ("question", "label"),
    [
        ("What will our MRR be in 2031?", "2031"),
        ("What will our MRR be next year?", "next year"),
        ("What will our MRR be in 5 years?", "in 5 years"),
    ],
)
async def test_a_question_beyond_the_projection_never_gets_a_figure_for_that_date(
    finance: Any, question: str, label: str
) -> None:
    from app.agents.horizon import Projection

    scenario = finance.scenario.run(Adjustments(), horizon=12)
    projection = Projection.of(scenario)
    assert projection is not None and projection.months == 12
    last = f"${projection.mrr:,.2f}"
    provider = FakeProvider(
        [
            [ToolCall(name="run_scenario", arguments={})],
            f"Projected MRR {label} is {last}, with runway of 11.23 months.",
            f"Your MRR {label} is projected to be {last}. Growth could slow. What would change your plan?",
        ]
    )
    result = await orchestrator(provider, finance, None).start(question).task  # type: ignore[misc]
    assert result.answer.startswith("The model's projection runs to ")
    assert f"so it has no figure for {label}" in result.answer
    assert f"{last}, which assumes today's trend holds (assumption, confirm)" in result.answer
    assert result.answer.count(last) == 1  # only code's labelled month-12 figure, never "for 2031"
    analyst = next(r for r in result.agents if r.type == "financial_analyst")
    assert label not in analyst.text.lower() or last not in analyst.text
    assert result.verification.state != "verified"
    assert any(label in a for a in result.verification.assumptions)


async def test_a_question_inside_the_projection_is_answered_as_before(finance: Any) -> None:
    from app.agents.horizon import Projection, beyond

    projection = Projection.of(finance.scenario.run(Adjustments(), horizon=12))
    assert beyond("What will MRR be in 3 months?", projection) is None
    assert beyond("What will MRR be in 2031?", projection) is not None


def test_a_metric_answer_names_the_period_it_is_for() -> None:
    """Founder re-test 45: 0.90 % and 1.22 % were one metric over two periods, with no period said."""
    from app.agents.runtime import metric_sentence

    content = {
        "label": "Gross revenue churn (monthly)",
        "value": 0.009,
        "unit": "ratio",
        "as_of": "2026-10",
        "lineage": {"period": "2026-08..2026-10"},
    }
    assert "for August to October 2026" in metric_sentence(content, "gross_revenue_churn")
    point = {**content, "lineage": {"period": "2026-10"}}
    assert "as of October 2026" in metric_sentence(point, "gross_revenue_churn")
