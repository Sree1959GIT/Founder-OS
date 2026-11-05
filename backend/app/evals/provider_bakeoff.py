"""Bake-off of LLM providers per agent type: accuracy, latency and cost per answer, plus the conversation lane's test.

Each model answers the labelled questions for each agent type through the real `AgentRunner`. `local` agents never run
on a cloud model (PRD R2), so a cloud row covers only `cloud_allowed` and `cloud` types, with the privacy filter on.
`summarise_calls` reads what really happened from `llm_calls.jsonl` (never prompts or replies, which it does not hold).
"""

from __future__ import annotations

import contextlib
import json
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.registry import REGISTRY
from app.conversation.manager import FAST_SYSTEM
from app.evals.agent_harness import AgentRun, run_agent
from app.evals.labelled_eval import LabelledCase, load_cases
from app.llm.base import LLMError, LLMProvider, Message
from app.llm.costs import CostLedger, Usage
from app.llm.router import LLMRouter

# The agents the bake-off times, each with questions its own rubric can judge.
AGENT_TYPES = ("financial_analyst", "librarian", "people_ops", "regulatory_tax", "devils_advocate")
LANE_PROMPTS = (
    "Say that the Financial Analyst and the Librarian are done and that three agents are still working.",
    "Say that the team is still working on the Dubai office question.",
    "Ask which assumption would change the founder's mind if it were wrong.",
    "Say that the answer is ready and that it rests on assumptions the founder should confirm.",
    "Say that a new question has been queued until this run is finished.",
)
_DIGIT = re.compile(r"\d")
LANE_LIMIT_S = 4.0


def cases_for(agent: str, per_agent: int, cases: list[LabelledCase] | None = None) -> list[str]:
    rows = cases if cases is not None else load_cases()
    tuned = [c.question for c in rows if agent in c.tune_for]
    named = [c.question for c in rows if agent in c.agents and c.question not in tuned]
    return (tuned + named)[:per_agent]


@dataclass
class ProviderRow:
    model: str
    agent: str
    is_cloud: bool = False
    runs: list[AgentRun] = field(default_factory=list)
    skipped: str = ""

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.runs)

    @property
    def pass_rate(self) -> float:
        return self.passed / len(self.runs) if self.runs else 0.0

    @property
    def mean_s(self) -> float:
        return statistics.fmean(r.latency_ms for r in self.runs) / 1000 if self.runs else 0.0

    def cost_per_answer(self, ledger: CostLedger | None) -> float | None:
        if not self.is_cloud:
            return 0.0
        if ledger is None or not self.runs:
            return None
        costs = [
            ledger.estimate(self.model, Usage(input_tokens=r.input_tokens, output_tokens=r.output_tokens))
            for r in self.runs
        ]
        return None if any(c is None for c in costs) else statistics.fmean(costs)  # type: ignore[arg-type]

    def cells(self, ledger: CostLedger | None = None) -> list[str]:
        if self.skipped:
            return [self.model, self.agent, "-", "-", "-", "-", "-", self.skipped]
        cost = self.cost_per_answer(ledger)
        repairs = sum(r.repairs for r in self.runs)
        return [
            self.model,
            self.agent,
            f"{self.passed}/{len(self.runs)}",
            f"{self.pass_rate:.0%}",
            f"{self.mean_s:.1f}",
            str(repairs),
            "unknown" if cost is None else f"${cost:.4f}",
            "; ".join(sorted({p.split(":")[0] for r in self.runs for p in r.problems}))[:70],
        ]


AGENT_HEADERS = ["model", "agent", "passed", "rate", "mean s", "repairs", "$/answer", "what failed"]


async def run_provider(
    provider: LLMProvider,
    finance: Any,
    vault: Any,
    *,
    agents: tuple[str, ...] = AGENT_TYPES,
    per_agent: int = 3,
    router: LLMRouter | None = None,
    on_run: Any = None,
) -> list[ProviderRow]:
    rows: list[ProviderRow] = []
    router = router or LLMRouter(provider)
    for agent in agents:
        row = ProviderRow(provider.model, agent, provider.is_cloud)
        if provider.is_cloud and REGISTRY[agent].privacy == "local":
            row.skipped = "local-only agent: never sent to a cloud model"
            rows.append(row)
            continue
        if REGISTRY[agent].tools and not provider.supports_tools:
            row.skipped = "this model has no tool support"
            rows.append(row)
            continue
        for question in cases_for(agent, per_agent):
            result = await run_agent(agent, question, router, finance, vault)
            row.runs.append(result)
            if on_run is not None:
                on_run(provider.model, result)
        rows.append(row)
    return rows


@dataclass
class LaneRow:
    model: str
    replies: list[tuple[str, float, str]] = field(default_factory=list)  # reply, seconds, problem

    @property
    def passed(self) -> int:
        return sum(not p for _, _, p in self.replies)

    @property
    def within_limit(self) -> int:
        return sum(s <= LANE_LIMIT_S for _, s, _ in self.replies)

    def cells(self) -> list[str]:
        latencies = sorted(s for _, s, _ in self.replies)
        p50 = latencies[len(latencies) // 2] if latencies else 0.0
        problems = "; ".join(sorted({p for _, _, p in self.replies if p}))[:60]
        n = len(self.replies)
        return [self.model, f"{self.passed}/{n}", f"{self.within_limit}/{n}", f"{p50:.2f}", problems]


LANE_HEADERS = ["model", "good replies", f"within {LANE_LIMIT_S:g} s", "p50 s", "what failed"]


def lane_problem(reply: str) -> str:
    """One short sentence with no figures, as the lane requires. The lane throws away a reply with a figure."""
    text = reply.strip()
    if not text:
        return "empty"
    if _DIGIT.search(text):
        return "states a figure"
    if len(text.split()) > 30:
        return "too long"
    return ""


async def run_lane(provider: LLMProvider) -> LaneRow:
    row = LaneRow(provider.model)
    # The first call may load the model: warm it, so the table shows the speed the lane would see.
    with contextlib.suppress(LLMError):
        await provider.complete([Message.user("Say OK.")])
    for prompt in LANE_PROMPTS:
        started = time.perf_counter()
        try:
            completion = await provider.complete([Message.system(FAST_SYSTEM), Message.user(prompt)])
            row.replies.append((completion.text, time.perf_counter() - started, lane_problem(completion.text)))
        except LLMError as exc:
            row.replies.append(("", time.perf_counter() - started, type(exc).__name__))
    return row


def summarise_calls(path: Path) -> list[list[str]]:
    """What the running app really spent, by agent type and model, from `llm_calls.jsonl`."""
    if not path.is_file():
        return []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        groups[(row.get("agent_type") or "(none)", row.get("model") or "?")].append(row)
    table_rows = []
    for (agent, model), rows in sorted(groups.items()):
        latencies = [float(r.get("latency_ms") or 0) for r in rows]
        costs = [float(r["est_cost_usd"]) for r in rows if r.get("est_cost_usd") is not None]
        failures = sum(1 for r in rows if r.get("error"))
        table_rows.append(
            [
                agent,
                model,
                str(len(rows)),
                f"{statistics.fmean(latencies) / 1000:.1f}",
                f"${statistics.fmean(costs):.4f}" if costs else "unknown",
                str(failures),
            ]
        )
    return table_rows


CALL_HEADERS = ["agent type", "model", "calls", "mean s", "$/call", "failed"]


def recommend_defaults(rows: list[ProviderRow], lane: list[LaneRow], ledger: CostLedger | None = None) -> list[str]:
    """Per agent type: the highest pass rate, then the cheapest, then the fastest. A proposal, never applied."""
    lines = []
    for agent in dict.fromkeys(r.agent for r in rows):
        mine = [r for r in rows if r.agent == agent and r.runs]
        if not mine:
            continue

        def key(r: ProviderRow) -> tuple[float, float, float]:
            cost = r.cost_per_answer(ledger)
            return (-r.pass_rate, cost if cost is not None else 1e9, r.mean_s)

        best = min(mine, key=key)
        lines.append(f"{agent}: {best.model} ({best.passed}/{len(best.runs)}, {best.mean_s:.1f} s)")
    usable = [r for r in lane if r.replies and r.passed == len(r.replies)]
    if usable:
        best = max(usable, key=lambda r: (r.within_limit, -float(r.cells()[3])))
        lines.append(
            f"conversation lane (FAST_LANE_MODEL): {best.model} ({best.within_limit}/{len(best.replies)} in time)"
        )
    elif lane:
        lines.append("conversation lane: no model passed every reply; keep the templates (FAST_LANE_MODEL empty)")
    return lines
