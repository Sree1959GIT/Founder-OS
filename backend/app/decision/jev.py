"""`JevProvider`: TypeSafe AI's Jev, a closed, paid cloud decision model. Optional, and off unless configured.

Built against the documented API (docs.typesafe.ai, read 2026-11-05), over httpx so no SDK is needed:

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer <JEV_API_KEY>
    {"model": "jev-latest", "state": ..., "questions": {"pick": {"type": "choice", "instructions": "...",
                                                                 "criteria": {"a": "..."}}}}
    -> {"model": "jev-1.14.0", "answers": {"pick": {"choice": "a", "confidence": 0.9, "probabilities": {...}}},
        "usage": {"input_tokens": 12, "output_tokens": 0}}

Input is billed at $0.042 per million tokens; output is free (docs.typesafe.ai/models, read 2026-11-05).

**Jev only ever receives non-sensitive routing state** (PRD F7). `routing_state` keeps a short list of fields, removes
data rows, emails and names through the privacy filter, and replaces every number. If that filter cannot read the
names, nothing is sent.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from loguru import logger

from app.decision.base import Decision, DecisionError, _validate
from app.decision.laya import parse_answer, questions_for
from app.llm.base import Timer
from app.llm.privacy import NameIndex, NamesUnavailable, filter_text

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_INPUT_USD_PER_MTOK = 0.042
ROUTING_FIELDS = frozenset({"message", "turn", "running"})  # the only state that may leave the PC
_NUMBER = re.compile(r"[$€£₹]?\d[\d,.]*\s*(?:%|k\b|m\b|bn\b|million\b|thousand\b)?", re.I)
MAX_FIELD_CHARS = 500


def routing_state(state: dict[str, Any], names: NameIndex | None = None) -> dict[str, str]:
    """What a routing decision may send. Amounts say nothing about where a question goes, so they do not travel."""
    if names is not None:
        names.refresh()
    kept: dict[str, str] = {}
    for key, value in state.items():
        if key in ROUTING_FIELDS and isinstance(value, str):
            kept[key] = _NUMBER.sub("[number]", filter_text(value, None, names))[:MAX_FIELD_CHARS]
    return kept


class JevProvider:
    name = "jev"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "jev-latest",
        url: str = JEV_URL,
        timeout_s: float = 10.0,
        names: NameIndex | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key = api_key
        self.model = model
        self.url = url
        self.timeout_s = timeout_s
        self.names = names
        self._transport = transport
        self.input_tokens = 0

    @property
    def est_cost_usd(self) -> float:
        return self.input_tokens / 1_000_000 * JEV_INPUT_USD_PER_MTOK

    async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
        _validate(options)
        if not self._key:
            raise DecisionError("Jev has no API key")
        timer = Timer()
        try:
            sent = routing_state(state, self.names)
        except NamesUnavailable as exc:  # fails closed
            raise DecisionError(f"the privacy filter could not read the names to hide: {exc}") from exc
        body = {"model": self.model, "state": sent, "questions": questions_for(question, options)}
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as client:
                response = await client.post(self.url, json=body, headers=headers)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # The exception type only: a response body or request could echo the key or the state.
            logger.info("Jev call failed: {}", type(exc).__name__)
            raise DecisionError(f"Jev call failed: {type(exc).__name__}") from exc
        choice, probability = parse_answer(data, options)
        usage = data.get("usage") or {}
        self.input_tokens += int(usage.get("input_tokens") or 0)
        return Decision(
            question=question,
            options=options,
            choice=choice,
            probability=probability,
            provider=f"jev:{data.get('model') or self.model}",
            latency_ms=timer.ms,
        )
