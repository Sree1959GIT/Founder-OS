"""Founder F12: what a decision cost, in the member's own currency.

- `FxRates` keeps one USD-based exchange-rate table, fetched at most once a day from a free source that needs no key
  (`FX_RATES_URL`, default open.er-api.com) and cached in `<DATA_DIR>/fx_rates.json`. Any failure, or a currency the
  table lacks, means US dollars: a cost is never shown in a currency we could not convert to.
- `SpendReport` is counted in code from the agents' own call records (no model does any arithmetic here, PRD §3):
  the estimated USD cost, the cloud calls per provider, and whether local (Qwen) parts were used.
- `money` writes "about ₹1", "about $0.02", "less than ₹1".

The cost cap is entered and shown in the member's currency but stored in USD (`to_usd` / `from_usd`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

FILE_NAME = "fx_rates.json"
MAX_AGE = timedelta(days=1)
SYMBOLS = {
    "USD": "$",
    "INR": "₹",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "CN¥",
    "AUD": "A$",
    "CAD": "C$",
    "SGD": "S$",
    "NZD": "NZ$",
    "HKD": "HK$",
    "AED": "AED ",
    "SAR": "SAR ",
    "CHF": "CHF ",
    "ZAR": "R",
    "BRL": "R$",
    "KRW": "₩",
    "NGN": "₦",
    "PHP": "₱",
}

Fetcher = Callable[[str], Awaitable[dict[str, Any]]]


async def _fetch(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {}


class RateTable(BaseModel):
    base: str = "USD"
    rates: dict[str, float] = Field(default_factory=dict)
    fetched_at: datetime | None = None
    source: str = ""


class FxRates:
    """Daily USD rates, cached on disk. `rate()` never blocks or fails: no table means 1.0 in USD."""

    def __init__(self, data_dir: Path, url: str, *, fetcher: Fetcher = _fetch) -> None:
        self.path = data_dir / FILE_NAME
        self.url = url
        self._fetcher = fetcher
        self._table = self._load()
        self._refreshing: asyncio.Task[None] | None = None

    def _load(self) -> RateTable:
        try:
            return RateTable.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return RateTable()

    @property
    def stale(self) -> bool:
        fetched = self._table.fetched_at
        return fetched is None or datetime.now(UTC) - fetched > MAX_AGE

    async def refresh(self) -> None:
        """Fetch today's table if the cached one is older than a day. Failures keep the old table (or USD)."""
        if not self.url or not self.stale:
            return
        try:
            data = await self._fetcher(self.url)
            rates = data.get("rates") if data.get("result", "success") == "success" else None
            if not isinstance(rates, dict) or not rates:
                raise ValueError("no rates in the answer")
            clean = {str(k).upper(): float(v) for k, v in rates.items() if isinstance(v, int | float) and v > 0}
            self._table = RateTable(rates=clean, fetched_at=datetime.now(UTC), source=self.url.split("/")[2])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self._table.model_dump_json(), encoding="utf-8")
            logger.info("Exchange rates updated ({} currencies)", len(clean))
        except (httpx.HTTPError, ValueError, OSError, TypeError) as exc:
            logger.info("Exchange rates not updated ({}): the cached rate or US dollars stand", type(exc).__name__)

    def refresh_soon(self) -> None:
        """Start a refresh in the background when the table is stale (from sync code, inside a running loop)."""
        if not self.url or not self.stale or (self._refreshing is not None and not self._refreshing.done()):
            return
        try:
            self._refreshing = asyncio.get_running_loop().create_task(self.refresh())
        except RuntimeError:
            return

    def rate(self, currency: str) -> tuple[str, float]:
        """(the currency shown, USD -> it). A currency with no known rate is shown in USD."""
        currency = (currency or "USD").upper()
        if currency == "USD":
            return "USD", 1.0
        self.refresh_soon()
        rate = self._table.rates.get(currency)
        return (currency, rate) if rate else ("USD", 1.0)

    def info(self, currency: str) -> dict[str, Any]:
        shown, rate = self.rate(currency)
        fetched = self._table.fetched_at
        return {
            "asked": (currency or "USD").upper(),
            "currency": shown,
            "symbol": SYMBOLS.get(shown, f"{shown} "),
            "rate": rate,
            "as_of": fetched.date().isoformat() if fetched and shown != "USD" else None,
            "source": self._table.source if shown != "USD" else "",
        }


def symbol(currency: str) -> str:
    return SYMBOLS.get(currency, f"{currency} ")


def money(usd: float, currency: str, rate: float) -> str:
    """ "about ₹1", "about $0.04", "less than ₹1": rounded for reading, never more precise than an estimate."""
    amount = usd * rate
    sign = symbol(currency)
    if amount <= 0:
        return "nothing"
    if amount < 0.01:
        return f"less than {sign}0.01"
    if amount < 1:
        return f"about {sign}{amount:.2f}"
    if amount < 10 and abs(amount - round(amount)) >= 0.05:
        return f"about {sign}{amount:.1f}"
    return f"about {sign}{amount:,.0f}"


def usd_text(usd: float) -> str:
    """Founder F12b: US dollars in small print, to 2 decimals ("US$0.29", never "US$0.2850")."""
    if 0 < usd < 0.005:
        return "less than US$0.01"
    cents = Decimal(str(usd)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # 0.2850 -> 0.29, not 0.28
    return f"US${cents}"


def to_usd(amount: float, rate: float) -> float:
    return round(amount / rate, 6) if rate > 0 else amount


def from_usd(usd: float, rate: float) -> float:
    return round(usd * rate, 2)


class SpendReport(BaseModel):
    """One decision's cost, counted in code from the agents' call records."""

    usd: float | None = Field(0.0, description="None: a model with no known price was used")
    cloud_calls: dict[str, int] = Field(default_factory=dict, description="Provider label -> calls")
    local_parts: bool = False

    @property
    def cloud_used(self) -> bool:
        return any(self.cloud_calls.values())

    def sentence(self, currency: str, rate: float) -> str:
        """ "This decision cost about ₹1: Gemini 4 calls; Qwen parts free." (or "nothing: … on Qwen")."""
        if not self.cloud_used:
            return "This decision cost nothing: all of it ran on Qwen on our server."
        calls = ", ".join(f"{name} {n} call{'s' if n != 1 else ''}" for name, n in self.cloud_calls.items())
        unknown = "an unknown amount (a model with no known price)"
        cost = unknown if self.usd is None else money(self.usd, currency, rate)
        free = "; Qwen parts free" if self.local_parts else ""
        return f"This decision cost {cost}: {calls}{free}."


def spend_of(results: list[Any], *, advisor_local: bool = False) -> SpendReport:
    """From `AgentResult`s: their `cloud_calls` and `est_cost_usd`. The Advisor itself always runs on Qwen."""
    calls: dict[str, int] = {}
    usd: float | None = 0.0
    local = advisor_local
    for result in results:
        for name, n in getattr(result, "cloud_calls", {}).items():
            calls[name] = calls.get(name, 0) + n
        if getattr(result, "local_calls", 0):
            local = True
        cost = getattr(result, "est_cost_usd", 0.0)
        usd = None if usd is None or cost is None else round(usd + cost, 6)
    return SpendReport(usd=usd, cloud_calls=calls, local_parts=local)
