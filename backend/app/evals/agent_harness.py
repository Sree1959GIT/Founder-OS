"""One agent, one question, one model: the unit that prompt tuning and the provider bake-off both measure.

The agent runs through the real `AgentRunner`, with the frame code would build, over the sample data. So the Verifier
and the repair turn count, and a `repair` is a model's answer that code had to send back.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.decision_frame import DecisionFrame, build_frame
from app.agents.events import EventBus
from app.agents.guards import goal_contradiction, role_problems
from app.agents.registry import REGISTRY
from app.agents.runtime import AgentInstance, AgentRunner
from app.agents.tools import ToolContext
from app.agents.verifier import split_sentences
from app.llm.router import LLMRouter

_CITATION = re.compile(r"\[[\w./-]+\.(?:md|csv|txt|pdf|xlsx)\]")
_RISK_LINE = re.compile(r"Risk:.*Likelihood:.*Impact:.*Mitigation:", re.I)
_LIST_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.M)
_NOTHING_FOUND = re.compile(
    r"\b(nothing|no (?:note|mention|record|information)|not (?:found|mentioned|covered))\b", re.I
)
_DECIDED_TO_DECIDE = re.compile(r"\bdecided to [\"“']?decide\b", re.I)
_OWNER = re.compile(r"\b(own\w*|lead\w*|responsible|accountable)\b", re.I)
_STEPS = re.compile(r"\b(first|second|third|step|steps|start|begin)\b", re.I)
_THE_FOUNDER = re.compile(r"\bthe founder\b", re.I)


@dataclass
class AgentRun:
    agent: str
    question: str
    text: str
    status: str
    verified: bool | None
    repairs: int
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def score(agent: str, question: str, text: str, frame: DecisionFrame | None, verified: bool | None) -> list[str]:
    """What this agent's answer must be, whatever the model. Word checks: they catch the mistakes seen live."""
    problems = list(role_problems(agent, text, question, frame))
    if not text.strip():
        return ["empty answer"]
    if verified is False:
        problems.append("the Verifier flagged it")
    if _THE_FOUNDER.search(text):
        problems.append("says 'the founder'")
    problems += [
        f"contradicts the goal check: {s.strip()}" for s in split_sentences(text) if goal_contradiction(s, frame)
    ]
    if agent == "people_ops":
        if not _OWNER.search(text):
            problems.append("names no owner")
        if not _STEPS.search(text):
            problems.append("gives no first steps")
    elif agent == "regulatory_tax":
        points = len(_LIST_LINE.findall(text))
        if not 3 <= points <= 6:
            problems.append(f"{points} points, wanted 3 to 5")
        if not re.search(r"\badviser\b", text, re.I):
            problems.append("does not say who confirms it")
    elif agent == "devils_advocate":
        risks = len(_RISK_LINE.findall(text))
        if risks < 3:
            problems.append(f"{risks} risks in the required form, wanted at least 3")
    elif agent == "librarian":
        if _DECIDED_TO_DECIDE.search(text):
            problems.append("says you decided to decide")
        if not _CITATION.search(text) and not _NOTHING_FOUND.search(text):
            problems.append("no source and does not say nothing was found")
    return problems


async def run_agent(agent: str, question: str, router: LLMRouter, finance: Any, vault: Any) -> AgentRun:
    def ctx(agent_id: str) -> ToolContext:
        return ToolContext(finance, vault, agent_id)

    frame = build_frame(question, ctx("frame")) if agent not in ("librarian", "financial_analyst") else None
    spec = REGISTRY[agent]
    inst = AgentInstance(type=agent, name=spec.title, brief=question)
    runner = AgentRunner(router, EventBus(), "eval", ctx)
    started = time.perf_counter()
    result = await runner.run(inst, question, frame=frame)
    latency = (time.perf_counter() - started) * 1000
    usage = getattr(result, "usage", None)
    run = AgentRun(
        agent=agent,
        question=question,
        text=result.text,
        status=result.status,
        verified=result.verified,
        repairs=max(result.attempts - 1, 0),
        latency_ms=latency,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        provider=result.provider,
    )
    run.problems = score(agent, question, result.text, frame, result.verified)
    # Founder note 55: a figure the source check had to take out is a failure, even though the answer reads clean.
    if result.removed_figures:
        run.problems.append(f"wrote {len(result.removed_figures)} unsupported figure(s) that were removed")
    if result.status != "done":
        run.problems.insert(0, f"ended {result.status}")
    if result.provider == "rules":
        run.problems.insert(0, "the model did not answer: rules template")
    return run
