"""Eval over the sample vault: do the right sources and facts reach the founder?

Offline, no Ollama (pytest and `scripts/eval_vault.py`): each question runs twice over the sample vault with keyword
search, so ranking is deterministic.
- `rules`: the LLM is down, so the Librarian answers from its template (PRD R3).
- `careless`: a fake LLM searches, ignores what it finds and names no source. This is the failure the founder saw, and
  the code must still surface a past decision, and must not cite what the answer did not use.

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
from app.engine.chunking import ApproxTokenizer
from app.engine.embeddings import FakeEmbedder
from app.engine.hybrid_rag import HybridIndex
from app.llm.base import LLMUnavailable, ToolCall
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.vault.manager import VaultManager

QUESTIONS_PATH = Path(__file__).with_name("vault_questions.json")
SAMPLE_VAULT = PROJECT_ROOT / "sample_data" / "vault"
CARELESS_ANSWER = "No specific figures on this are available."


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    cited: list[str]
    facts: list[list[str]]  # every group must match; any phrase in a group will do
    past_decisions: list[str] = field(default_factory=list)
    not_cited: list[str] = field(default_factory=list)


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


async def run_offline_async(cases: list[EvalCase] | None = None) -> list[EvalResult]:
    results: list[EvalResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "vault"
        shutil.copytree(SAMPLE_VAULT, root)
        manager = VaultManager(root)
        index = HybridIndex(manager, FakeEmbedder(), None, ApproxTokenizer())  # keyword search: deterministic ranking
        index.refresh(dense=False)
        vault = SimpleNamespace(vault=manager, index=index, ensure_started=lambda: None, wait_ready=lambda: True)
        for case in cases if cases is not None else load_cases():
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
    if not reply.get("verified"):
        problems.append(f"not verified: {reply.get('issues')}")
    seconds = float(reply.get("elapsed_ms", 0)) / 1000
    return EvalResult(case.id, "live", problems, f"{seconds:.0f} s, cites {sorted(cited) or 'nothing'}")
