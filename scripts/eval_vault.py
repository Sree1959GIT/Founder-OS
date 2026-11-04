"""Vault eval: do past decisions, citations and key facts reach the founder? Prints one line per question.

    python scripts/eval_vault.py                 offline: no Ollama, no backend, seconds
    python scripts/eval_vault.py --live          the real model, through a running backend (minutes)
    python scripts/eval_vault.py --live --only same-decision-again

Exit code 0 when every check passes, 1 otherwise, 2 when the backend cannot be reached.
"""

from __future__ import annotations

import argparse
import sys

import httpx
from loguru import logger

from app.evals.vault_eval import EvalResult, check_live_reply, load_cases, run_offline


def run_live(url: str, only: str | None) -> list[EvalResult] | None:
    results: list[EvalResult] = []
    with httpx.Client(base_url=url, timeout=900.0) as client:
        for case in load_cases():
            if only and case.id != only:
                continue
            try:
                response = client.post("/api/chat", json={"message": case.question, "stream": False})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"Cannot get an answer from {url}: {type(exc).__name__}: {exc}. Is run.bat running?")
                return None
            result = check_live_reply(case, response.json())
            print(result.line(), flush=True)
            results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="ask a running backend (real model) instead of the fakes")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="backend URL for --live")
    parser.add_argument("--only", help="run one question id (with --live)")
    args = parser.parse_args()
    logger.remove()
    if args.live:
        results = run_live(args.url, args.only)
        if results is None:
            return 2
    else:
        results = run_offline()
        for result in results:
            print(result.line())
    passed = sum(r.passed for r in results)
    print(f"{'LIVE' if args.live else 'OFFLINE'} EVAL: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
