"""The labelled question set: vault, metrics, hires, office or region, pricing, new product and ambiguous turns.

Each question carries what is true whatever the model writes: the intent, who must be on the team, the decision type,
the sources, the code-computed figures. Offline it runs with the LLM down (PRD R3), so a failure is a routing or code
bug. `scripts/tune_prompts.py` and `scripts/bakeoff_providers.py` use the same set with real models.
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator, ChatResult
from app.agents.guards import goal_contradiction
from app.agents.tools import ToolContext
from app.conversation.classifier import TurnClassifier
from app.decision.base import Decision, DecisionService, FakeDecisionProvider
from app.evals.vault_eval import make_sample_vault, sample_finance
from app.llm.base import LLMUnavailable
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter

QUESTIONS_PATH = Path(__file__).with_name("labelled_questions.json")
CATEGORIES = ("vault", "metrics", "hires", "office_region", "pricing", "new_product", "ambiguous")
_THIRD_PERSON = re.compile(r"\bthe founder\b", re.I)


@dataclass(frozen=True)
class LabelledCase:
    id: str
    category: str
    question: str
    intent: str | None = None
    agents: list[str] = field(default_factory=list)
    decision_type: str | None = None
    cited: list[str] = field(default_factory=list)
    must_say: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    goal_away: bool = False
    turn_kind: str | None = None
    running: str = ""
    tune_for: list[str] = field(default_factory=list)


@dataclass
class LabelledResult:
    id: str
    category: str
    mode: str
    problems: list[str]
    latency_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return not self.problems

    def line(self) -> str:
        verdict = "PASS" if self.passed else "FAIL: " + "; ".join(self.problems)
        return f"{self.category:<14} {self.id:<22} {self.mode:<7} {verdict}"


def load_cases(path: Path = QUESTIONS_PATH) -> list[LabelledCase]:
    return [LabelledCase(**case) for case in json.loads(path.read_text(encoding="utf-8"))]


def check_chat(case: LabelledCase, mode: str, reply: dict[str, Any], frame: Any = None) -> LabelledResult:
    """The rubric for a question that goes through the graph. `frame` is the DecisionFrame when known."""
    problems: list[str] = []
    answer = str(reply.get("answer", ""))
    if case.intent and reply.get("intent") and reply["intent"] != case.intent:
        problems.append(f"intent {reply['intent']}, wanted {case.intent}")
    team = [a.get("type") for a in reply.get("agents", [])]
    problems += [f"{agent} not on the team {team}" for agent in case.agents if agent not in team]
    if not case.agents and case.intent == "chitchat" and team:
        problems.append(f"a team {team} for small talk")
    if case.decision_type and reply.get("decision_type") != case.decision_type:
        problems.append(f"decision type {reply.get('decision_type')}, wanted {case.decision_type}")
    everything = answer + " " + " ".join(str(a.get("text", "")) for a in reply.get("agents", []))
    problems += [f"does not say {w!r}" for w in case.must_say if w.lower() not in everything.lower()]
    problems += [f"says {w!r}" for w in case.must_not if w.lower() in answer.lower()]
    cited = {c.get("path") for c in reply.get("citations", [])} | {c.get("path") for c in reply.get("retrieved", [])}
    problems += [f"source {path} not found" for path in case.cited if path not in cited]
    if _THIRD_PERSON.search(answer):
        problems.append("says 'the founder' to the founder")
    if case.goal_away and "moves you away from your goal" not in answer:
        problems.append("does not say it moves away from a goal")
    if frame is not None:
        for sentence in re.split(r"(?<=[.!?])\s+", answer):
            goal = goal_contradiction(sentence, frame)
            if goal:
                problems.append(f"contradicts the goal check on {goal!r}: {sentence}")
    return LabelledResult(case.id, case.category, mode, problems, float(reply.get("elapsed_ms") or 0))


def _down(messages: list[Any], tools: Any, schema: Any) -> str:
    raise LLMUnavailable("down")


class _Unsure:
    """The decision model has not answered: routing rests on rules, then the safe default team."""

    name = "unsure"

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        return Decision(question=question, options=options, choice=options[0], probability=0.1, provider="unsure")


async def _check_turn(case: LabelledCase) -> LabelledResult:
    classifier = TurnClassifier(DecisionService(FakeDecisionProvider(probability=0.1)), 1.0)
    classified = await classifier.classify(case.question, case.running)
    problems = [] if classified.kind == case.turn_kind else [f"turn kind {classified.kind}, wanted {case.turn_kind}"]
    return LabelledResult(case.id, case.category, "rules", problems)


async def _check_graph(case: LabelledCase, finance: Any, vault: Any) -> LabelledResult:
    orchestrator = AgentOrchestrator(
        LLMRouter(FakeProvider(default=_down)),
        DecisionService(_Unsure()),
        EventBus(),
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )
    result: ChatResult = await orchestrator.start(case.question).task  # type: ignore[misc]
    return check_chat(case, "rules", result.model_dump(mode="json"), result.decision_frame)


async def run_offline_async(cases: list[LabelledCase] | None = None) -> list[LabelledResult]:
    results: list[LabelledResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finance = sample_finance(root / "finance")
        vault = make_sample_vault(root / "vault")
        for case in cases or load_cases():
            if case.turn_kind:
                results.append(await _check_turn(case))
            else:
                results.append(await _check_graph(case, finance, vault))
    return results


def run_offline(cases: list[LabelledCase] | None = None) -> list[LabelledResult]:
    return asyncio.run(run_offline_async(cases))


def summary(results: list[LabelledResult]) -> list[str]:
    lines = []
    for category in CATEGORIES:
        rows = [r for r in results if r.category == category]
        if rows:
            lines.append(f"{category:<14} {sum(r.passed for r in rows)}/{len(rows)}")
    return lines
