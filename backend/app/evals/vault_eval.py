"""Eval over the sample vault: do the right sources and facts reach the founder?

Offline, no Ollama (pytest and `scripts/eval_vault.py`): each question runs twice over the sample vault with keyword
search, so ranking is deterministic.
- `rules`: the LLM is down, so the Librarian answers from its template (PRD R3).
- `careless`: a fake LLM searches, ignores what it finds and names no source. This is the failure the founder saw, and
  the code must still surface a past decision, and must not cite what the answer did not use.

A case with `impact` is a decision: the Financial Analyst and the Advisor run over the sample finance data, and the
code-computed impact must match. In `careless` the fake LLM writes the sentence the founder saw, and it must not reach
the answer.

Live (`scripts/eval_vault.py --live`): the same questions through `POST /api/chat` on a running backend, so with
the real model and embeddings. Model output varies, so a failure there is a prompt to read the answer, not a proof.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.agents.events import EventBus
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentResult, AgentRunner, Plan, advise
from app.agents.tools import ToolContext
from app.config import PROJECT_ROOT
from app.engine.calibration import CalibrationStore
from app.engine.chunking import ApproxTokenizer
from app.engine.duckdb_engine import FinanceDB
from app.engine.embeddings import FakeEmbedder
from app.engine.hybrid_rag import HybridIndex
from app.engine.ingest import ingest_directory
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.llm.base import LLMUnavailable, ToolCall
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.vault.manager import VaultManager

QUESTIONS_PATH = Path(__file__).with_name("vault_questions.json")
SAMPLE_VAULT = PROJECT_ROOT / "sample_data" / "vault"
CARELESS_ANSWER = "No specific figures on this are available."
# Seen live, the founder's RT6: total payroll as the cost of a designer, and runway reduced by an amount of money.
WRONG_MEANING_ANSWER = (
    "The financial impact of hiring a designer would be a monthly cost of $308,437.67, reducing runway by that amount."
)


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    cited: list[str]
    facts: list[list[str]]  # every group must match; any phrase in a group will do
    past_decisions: list[str] = field(default_factory=list)
    not_cited: list[str] = field(default_factory=list)
    impact: dict[str, float] = field(default_factory=dict)  # expected fields of `decision_impact`
    not_in_answer: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    case: str
    mode: str
    problems: list[str]
    detail: str = ""

    @property
    def passed(self) -> bool:
        return not self.problems

    def line(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return f"{verdict} [{self.mode}] {self.case}: {'; '.join(self.problems) or self.detail}"


def load_cases(path: Path = QUESTIONS_PATH) -> list[EvalCase]:
    return [EvalCase(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def score(
    case: EvalCase,
    *,
    answer: str,
    cited: set[str],
    past_decisions: set[str],
    check_all_cited: bool = True,
) -> list[str]:
    """What is wrong with an answer: missing sources, cited sources it should not use, missing facts."""
    problems: list[str] = []
    if check_all_cited:
        problems += [f"did not cite {path}" for path in case.cited if path not in cited]
    problems += [f"cited {path} without a reason" for path in case.not_cited if path in cited]
    if past_decisions != set(case.past_decisions):
        problems.append(f"past decisions {sorted(past_decisions)} != expected {sorted(case.past_decisions)}")
    lowered = answer.lower()
    problems += [
        f"missing fact ({' | '.join(group)})"
        for group in case.facts
        if not any(phrase.lower() in lowered for phrase in group)
    ]
    return problems


def impact_problems(case: EvalCase, impact: dict[str, Any] | None, answer: str) -> list[str]:
    """The impact fields must be the expected numbers, and the answer must not use the numbers it should not."""
    problems: list[str] = []
    if case.impact and impact is None:
        problems.append("no decision impact")
    for name, expected in case.impact.items():
        value = (impact or {}).get(name)
        if impact is not None and (value is None or abs(float(value) - expected) > 0.005):
            problems.append(f"impact {name} = {value}, expected {expected}")
    return problems + [f"answer contains {phrase}" for phrase in case.not_in_answer if phrase in answer]


# --- offline ----------------------------------------------------------------------------------------------------
def _careless_llm(question: str) -> FakeProvider:
    def respond(messages: list[Any], tools: Any, schema: Any) -> Any:
        return CARELESS_ANSWER

    return FakeProvider([[ToolCall(name="search_vault", arguments={"query": question})]], default=respond)


def _down_llm() -> FakeProvider:
    return FakeProvider(default=lambda messages, tools, schema: LLMUnavailable("no model in this eval"))


async def _ask(provider: FakeProvider, vault: Any, question: str) -> tuple[AgentResult, str]:
    """The Librarian and then the Advisor, as a decision team would run them."""
    router = LLMRouter(provider)
    runner = AgentRunner(router, EventBus(), "run_eval", lambda agent_id: ToolContext(None, vault, agent_id))
    instance = AgentInstance(type="librarian", name=REGISTRY["librarian"].title, brief=question, provider=provider.name)
    result = await runner.run(instance, question)
    plan = Plan(intent="knowledge", team=[instance], planner="eval")
    parts = [chunk.delta async for chunk in advise(router, question, plan, [result])]
    return result, "".join(parts)


def _check(case: EvalCase, mode: str, result: AgentResult, advisor_answer: str) -> EvalResult:
    used_in_text = {c.path for c in result.citations}
    found = {d.path for d in result.past_decisions}
    # A careless model names no sources of its own, so only a past decision can be expected in its answer.
    problems = (
        score(
            case,
            answer=f"{result.text}\n{advisor_answer}",
            cited=used_in_text,
            past_decisions=found,
        )
        if mode == "rules"
        else score(
            EvalCase(
                case.id,
                case.question,
                cited=case.past_decisions,
                # Facts in an ordinary note cannot appear when the model ignored them: only a record is guaranteed.
                facts=case.facts if case.past_decisions else [],
                past_decisions=case.past_decisions,
                not_cited=case.not_cited,
            ),
            answer=advisor_answer,
            cited=used_in_text,
            past_decisions=found,
        )
    )
    problems += [f"{path} is cited but the answer does not name it" for path in used_in_text if path not in result.text]
    return EvalResult(case.id, mode, problems, f"cites {sorted(used_in_text) or 'nothing'}")


def make_sample_vault(root: Path) -> Any:
    """A private copy of the sample vault with keyword search, so ranking is deterministic."""
    shutil.copytree(SAMPLE_VAULT, root)
    manager = VaultManager(root)
    index = HybridIndex(manager, FakeEmbedder(), None, ApproxTokenizer())
    index.refresh(dense=False)
    return SimpleNamespace(
        vault=manager,
        index=index,
        ensure_started=lambda: None,
        wait_ready=lambda: True,
        apply_changes=lambda paths: index.refresh(sorted(paths), dense=False),
    )


def sample_finance(root: Path) -> Any:
    db = FinanceDB(root / "default")
    ingest_directory(db, PROJECT_ROOT / "sample_data")
    return SimpleNamespace(
        db=db,
        metrics=MetricsEngine(db),
        scenario=ScenarioEngine(db),
        calibration=CalibrationStore(root / "calibration"),
    )


def wrong_meaning_llm() -> FakeProvider:
    """Fetches total payroll and calls it the cost of the hire, every time it is asked."""

    def respond(messages: list[Any], tools: Any, schema: Any) -> Any:
        return WRONG_MEANING_ANSWER

    call = ToolCall(name="get_metric", arguments={"name": "headcount_cost"})
    return FakeProvider([[call]], default=respond)


async def _ask_decision(provider: FakeProvider, finance: Any, question: str) -> tuple[AgentResult, str, list[str]]:
    """The Financial Analyst and then the Advisor, on the sample finance data."""
    router = LLMRouter(provider)
    runner = AgentRunner(router, EventBus(), "run_eval", lambda agent_id: ToolContext(finance, None, agent_id))
    title = REGISTRY["financial_analyst"].title
    instance = AgentInstance(type="financial_analyst", name=title, brief=question, provider=provider.name)
    result = await runner.run(instance, question)
    plan = Plan(intent="decision", team=[instance], planner="eval")
    issues: list[str] = []
    parts = [chunk.delta async for chunk in advise(router, question, plan, [result], issues)]
    return result, "".join(parts), issues


async def _run_decision_case(case: EvalCase, finance: Any) -> list[EvalResult]:
    results: list[EvalResult] = []
    for mode, provider in (("rules", _down_llm()), ("careless", wrong_meaning_llm())):
        result, answer, issues = await _ask_decision(provider, finance, case.question)
        impact = None if result.decision_impact is None else result.decision_impact.model_dump()
        problems = impact_problems(case, impact, f"{result.text}\n{answer}")
        if mode == "careless" and (result.verified or not issues):
            problems.append(f"the wrong claim was not flagged (verified={result.verified}, advisor issues={issues})")
        if mode == "rules" and not result.verified:
            problems.append(f"the code-written answer failed verification: {result.issues}")
        results.append(EvalResult(case.id, mode, problems, answer[:90]))
    return results


async def run_offline_async(cases: list[EvalCase] | None = None) -> list[EvalResult]:
    results: list[EvalResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "vault"
        shutil.copytree(SAMPLE_VAULT, root)
        manager = VaultManager(root)
        index = HybridIndex(manager, FakeEmbedder(), None, ApproxTokenizer())  # keyword search: deterministic ranking
        index.refresh(dense=False)
        vault = SimpleNamespace(vault=manager, index=index, ensure_started=lambda: None, wait_ready=lambda: True)
        finance = sample_finance(Path(tmp) / "finance")
        for case in cases if cases is not None else load_cases():
            if case.impact:
                results += await _run_decision_case(case, finance)
                continue
            modes: dict[str, Callable[[], FakeProvider]] = {
                "rules": _down_llm,
                "careless": lambda question=case.question: _careless_llm(question),
            }
            for mode, make_provider in modes.items():
                result, answer = await _ask(make_provider(), vault, case.question)
                results.append(_check(case, mode, result, answer))
    return results


def run_offline(cases: list[EvalCase] | None = None) -> list[EvalResult]:
    return asyncio.run(run_offline_async(cases))


# --- live -------------------------------------------------------------------------------------------------------
def check_live_reply(case: EvalCase, reply: dict[str, Any]) -> EvalResult:
    """One `/api/chat` reply. The founder reads `answer`, so a past decision's facts must be in that text."""
    cited = {c["path"] for c in reply.get("citations", [])}
    found = {d["path"] for d in reply.get("past_decisions", [])}
    team_text = " ".join(str(a.get("text", "")) for a in reply.get("agents", []))
    answer = str(reply.get("answer", ""))
    problems = score(
        case,
        answer=answer if case.past_decisions else f"{answer}\n{team_text}",
        cited=cited,
        past_decisions=found,
    )
    problems += impact_problems(case, reply.get("decision_impact"), answer)
    if not reply.get("verified"):
        problems.append(f"not verified: {reply.get('issues')}")
    seconds = float(reply.get("elapsed_ms", 0)) / 1000
    return EvalResult(case.id, "live", problems, f"{seconds:.0f} s, cites {sorted(cited) or 'nothing'}")
