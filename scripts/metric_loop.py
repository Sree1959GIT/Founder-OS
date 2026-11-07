"""Time a single-metric question through a running backend, and check that it verifies, N times.

    python scripts/metric_loop.py                       "What's our runway?", 10 times, http://127.0.0.1:8000
    python scripts/metric_loop.py --count 5 --base http://127.0.0.1:8011 --question "What's our MRR?"

The last line is the summary to compare with the Windows checklist. Target: under 8 s warm, verified every time.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

TARGET_S = 8.0


def ask(base: str, question: str) -> tuple[float, dict]:
    request = urllib.request.Request(
        f"{base}/api/chat",
        data=json.dumps({"message": question, "stream": False}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=600) as response:
        body = json.load(response)
    return time.perf_counter() - started, body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default="What's our runway?")
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    times: list[float] = []
    verified = 0
    for i in range(1, args.count + 1):
        seconds, body = ask(args.base, args.question)
        times.append(seconds)
        verified += bool(body["verified"])
        by_code = bool(body["agents"]) and body["agents"][0].get("written_by_code", False)
        print(f"{i:>2}. {seconds:5.1f} s  verified {body['verified']}  by code {by_code}  {body['answer']}", flush=True)
        for issue in body["issues"]:
            print(f"    issue: {issue}", flush=True)
    ordered = sorted(times)
    print(
        f"METRIC LOOP: verified {verified}/{args.count} | median {ordered[len(ordered) // 2]:.1f} s | "
        f"slowest {ordered[-1]:.1f} s | target under {TARGET_S:.0f} s"
    )
    return 0 if verified == args.count and ordered[-1] < TARGET_S else 1


if __name__ == "__main__":
    sys.exit(main())
