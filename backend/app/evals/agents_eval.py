"""Eval of the M3b specialists: does each one join the team and carry what it must?

Offline, no Ollama (pytest and `scripts/eval_agents.py`): each case runs through the whole graph over the sample vault
and finance data, twice.
- `rules`: the LLM is down, so every agent answers from its template (PRD R3).
- `careless`: a fake LLM writes an invented figure into everything. The team must still answer, nothing with that
  figure may count as verified, and a memo must not keep it.

Live (`scripts/eval_agents.py --live`): the same questions through `POST /api/chat`, so with the real model. Model
output varies, so a failure there is a prompt to read the answer, not a proof of a bug.

Live runs write memos into the vault of the backend they ask. Use a test backend, or delete them afterwards.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator, ChatResult
from app.agents.tools import ToolContext
from app.decision.base import DecisionService, FakeDecisionProvider
from app.evals.vault_eval import make_sample_vault, sample_finance
from app.llm.base import LLMUnavailable
from app.llm.fake import FakeProvider, schema_example
from app.llm.router import LLMRouter

QUESTIONS_PATH = Path(__file__).with_name("agent_questions.json")
INVENTED = "$48,123"


@dataclass(frozen=True)
class AgentCase:
    id: str
    question: str
    agent: str
    artifact: str | None = None
    text_has: list[str] = field(default_factory=list)
    memo: bool = False


@dataclass
class AgentEvalResult:
    id: str
    mode: str
    problems: list[str]

    @property
    def passed(self) -> bool:
        return not self.problems

    def line(self) -> str:
        verdict = "PASS" if self.passed else "FAIL: " + "; ".join(self.problems)
        return f"{self.id:<22} {self.mode:<9} {verdict}"


def load_cases(path: Path = QUESTIONS_PATH) -> list[AgentCase]:
    return [AgentCase(**case) for case in json.loads(path.read_text(encoding="utf-8"))]


def _agent_of(reply: dict[str, Any], agent_type: str) -> dict[str, Any] | None:
    return next((a for a in reply.get("agents", []) if a.get("type") == agent_type), None)


def check_reply(case: AgentCase, mode: str, reply: dict[str, Any]) -> AgentEvalResult:
    """The checks that hold for any model: this agent ran, and what code guarantees is there."""
    problems: list[str] = []
    agent = _agent_of(reply, case.agent)
    if agent is None:
        team = [a.get("type") for a in reply.get("agents", [])]
        return AgentEvalResult(case.id, mode, [f"{case.agent} not on the team: {team}"])
    if agent.get("status") != "done":
        problems.append(f"{case.agent} ended {agent.get('status')}: {agent.get('error')}")
    if case.artifact and not any(a.get("kind") == case.artifact for a in agent.get("artifacts", [])):
        problems.append(f"no {case.artifact} artifact")
    text = agent.get("text", "")
    for wanted in case.text_has:
        if wanted.lower() not in text.lower():
            problems.append(f"missing {wanted!r}")
    if case.memo:
        memo = reply.get("memo") or {}
        if not memo.get("path"):
            problems.append("no memo written")
        elif not memo.get("review_date") or not memo.get("predictions"):
            problems.append("the memo has no review date or prediction")
        elif memo["path"] not in reply.get("answer", "") or memo["review_date"] not in reply.get("answer", ""):
            problems.append("the reply does not name the memo and its review date")
    return AgentEvalResult(case.id, mode, problems)


def _careless(messages: list[Any], tools: Any, schema: Any) -> str:
    if schema is None:
        return f"- Risk: this costs {INVENTED} a month. Likelihood: high. Impact: high. Mitigation: wait."
    if "predictions" in schema.get("properties", {}):
        return json.dumps(
            {
                "title": "The decision",
                "decision": f"Go ahead at {INVENTED} a month.",
                "context": "Careless.",
                "options": ["Go", "Stop"],
                "assumptions": ["It works"],
                "predictions": [{"statement": "It works by the review date", "probability": 0.5}],
                "kill_criteria": ["It does not work"],
            }
        )
    return json.dumps(schema_example(schema))


def _down(messages: list[Any], tools: Any, schema: Any) -> str:
    raise LLMUnavailable("down")


def _careless_problems(result: ChatResult, vault_root: Path) -> list[str]:
    problems = [
        f"{a.name} was verified with an invented figure"
        for a in result.agents
        if a.verified and a.status == "done" and INVENTED in a.text
    ]
    if result.memo is not None:
        text = (vault_root / result.memo.path).read_text(encoding="utf-8")
        # Nowhere: not as a fact, not in a question, not on the list of what to confirm.
        if INVENTED.lstrip("$") in text:
            problems.append("the memo kept an invented figure")
        if "[figure removed" in text:
            problems.append("the memo has a scar where a figure was")
    return problems


async def _run_case(case: AgentCase, mode: str, finance: Any, vault: Any) -> AgentEvalResult:
    provider = FakeProvider(default=_careless if mode == "careless" else _down)
    orchestrator = AgentOrchestrator(
        LLMRouter(provider),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )
    result: ChatResult = await orchestrator.start(case.question).task  # type: ignore[misc]
    checked = check_reply(case, mode, result.model_dump(mode="json"))
    if mode == "careless":
        checked.problems = [p for p in checked.problems if not p.startswith("missing")]
        checked.problems += _careless_problems(result, vault.vault.root)
    return checked


async def run_offline_async(cases: list[AgentCase] | None = None) -> list[AgentEvalResult]:
    results: list[AgentEvalResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finance = sample_finance(root / "finance")
        for mode in ("rules", "careless"):
            vault = make_sample_vault(root / f"vault-{mode}")
            for case in cases or load_cases():
                results.append(await _run_case(case, mode, finance, vault))
            shutil.rmtree(root / f"vault-{mode}", ignore_errors=True)
    return results


def run_offline(cases: list[AgentCase] | None = None) -> list[AgentEvalResult]:
    return asyncio.run(run_offline_async(cases))
