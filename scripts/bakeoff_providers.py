"""Bake-off of LLM models per agent type: accuracy, latency and cost per answer, and the conversation lane's speed.

    python scripts/bakeoff_providers.py                                  qwen3:8b and phi4-mini (about 30 minutes)
    python scripts/bakeoff_providers.py --models qwen3:8b,mistral:latest
    python scripts/bakeoff_providers.py --cloud gemini:gemini-3.8-flash  also a configured cloud model (paid)
    python scripts/bakeoff_providers.py --calls-only                     just the table from llm_calls.jsonl

Uses a private copy of the sample data: your vault and numbers are not touched. A loaded model can push the GPU's other
models out, and they reload on their next use. Proposes defaults per agent type and changes none of them.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import PROJECT_ROOT, Settings
from app.evals.agent_harness import AgentRun
from app.evals.decision_bakeoff import table
from app.evals.provider_bakeoff import (
    AGENT_HEADERS,
    CALL_HEADERS,
    LANE_HEADERS,
    LaneRow,
    ProviderRow,
    recommend_defaults,
    run_lane,
    run_provider,
    summarise_calls,
)
from app.evals.vault_eval import make_sample_vault, sample_finance
from app.llm.costs import CostLedger
from app.llm.fake import FakeProvider
from app.llm.names import name_sources
from app.llm.ollama import OllamaProvider
from app.llm.privacy import NameIndex
from app.llm.router import LLMRouter, build_named_provider


async def bakeoff(args: argparse.Namespace) -> int:
    rows: list[ProviderRow] = []
    lanes: list[LaneRow] = []
    ledger: CostLedger | None = None

    def progress(model: str, result: AgentRun) -> None:
        verdict = "PASS" if result.passed else "FAIL: " + "; ".join(result.problems)[:160]
        print(f"{model} {result.agent} {result.latency_ms / 1000:5.1f}s {verdict}", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finance = sample_finance(root / "finance")
        vault = make_sample_vault(root / "vault")
        for model in [m.strip() for m in args.models.split(",") if m.strip()]:
            provider = OllamaProvider(args.ollama_url, model, think=False, keep_alive="5m", timeout_s=args.timeout)
            lane_provider = OllamaProvider(args.ollama_url, model, think=False, keep_alive="5m", timeout_s=60.0)
            lanes.append(await run_lane(lane_provider))
            print(f"{model} lane: {lanes[-1].cells()}", flush=True)
            rows += await run_provider(provider, finance, vault, per_agent=args.per_agent, on_run=progress)
        if args.cloud:
            settings = Settings()  # the keys in .env are read here, and only by the app's own settings
            ledger = CostLedger(
                root / "bakeoff_calls.jsonl",
                prices={m: (float(p[0]), float(p[1])) for m, p in settings.llm_prices.items()},
            )
            for spec in [s.strip() for s in args.cloud.split(",") if s.strip()]:
                name, _, model = spec.partition(":")
                cloud = build_named_provider(settings, name, model)  # type: ignore[arg-type]
                if cloud is None:
                    print(f"{spec}: not configured in .env, skipped")
                    continue
                router = LLMRouter(FakeProvider(name="unused-local"), cloud, cloud_allowed=True, ledger=ledger)
                router.names = NameIndex(name_sources(finance, vault))
                rows += await run_provider(
                    cloud, finance, vault, per_agent=args.per_agent, router=router, on_run=progress
                )
    print()
    print("PROVIDER BAKE-OFF per agent type")
    print(table(AGENT_HEADERS, [r.cells(ledger) for r in rows]))
    print()
    print(f"CONVERSATION LANE, one short sentence with no figures; the app's limit is {4} s")
    print(table(LANE_HEADERS, [r.cells() for r in lanes]))
    _print_calls(args)
    print()
    print("PROPOSED DEFAULTS (nothing is changed; record your choice in PRD section 12):")
    for line in recommend_defaults(rows, lanes, ledger):
        print(" ", line)
    return 0


def _print_calls(args: Any) -> None:
    calls = summarise_calls(Path(args.calls))
    print()
    print(f"WHAT THE APP REALLY USED, from {args.calls}")
    print(table(CALL_HEADERS, calls) if calls else "No calls recorded yet.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default="qwen3:8b,phi4-mini:latest", help="comma-separated Ollama models")
    parser.add_argument("--cloud", default="", help="comma-separated provider:model, for example openai:gpt-6-luna")
    parser.add_argument("--per-agent", type=int, default=3)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--calls", default=str(PROJECT_ROOT / "data" / "default" / "llm_calls.jsonl"))
    parser.add_argument("--calls-only", action="store_true")
    args = parser.parse_args()
    logger.remove()
    if args.calls_only:
        _print_calls(args)
        return 0
    return asyncio.run(bakeoff(args))


if __name__ == "__main__":
    sys.exit(main())
