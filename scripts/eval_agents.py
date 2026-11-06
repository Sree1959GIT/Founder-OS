"""Specialist and decision-quality eval. Does each M3b agent join the team and carry what it must, and does a memo pass
the decision rubric (type, costs, goal check, options, outcomes, voice)? Prints one line per check.

    python scripts/eval_agents.py                 offline: no Ollama, no backend, seconds
    python scripts/eval_agents.py --live          the real model, through a running backend (minutes)
    python scripts/eval_agents.py --live --only memo-writer

Live runs write memos into that backend's vault: use a test backend, or delete them afterwards.
Exit code 0 when every check passes, 1 otherwise, 2 when the backend cannot be reached.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx
from loguru import logger

from app.evals import decision_eval
from app.evals.agents_eval import check_reply, load_cases, run_offline


def run_live(url: str, only: str | None) -> list[Any] | None:
    results: list[Any] = []
    with httpx.Client(base_url=url, timeout=1200.0) as client:
        cases: list[Any] = [*load_cases(), *decision_eval.load_cases()]
        for case in cases:
            if only and case.id != only:
                continue
            try:
                response = client.post("/api/chat", json={"message": case.question, "stream": False})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"Cannot get an answer from {url}: {type(exc).__name__}: {exc}. Is run.bat running?")
                return None
            if isinstance(case, decision_eval.DecisionCase):
                # Whether a cited path is a real note is asked of the same backend.
                result: Any = decision_eval.check_decision(
                    case,
                    "live",
                    response.json(),
                    exists=lambda path: client.get(f"/api/vault/notes/{path}").status_code == 200,
                )
            else:
                result = check_reply(case, "live", response.json())
            print(result.line(), flush=True)
            results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="ask a running backend (real model)")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="backend URL for --live")
    parser.add_argument("--only", help="run one question id (with --live)")
    args = parser.parse_args()
    logger.remove()
    if args.live:
        results = run_live(args.url, args.only)
        if results is None:
            return 2
    else:
        results = [*run_offline(), *decision_eval.run_offline()]
        for result in results:
            print(result.line())
    passed = sum(r.passed for r in results)
    print(f"{'LIVE' if args.live else 'OFFLINE'} AGENT EVAL: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
