"""`LayaProvider`: local, open-weight Laya (Convai Innovations, Apache-2.0), on the GPU or the CPU.

Built against the documented API (github.com/NandhaKishorM/laya, read 2026-11-05):

    from laya import Router
    router = Router(max_loaded=1, device="cuda")
    result = router.predict(state, {"pick": {"type": "choice", "instructions": "...", "criteria": {"a": "..."}}})
    result["answers"]["pick"] == {"choice": "a", "confidence": 0.9, "probabilities": {"a": 0.9, "b": 0.1}}

A fine-tuned checkpoint loads with `laya.load(path)` and answers `agent.predict(state, questions)` the same way.
`laya` needs PyTorch, so it is an optional install and imported only here, when this provider is chosen. Without it,
or without its weights, every call raises `DecisionError`, and the service falls back to the LLM (PRD R3).

The base model performs near chance until it is fine-tuned, so a default never points here. See PRD F7.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any

from app.decision.base import Decision, DecisionError, _validate
from app.llm.base import Timer

QUESTION_ID = "pick"
Predictor = Callable[[Any, dict[str, Any]], dict[str, Any]]


def questions_for(question: str, options: list[str]) -> dict[str, Any]:
    return {QUESTION_ID: {"type": "choice", "instructions": question, "criteria": {o: o for o in options}}}


def parse_answer(result: dict[str, Any], options: list[str], question_id: str = QUESTION_ID) -> tuple[str, float]:
    """(choice, probability) from a System One style response, shared by Laya and Jev. Raises on anything unusable."""
    try:
        answer = result["answers"][question_id]
        choice = str(answer["choice"])
        probabilities = answer.get("probabilities") or {}
        probability = float(probabilities[choice]) if choice in probabilities else float(answer["confidence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionError(f"unusable answer ({type(exc).__name__}: {exc})") from exc
    if choice not in options:
        raise DecisionError(f"chose {choice!r}, which is not an option")
    return choice, min(max(probability, 0.0), 1.0)


def _load_predictor(checkpoint: str, device: str) -> Predictor:
    try:
        import laya  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DecisionError("the laya package is not installed: see scripts/finetune_laya.py") from exc
    kwargs = {"device": device} if device else {}
    try:
        if checkpoint:
            agent = laya.load(checkpoint)
            return agent.predict
        router = laya.Router(max_loaded=1, **kwargs)
        return router.predict
    except Exception as exc:  # a missing checkpoint or an out-of-memory GPU must not stop the run
        raise DecisionError(f"Laya could not load: {type(exc).__name__}: {exc}") from exc


class LayaProvider:
    """Loads on the first call, off the event loop, and keeps the checkpoint resident."""

    name = "laya"

    def __init__(self, checkpoint: str = "", device: str = "", predictor: Predictor | None = None) -> None:
        self.checkpoint = checkpoint
        self.device = device
        self._predictor = predictor
        self._lock = threading.Lock()

    def _predict(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._predictor is None:
                self._predictor = _load_predictor(self.checkpoint, self.device)
            try:
                return self._predictor(state, questions)
            except DecisionError:
                raise
            except Exception as exc:
                raise DecisionError(f"Laya failed: {type(exc).__name__}: {exc}") from exc

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        _validate(options)
        timer = Timer()
        result = await asyncio.to_thread(self._predict, state, questions_for(question, options))
        choice, probability = parse_answer(result, options)
        model = self.checkpoint or (result.get("routing") or {}).get("model") or "laya"
        return Decision(
            question=question,
            options=options,
            choice=choice,
            probability=probability,
            provider=f"laya:{model}",
            latency_ms=timer.ms,
        )
