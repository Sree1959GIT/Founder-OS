"""Offline prompt tuning: try each version of an agent's prompt against the labelled questions on a real model.

    python scripts/tune_prompts.py                                  every agent with versions, on qwen3:8b (minutes)
    python scripts/tune_prompts.py --agents people_ops,librarian
    python scripts/tune_prompts.py --apply                          also copy the winner over the live prompt

Reports pass rate, repairs and latency per version, and records the winner in prompts/versions/MANIFEST.json. Nothing
rewrites prompts at runtime. Uses a private copy of the sample data, so your vault is not touched. Prints one table.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
import tempfile
from pathlib import Path

from loguru import logger

from app.evals.agent_harness import AgentRun, run_agent
from app.evals.decision_bakeoff import table
from app.evals.prompt_tuning import (
    HEADERS,
    agents_with_versions,
    apply_version,
    choose_best,
    live_version,
    record,
    tune_agent,
)
from app.evals.vault_eval import make_sample_vault, sample_finance
from app.llm.ollama import OllamaProvider
from app.llm.router import LLMRouter


async def tune(args: argparse.Namespace) -> int:
    provider = OllamaProvider(args.ollama_url, args.model, think=False, keep_alive="10m", timeout_s=args.timeout)
    router = LLMRouter(provider)
    agents = [a.strip() for a in args.agents.split(",") if a.strip()] or agents_with_versions()
    rows: list[list[str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finance = sample_finance(root / "finance")
        vault = make_sample_vault(root / "vault")

        async def run(agent: str, question: str) -> AgentRun:
            return await run_agent(agent, question, router, finance, vault)

        def progress(version: str, result: AgentRun) -> None:
            verdict = "PASS" if result.passed else "FAIL: " + "; ".join(result.problems)[:200]
            print(f"{result.agent} {version} {result.latency_ms / 1000:5.1f}s {verdict}", flush=True)

        for agent in agents:
            scores = await tune_agent(agent, run, on_run=progress)
            if not scores:
                print(f"{agent}: no versions")
                continue
            live = live_version(agent)
            keep = choose_best(scores, live)
            assert keep is not None
            record(agent, scores, keep, model=args.model, date=dt.date.today().isoformat())
            rows += [
                [*s.cells(), ("best" if s is keep else "") + (" live" if s.version == live else "")] for s in scores
            ]
            if args.apply and keep.version != live:
                apply_version(agent, keep.version)
                print(f"APPLIED {agent}: {live} -> {keep.version}")
    print()
    print(f"PROMPT TUNING on {args.model}")
    print(table([*HEADERS, "note"], rows))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agents", default="", help="comma-separated; default: every agent with versions")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--apply", action="store_true", help="copy the winner over the live prompt")
    args = parser.parse_args()
    logger.remove()
    return asyncio.run(tune(args))


if __name__ == "__main__":
    sys.exit(main())
