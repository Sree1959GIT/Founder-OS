"""The labelled question set: routing, sources, figures and the goal check, on questions from every category.

    python scripts/eval_labelled.py                         offline: no Ollama, no backend, about a minute
    python scripts/eval_labelled.py --live --category hires the real model, through a running backend (minutes)
    python scripts/eval_labelled.py --live                  every question: an hour or so

Live runs can write memos into that backend's vault when a question asks for one: use a test backend, or delete them
afterwards. Ambiguous turns are checked by the rules in both modes, because they never go through a chat.
Prints one line per failure, one line per category, then a total.
Exit code 0 when every check passes, 1 otherwise, 2 when the backend cannot be reached.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
from loguru import logger

from app.agents.decision_frame import DecisionFrame
from app.evals.labelled_eval import (
    CATEGORIES,
    LabelledCase,
    LabelledResult,
    check_chat,
    load_cases,
    run_offline,
    run_offline_async,
    summary,
)


def run_live(url: str, cases: list[LabelledCase]) -> list[LabelledResult] | None:
    results: list[LabelledResult] = []
    with httpx.Client(base_url=url, timeout=1200.0) as client:
        for case in cases:
            if case.turn_kind:
                results += asyncio.run(run_offline_async([case]))
                continue
            try:
                response = client.post("/api/chat", json={"message": case.question, "stream": False})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"Cannot get an answer from {url}: {type(exc).__name__}: {exc}. Is run.bat running?")
                return None
            reply = response.json()
            frame = reply.get("decision_frame")
            result = check_chat(case, "live", reply, DecisionFrame.model_validate(frame) if frame else None)
            print(
                f"... {case.id}: {'pass' if result.passed else 'FAIL'} ({result.latency_ms / 1000:.0f} s)", flush=True
            )
            results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="ask a running backend (real model)")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="backend URL for --live")
    parser.add_argument("--category", choices=CATEGORIES, help="only this category")
    args = parser.parse_args()
    logger.remove()

    cases = [c for c in load_cases() if not args.category or c.category == args.category]
    results = run_live(args.url, cases) if args.live else run_offline(cases)
    if results is None:
        return 2
    for result in results:
        if not result.passed:
            print(f"FAIL {result.id}: {'; '.join(result.problems)}")
    print("\n".join(summary(results)))
    passed = sum(r.passed for r in results)
    print(f"{'LIVE' if args.live else 'OFFLINE'} LABELLED EVAL: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
