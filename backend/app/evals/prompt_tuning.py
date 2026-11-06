"""Offline prompt tuning: try prompt versions per agent against the labelled questions, keep the best as a version.

Versions live in `app/agents/prompts/versions/<agent>/vN.md`, and `MANIFEST.json` records which one is live and why.
The live prompt stays `prompts/<agent>.md`. **Nothing rewrites a prompt at runtime**: only this offline tool, when told
to with `--apply`, copies a version over the live file. A person reads the diff in a commit.

The best version has the highest pass rate, then the fewest repairs, then the lowest latency. A version must beat the
live one by a whole case to replace it: a tie keeps what is there, because one run of a small set is noisy.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.registry import PROMPTS_DIR, AgentType
from app.evals.agent_harness import AgentRun
from app.evals.labelled_eval import load_cases

VERSIONS_DIR = PROMPTS_DIR / "versions"
MANIFEST_PATH = VERSIONS_DIR / "MANIFEST.json"
Runner = Callable[[str, str], Awaitable[AgentRun]]


@dataclass
class VariantScore:
    agent: str
    version: str
    runs: list[AgentRun] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.runs)

    @property
    def pass_rate(self) -> float:
        return self.passed / len(self.runs) if self.runs else 0.0

    @property
    def repairs(self) -> int:
        return sum(r.repairs for r in self.runs)

    @property
    def latency_ms(self) -> float:
        return statistics.fmean(r.latency_ms for r in self.runs) if self.runs else 0.0

    def rank(self) -> tuple[float, int, float]:
        return (-self.pass_rate, self.repairs, self.latency_ms)

    def cells(self) -> list[str]:
        return [
            self.agent,
            self.version,
            f"{self.passed}/{len(self.runs)}",
            f"{self.pass_rate:.0%}",
            str(self.repairs),
            f"{self.latency_ms / 1000:.1f}",
        ]

    def as_record(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "cases": len(self.runs),
            "repairs": self.repairs,
            "mean_latency_s": round(self.latency_ms / 1000, 1),
        }


HEADERS = ["agent", "version", "passed", "pass rate", "repairs", "mean s"]


def questions_for(agent: str, limit: int | None = None) -> list[str]:
    questions = [c.question for c in load_cases() if agent in c.tune_for]
    return questions[:limit] if limit else questions


def versions_of(agent: str, root: Path = VERSIONS_DIR) -> dict[str, str]:
    folder = root / agent
    if not folder.is_dir():
        return {}
    files = sorted(folder.glob("v*.md"), key=lambda p: (len(p.stem), p.stem))
    return {path.stem: path.read_text(encoding="utf-8") for path in files}


def agents_with_versions(root: Path = VERSIONS_DIR) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


@contextmanager
def prompt_override(agent: str, text: str) -> Iterator[None]:
    """For this offline measurement only. The app has no way to take a prompt from anywhere but its file."""
    original = AgentType.prompt

    def patched(self: AgentType) -> str:
        return text if self.name == agent else original(self)

    AgentType.prompt = patched  # type: ignore[method-assign]
    try:
        yield
    finally:
        AgentType.prompt = original  # type: ignore[method-assign]


async def tune_agent(
    agent: str,
    run: Runner,
    *,
    root: Path = VERSIONS_DIR,
    questions: list[str] | None = None,
    on_run: Callable[[str, AgentRun], None] | None = None,
) -> list[VariantScore]:
    scores: list[VariantScore] = []
    wanted = questions if questions is not None else questions_for(agent)
    for version, text in versions_of(agent, root).items():
        score = VariantScore(agent, version)
        with prompt_override(agent, text):
            for question in wanted:
                result = await run(agent, question)
                score.runs.append(result)
                if on_run is not None:
                    on_run(version, result)
        scores.append(score)
    return scores


def sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:12]


def live_version(agent: str, root: Path = VERSIONS_DIR, prompts: Path = PROMPTS_DIR) -> str | None:
    """Which version the live prompt is, or None if someone edited it by hand since."""
    live = sha((prompts / f"{agent}.md").read_text(encoding="utf-8"))
    return next((v for v, text in versions_of(agent, root).items() if sha(text) == live), None)


def choose_best(scores: list[VariantScore], live: str | None) -> VariantScore | None:
    """The version to keep. A challenger must pass at least one more case than the live version."""
    if not scores:
        return None
    best = min(scores, key=VariantScore.rank)
    current = next((s for s in scores if s.version == live), None)
    return current if current is not None and best.passed <= current.passed else best


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def record(
    agent: str,
    scores: list[VariantScore],
    keep: VariantScore,
    *,
    model: str,
    date: str,
    path: Path = MANIFEST_PATH,
) -> None:
    manifest = load_manifest(path)
    manifest[agent] = {
        "best": keep.version,
        "model": model,
        "date": date,
        "results": {s.version: s.as_record() for s in scores},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def apply_version(agent: str, version: str, root: Path = VERSIONS_DIR, prompts: Path = PROMPTS_DIR) -> None:
    text = versions_of(agent, root)[version]
    (prompts / f"{agent}.md").write_text(text, encoding="utf-8", newline="\n")
