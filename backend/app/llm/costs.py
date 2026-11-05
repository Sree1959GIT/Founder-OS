"""Per-call cost and latency, and the monthly cost cap on cloud models.

Every LLM call is one line in `data/<ws>/llm_calls.jsonl`: who called, which model, tokens, latency and estimated cost.
Never the prompt or the reply. Costs are estimates from the token counts the provider reports and `DEFAULT_PRICES`
(override with `LLM_PRICES`).

The cap fails safe: at or over `CLOUD_MONTHLY_CAP_USD`, and for a model with no known price, the router uses Ollama.
Calls already in flight when the cap is reached still finish, so a month can end slightly over it.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.llm.base import Usage

# USD per million tokens (input, output), standard tier, read from the providers' pricing pages on 2026-11-04.
# Gemini 3.8 Flash doubles on 2027-01-01 and Gemini 4 Argon on 2026-12-01: update these or set LLM_PRICES.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-4-argon": (2.0, 10.0),
    "gpt-6.1-sol": (2.0, 10.0),
    "gpt-6.1-terra": (1.0, 5.0),
    "gpt-6-luna": (0.10, 0.50),
}


class CallRecord(BaseModel):
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_type: str = ""
    provider: str
    model: str
    is_cloud: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    est_cost_usd: float | None = None
    fallback_from: str | None = None
    filtered_items: int = 0
    error: str | None = None


class CostLedger:
    def __init__(
        self,
        path: Path,
        *,
        monthly_cap_usd: float = 25.0,
        prices: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.path = path
        self.monthly_cap_usd = monthly_cap_usd
        self.prices = {**DEFAULT_PRICES, **(prices or {})}
        self._lock = threading.Lock()
        self._records: list[CallRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        month = _month(datetime.now(UTC))
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = CallRecord.model_validate_json(line)
            except ValueError:
                logger.warning("Skipping an unreadable line in {}", self.path.name)
                continue
            if _month(record.at) == month:  # older lines stay in the file; only this month's matter here
                self._records.append(record)

    def estimate(self, model: str, usage: Usage) -> float | None:
        price = self.prices.get(model)
        if price is None:
            return None
        return round((usage.input_tokens * price[0] + usage.output_tokens * price[1]) / 1_000_000, 6)

    def record(self, record: CallRecord) -> CallRecord:
        with self._lock:
            month = _month(record.at)
            self._records = [r for r in self._records if _month(r.at) == month]
            self._records.append(record)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(record.model_dump_json() + "\n")
            except OSError as exc:  # accounting must never break an answer; the month's total is still in memory
                logger.warning("Could not write {}: {}", self.path.name, exc)
        return record

    def month_spend(self) -> float:
        month = _month(datetime.now(UTC))
        with self._lock:
            return round(sum(r.est_cost_usd or 0.0 for r in self._records if _month(r.at) == month), 6)

    def refusal(self, model: str) -> str | None:
        """Why this cloud model may not be called now, or None when it may."""
        if model not in self.prices:
            return f"no known price for {model}: add it to LLM_PRICES"
        spent = self.month_spend()
        if spent >= self.monthly_cap_usd:
            return f"this month's cloud spend ${spent:.2f} reached the ${self.monthly_cap_usd:.2f} cap"
        return None

    def stats(self) -> dict[str, dict[str, Any]]:
        """This month, per agent type: calls, errors, tokens, cost, and latency (mean and p50)."""
        month = _month(datetime.now(UTC))
        grouped: dict[str, list[CallRecord]] = defaultdict(list)
        with self._lock:
            for record in self._records:
                if _month(record.at) == month:
                    grouped[record.agent_type or "unknown"].append(record)
        return {agent: _summary(records) for agent, records in grouped.items()}

    def summary(self) -> dict[str, Any]:
        spent = self.month_spend()
        return {
            "month": _month(datetime.now(UTC)),
            "spent_usd": spent,
            "cap_usd": self.monthly_cap_usd,
            "remaining_usd": round(max(0.0, self.monthly_cap_usd - spent), 6),
            "over_cap": spent >= self.monthly_cap_usd,
        }


def _month(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m")


def _summary(records: list[CallRecord]) -> dict[str, Any]:
    answered = sorted(r.latency_ms for r in records if r.error is None)
    cloud = [r for r in records if r.is_cloud]
    return {
        "calls": len(records),
        "cloud_calls": len(cloud),
        "errors": sum(r.error is not None for r in records),
        "input_tokens": sum(r.input_tokens for r in records),
        "output_tokens": sum(r.output_tokens for r in records),
        "est_cost_usd": round(sum(r.est_cost_usd or 0.0 for r in records), 6),
        "latency_ms_mean": round(sum(answered) / len(answered), 1) if answered else None,
        "latency_ms_p50": answered[len(answered) // 2] if answered else None,
    }


def dumps_for_log(record: CallRecord) -> str:
    return json.dumps(record.model_dump(mode="json", exclude_none=True))
