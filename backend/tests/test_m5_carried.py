"""Carried from the M4 review into M5 (first task): 60, 61, 63 and 7. 62 is in test_decision_frame.py."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import app.agents.graph as graph_module
from app.agents.cash_risk import cash_risk, wants_warning
from app.agents.dedupe import without_repeats
from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.tools import ToolContext
from app.agents.verifier import split_sentences
from app.conversation.manager import ConversationManager
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from tests.test_specialists import _until, slow_provider


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


def _orchestrator(provider: Any, finance: Any, **kwargs: Any) -> AgentOrchestrator:
    return AgentOrchestrator(
        LLMRouter(provider),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, None, aid),
        **kwargs,
    )


# ---- 60: "Hold the team back" really stops the agents, and the lane does not say they are done
async def test_no_agent_runs_before_approval_and_none_after_a_rejection(
    finance: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real_run = graph_module.AgentRunner.run

    async def counted(self: Any, inst: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(inst.type)
        return await real_run(self, inst, *args, **kwargs)

    monkeypatch.setattr(graph_module.AgentRunner, "run", counted)
    orch = _orchestrator(slow_provider(), finance, approval_policy="always", approval_timeout_s=5)
    manager = ConversationManager(orch)
    outcome = await manager.turn(None, "Should we expand the team this year?")
    run = orch.runs[outcome.run_id or ""]
    await _until(lambda: any(e.type == "team.proposed" for e in orch.bus.history(run.run_id)))
    await asyncio.sleep(0.1)  # time for an agent to start, if one wrongly would
    assert calls == [] and not run.agent_tasks
    assert orch.approve(run.run_id, approved=False)
    result = await run.task  # type: ignore[misc]
    await _until(lambda: not manager.sessions[outcome.session_id].narrators)
    assert calls == [] and result.agents == [] and result.status == "rejected"
    assert not any(e.type in ("agent.spawned", "agent.started", "agent.done") for e in orch.bus.history(run.run_id))
    said = " ".join(manager.sessions[outcome.session_id].narration)
    assert " done" not in said and "no agent ran" in said


async def test_after_approval_the_agents_do_run(finance: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real_run = graph_module.AgentRunner.run

    async def counted(self: Any, inst: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(inst.type)
        return await real_run(self, inst, *args, **kwargs)

    monkeypatch.setattr(graph_module.AgentRunner, "run", counted)
    provider = slow_provider()
    orch = _orchestrator(provider, finance, approval_policy="always", approval_timeout_s=5)
    run = orch.start("Should we expand the team this year?")
    await _until(lambda: any(e.type == "team.proposed" for e in orch.bus.history(run.run_id)))
    assert calls == []
    assert orch.approve(run.run_id)
    await _until(lambda: bool(calls))
    provider.release.set()
    await run.task  # type: ignore[misc]
    assert set(calls) >= {"financial_analyst", "librarian"}


# ---- 61: "vs." does not end a sentence, so the near-duplicate pass cannot cut one in half
def test_vs_does_not_end_a_sentence() -> None:
    first = "The main trade-off is runway reduction vs. Your goal 'Decide whether to open Dubai'."
    text = f"{first} What matters more?"
    assert split_sentences(text)[0] == first
    goal = "Decide whether to open Dubai"
    out = without_repeats(text, [goal], [f"Your goal '{goal}' is open."])
    assert not out.rstrip().endswith("vs.")  # the whole sentence is kept or dropped, never half of it


# ---- 63: a one-metric question never waits for team approval
@pytest.mark.parametrize(
    "question", ["What is our gross revenue churn?", "What is our net revenue churn?", "What is our runway?"]
)
async def test_a_metric_lookup_needs_no_approval_even_when_always(finance: Any, question: str) -> None:
    orch = _orchestrator(FakeProvider(), finance, approval_policy="always", approval_timeout_s=5)
    run = orch.start(question)
    result = await asyncio.wait_for(run.task, timeout=5)  # type: ignore[arg-type]
    proposed = next(e for e in orch.bus.history(run.run_id) if e.type == "team.proposed")
    assert proposed.data["needs_approval"] is False and result.status == "done" and result.metrics


async def test_a_decision_still_waits_when_always(finance: Any) -> None:
    orch = _orchestrator(slow_provider(), finance, approval_policy="always", approval_timeout_s=5)
    run = orch.start("Should we expand the team this year?")
    await _until(lambda: any(e.type == "team.proposed" for e in orch.bus.history(run.run_id)))
    proposed = next(e for e in orch.bus.history(run.run_id) if e.type == "team.proposed")
    assert proposed.data["needs_approval"] is True
    orch.approve(run.run_id, approved=False)
    await run.task  # type: ignore[misc]


# ---- 7: the Advisor speaks up when cash may run out within 12 months
def test_cash_risk_sentence_carries_the_routines_figures(finance: Any) -> None:
    risk = cash_risk(finance, warn_at=0.0)
    assert risk is not None and 0 <= risk.probability <= 1
    assert f"{risk.percent:g} % of 1,000 simulated futures" in risk.sentence and "within 12 months" in risk.sentence
    assert risk.lineage.metric == "monte_carlo"
    assert cash_risk(finance, warn_at=2.0) is None  # off
    assert cash_risk(finance, warn_at=risk.probability + 0.01) is None  # below the line: silent


def test_only_decisions_and_cash_questions_get_the_warning() -> None:
    assert wants_warning("decision", [])
    assert wants_warning("finance", ["runway"]) and wants_warning("finance", ["net_burn"])
    assert not wants_warning("finance", ["mrr"]) and not wants_warning("chitchat", [])


async def test_a_runway_answer_warns_and_stays_verified(finance: Any) -> None:
    orch = _orchestrator(FakeProvider(["What would you cut first?"]), finance, cash_risk_warn_at=0.0)
    result = await orch.start("What is our runway?").task  # type: ignore[misc]
    assert result.cash_risk is not None and result.answer.rstrip().endswith(result.cash_risk.sentence)
    assert result.verification.state == "verified", result.issues
    quiet = _orchestrator(FakeProvider(["What would you cut first?"]), finance, cash_risk_warn_at=2.0)
    assert (await quiet.start("What is our runway?").task).cash_risk is None  # type: ignore[misc]


async def test_an_mrr_answer_has_no_warning(finance: Any) -> None:
    orch = _orchestrator(FakeProvider(["What drives it?"]), finance, cash_risk_warn_at=0.0)
    result = await orch.start("What is our MRR?").task  # type: ignore[misc]
    assert result.cash_risk is None and "simulated futures" not in result.answer
