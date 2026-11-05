"""Bake-off of decision models (PRD F7): accuracy, calibration and latency per provider, on labelled routing examples.

    python scripts/eval_decision_models.py                         rules and a stand-in fake: no model, seconds
    python scripts/eval_decision_models.py --llm qwen3:8b,phi4-mini:latest
    python scripts/eval_decision_models.py --laya                  stock Laya (needs the optional `laya` package)
    python scripts/eval_decision_models.py --laya models/laya-founderos  a fine-tuned checkpoint
    python scripts/eval_decision_models.py --jev                   needs JEV_API_KEY: paid, about $0.001 for the run
    python scripts/eval_decision_models.py --split all             every example (default: the held-out test split)

Each model is also scored as a cascade with the first --llm model behind it when it is below the threshold. Nothing
changes the app's defaults: read the table and decide. Prints one aligned table. Exit code 0 unless no provider ran.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from loguru import logger

from app.config import Settings
from app.decision.base import DecisionProvider, FakeDecisionProvider, LLMDecisionProvider
from app.decision.jev import JEV_INPUT_USD_PER_MTOK, JevProvider
from app.decision.laya import LayaProvider
from app.evals.decision_bakeoff import (
    HEADERS,
    CascadeProvider,
    RulesProvider,
    load_examples,
    recommend,
    run_bakeoff,
    table,
)
from app.llm.ollama import OllamaProvider
from app.llm.router import LLMRouter


def llm_provider(model: str, base_url: str, timeout_s: float) -> DecisionProvider:
    local = OllamaProvider(base_url, model, think=False, keep_alive="5m", num_ctx=2048, timeout_s=timeout_s)
    provider: Any = LLMDecisionProvider(LLMRouter(local))
    provider.name = f"llm:{model}"
    return provider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", default="", help="comma-separated Ollama models")
    parser.add_argument("--laya", nargs="?", const="stock", default=None, help="'stock' or a checkpoint folder")
    parser.add_argument("--device", default="", help="for Laya: cuda or cpu (default: its own choice)")
    parser.add_argument("--jev", action="store_true", help="use Jev (paid); reads JEV_API_KEY from the environment")
    parser.add_argument("--split", default="test", choices=("test", "train", "all"))
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--min-confidence", type=float, default=0.75)
    args = parser.parse_args()
    logger.remove()

    examples = load_examples(split=None if args.split == "all" else args.split)
    providers: dict[str, DecisionProvider] = {
        "rules": RulesProvider(),
        "fake (always first option)": FakeDecisionProvider(),
    }
    llms = {
        f"llm:{m.strip()}": llm_provider(m.strip(), args.ollama_url, args.timeout)
        for m in args.llm.split(",")
        if m.strip()
    }
    providers |= llms
    first_llm = next(iter(llms.values()), None)
    jev = None
    if args.laya is not None:
        checkpoint = "" if args.laya == "stock" else args.laya
        laya = LayaProvider(checkpoint, args.device)
        providers[f"laya:{args.laya}"] = laya
    if args.jev:
        key = os.environ.get("JEV_API_KEY") or Settings().jev_api_key
        jev = JevProvider(key)
        providers["jev"] = jev
    for name, provider in list(providers.items()):
        if first_llm is not None and name.startswith(("laya", "jev")):
            providers[f"{name}+llm"] = CascadeProvider(provider, first_llm, args.min_confidence)

    def progress(row: Any) -> None:
        print(f"... {row.provider} {row.kind}: {row.accuracy:.1%} of {row.n}, p50 {row.p50_ms:.0f} ms", flush=True)

    rows = asyncio.run(run_bakeoff(providers, examples, min_confidence=args.min_confidence, on_row=progress))
    print()
    print(f"DECISION BAKE-OFF on {len(examples)} examples ({args.split} split), threshold {args.min_confidence}")
    print(table(HEADERS, [r.cells() for r in rows]))
    if jev is not None:
        print(f"Jev cost: {jev.input_tokens} input tokens, ${jev.est_cost_usd:.6f} at ${JEV_INPUT_USD_PER_MTOK}/Mtok")
    failed = sorted({r.provider for r in rows if r.errors == r.n})
    if failed:
        print(f"Did not answer at all (see the docs in app/decision): {', '.join(failed)}")
    print("READING:", recommend([r for r in rows if not r.provider.startswith(("fake", "rules"))]))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
