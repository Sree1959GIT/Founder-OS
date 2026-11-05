"""Fine-tune Laya for FounderOS's routing, on the founder's RTX 4080 Laptop (12 GB, shared with n8n's Ollama models).

Run it from a separate environment, because `laya` brings PyTorch and FounderOS itself does not need it:

    py -3.11 -m venv .venv-laya
    .venv-laya\\Scripts\\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu124
    .venv-laya\\Scripts\\python.exe -m pip install laya

    .venv-laya\\Scripts\\python.exe scripts\\finetune_laya.py --dry-run     writes the training file and checks the GPU
    docker exec ollama ollama stop qwen3:8b                                 frees about 6 GB; it reloads when used
    .venv-laya\\Scripts\\python.exe scripts\\finetune_laya.py               1 to 2 hours; Ctrl+C stops it

It uses only the standard library until the training step, so `--dry-run` works from the main `.venv` too. Training
data: the `train` split of `backend/app/evals/routing_examples.json`, plus corrected lines of the decision log. The
`test` split stays held out for `scripts/eval_decision_models.py --laya models/laya-founderos`.

API as documented in github.com/NandhaKishorM/laya/blob/main/docs/finetune.md (read 2026-11-05):
`finetune(data, base, out, TrainConfig(...))`; JSONL lines of `state`, `questions`, `expected`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

EXAMPLES = ROOT / "backend" / "app" / "evals" / "routing_examples.json"
DEFAULT_LOG = ROOT / "data" / "default" / "decision_log.jsonl"
DEFAULT_OUT = ROOT / "models" / "laya-founderos"
OPTION_TEXT = {
    "finance": "a question answered from the company's financial metrics",
    "knowledge": "a question answered from the founder's notes and past decisions",
    "decision": "a choice the founder is weighing, which needs a team to analyse it",
    "chitchat": "small talk, with nothing to look up",
    "financial_analyst": "metrics, scenarios and runway",
    "librarian": "the founder's notes and past decisions",
    "market_scout": "market size, competitors and local conditions",
    "revenue_customer": "pricing, churn, pipeline and customer segments",
    "people_ops": "hiring plan, capacity, ownership and execution",
    "regulatory_tax": "licences, tax and compliance",
    "prioritiser": "ranking a list of options",
    "perspective_lens": "one outside viewpoint, such as an investor",
    "devils_advocate": "a pre-mortem: what could go wrong",
    "backchannel": "an acknowledgement, nothing to do",
    "answerable_now": "asks about the progress of the running work",
    "amendment": "changes the running request or its inputs",
    "new_question": "a separate request for later",
    "stop": "stop the running work",
}
# Micro-batches are small because the GPU is shared: 4 x 16 keeps the effective batch at the documented 64.
TRAIN_DEFAULTS: dict[str, Any] = {"epochs": 8, "micro_batch": 4, "grad_accum": 16, "seed": 42}
MIN_FREE_MB = 5000


def case_line(question: str, options: list[str], state: dict[str, Any], label: str) -> dict[str, Any]:
    criteria = {o: OPTION_TEXT.get(o, o) for o in options}
    return {
        "state": state,
        "questions": {"pick": {"type": "choice", "instructions": question, "criteria": criteria}},
        "expected": {"pick": label},
    }


def corrected_log_lines(path: Path) -> list[dict[str, Any]]:
    """Decisions the founder corrected: the data flywheel of PRD F7. Lines that are not corrected are not labels."""
    if not path.is_file():
        return []
    decisions: dict[str, dict[str, Any]] = {}
    corrections: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if "correction_for" in row:
            corrections[row["correction_for"]] = row.get("correct", "")
        elif row.get("id"):
            decisions[row["id"]] = row
    lines = []
    for decision_id, label in corrections.items():
        row = decisions.get(decision_id)
        if row and label in row.get("options", []):
            lines.append(case_line(row["question"], row["options"], row.get("state") or {}, label))
    return lines


def training_lines(examples_path: Path = EXAMPLES, log_path: Path = DEFAULT_LOG) -> list[dict[str, Any]]:
    from app.evals.decision_bakeoff import QUESTIONS, load_examples

    lines = []
    for example in load_examples(examples_path, split="train"):
        question, options = QUESTIONS[example.kind]
        lines.append(case_line(question, list(options), example.state(), example.label))
    return lines + corrected_log_lines(log_path)


def write_training_file(path: Path, lines: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    path.write_text(text, encoding="utf-8", newline="\n")


def free_gpu_mb() -> int | None:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout
        return int(out.splitlines()[0].strip())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="write the training file, check the GPU, do not train")
    parser.add_argument("--base", default="english", help="Laya base checkpoint (default: english)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="decision log with corrections")
    parser.add_argument("--epochs", type=int, default=TRAIN_DEFAULTS["epochs"])
    parser.add_argument("--micro-batch", type=int, default=TRAIN_DEFAULTS["micro_batch"])
    parser.add_argument("--grad-accum", type=int, default=TRAIN_DEFAULTS["grad_accum"])
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--force", action="store_true", help="train even with little free GPU memory")
    args = parser.parse_args()

    lines = training_lines(log_path=args.log)
    data = args.out.parent / f"{args.out.name}-train.jsonl"
    write_training_file(data, lines)
    free = free_gpu_mb()
    print(f"TRAINING FILE: {data} ({len(lines)} examples)")
    print(f"GPU FREE: {free if free is not None else 'unknown'} MB (want {MIN_FREE_MB} MB; Ollama models use it too)")
    print(f"SETTINGS: epochs {args.epochs}, micro-batch {args.micro_batch} x {args.grad_accum}, base {args.base}")
    if args.dry_run:
        print("DRY RUN: nothing trained.")
        return 0
    if free is not None and free < MIN_FREE_MB and not args.force:
        print(
            "Not enough free GPU memory: stop an Ollama model, for example `docker exec ollama ollama stop qwen3:8b`."
        )
        return 2
    try:
        from laya.train import TrainConfig, finetune  # type: ignore[import-not-found]
    except ImportError:
        print("The laya package is not installed in this Python. See the top of this script.")
        return 2
    config = TrainConfig(
        epochs=args.epochs,
        micro_batch=args.micro_batch,
        grad_accum=args.grad_accum,
        seed=TRAIN_DEFAULTS["seed"],
        gradient_checkpointing=True,
    )
    report = finetune(str(data), args.base, str(args.out), config, device=args.device)
    print(f"DONE: {args.out}")
    print(
        json.dumps(
            {k: report[k] for k in ("train_items", "calibration_items", "temperature") if k in report}, default=str
        )
    )
    print(f"Next: .venv-laya\\Scripts\\python.exe scripts\\eval_decision_models.py --laya {args.out} --llm qwen3:8b")
    return 0


if __name__ == "__main__":
    sys.exit(main())
