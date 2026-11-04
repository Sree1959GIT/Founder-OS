"""Agent registry (PRD F3): fixed agent **types**; the Planner spawns **instances** of them.

Each type has a vetted prompt (`prompts/<name>.md`, editable without code changes), an allow-list of tools, a privacy
class (`local` | `cloud_allowed` | `cloud`) and a cost class. Nothing outside this registry can be spawned.
Specialist agents are added in M3b.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.llm.router import Privacy

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class AgentType:
    name: str
    title: str
    job: str
    tools: tuple[str, ...] = ()
    privacy: Privacy = "local"
    cost: Literal["low", "medium", "high"] = "low"
    core: bool = True
    spawnable: bool = field(default=True, metadata={"doc": "the Planner may put it on a team"})

    def prompt(self) -> str:
        """The prompt file, read on every call so edits apply without a restart."""
        path = PROMPTS_DIR / f"{self.name}.md"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"agent prompt {path} is missing") from exc


FINANCE_TOOLS = (
    "list_metrics",
    "get_metric",
    "metrics_summary",
    "run_scenario",
    "run_monte_carlo",
    "run_sql",
    "weighted_scoring",
    "expected_value",
    "calibration_scores",
)
LIBRARY_TOOLS = ("past_decisions", "search_vault", "read_note", "write_note")

REGISTRY: dict[str, AgentType] = {
    t.name: t
    for t in (
        AgentType(
            "advisor",
            "Advisor",
            "Socratic dialogue in replies of 3 sentences or fewer; narrates what the team is doing",
            spawnable=False,
        ),
        AgentType(
            "planner",
            "Planner",
            "Classifies the decision and proposes the team: agent types, instances and briefs",
            spawnable=False,
        ),
        AgentType(
            "financial_analyst",
            "Financial Analyst",
            "The only agent that runs metric routines, scenarios, Monte Carlo and guarded SQL; numbers carry lineage",
            tools=FINANCE_TOOLS,
        ),
        AgentType(
            "librarian",
            "Librarian",
            "Hybrid search over the vault and past decisions; returns context with citations",
            tools=LIBRARY_TOOLS,
        ),
        AgentType(
            "verifier",
            "Verifier",
            "Rejects numbers without lineage and claims without citations; sends work back once, then flags it",
            spawnable=False,
        ),
    )
}


def spawnable_types() -> list[str]:
    return [name for name, t in REGISTRY.items() if t.spawnable]
