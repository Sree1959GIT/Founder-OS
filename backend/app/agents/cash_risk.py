"""The Advisor speaks up when cash may run out within a year (founder note 7).

Code runs the seeded Monte Carlo (1,000 runs, no change to the plan) and, when the share of runs whose cash goes below
zero within 12 months reaches `CASH_RISK_WARN_AT`, adds one sentence to a decision or runway answer. The figures are
the routine's, with its lineage, so the Verifier accepts them and the voice may speak them.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel

from app.engine.lineage import Lineage
from app.engine.montecarlo import MonteCarloRequest, run_monte_carlo

RUNS = 1000
# Questions about these metrics are about cash: a warning belongs there. An MRR or CAC lookup gets none.
CASH_METRICS = frozenset({"runway", "net_burn", "gross_burn"})


class CashRisk(BaseModel):
    probability: float  # 0 to 1: share of runs with cash below zero within 12 months
    runs: int
    as_of: str
    sentence: str
    lineage: Lineage

    @property
    def percent(self) -> float:
        return round(self.probability * 100)

    @property
    def figures(self) -> list[float]:
        """The figures the sentence states, for the Verifier."""
        return [float(self.percent), float(self.runs), 12.0]


def cash_risk(finance: Any, warn_at: float) -> CashRisk | None:
    """The warning, or None when the risk is below `warn_at`, warnings are off (`warn_at` > 1) or data is missing."""
    if warn_at > 1 or finance is None or getattr(finance, "scenario", None) is None:
        return None
    try:
        result = run_monte_carlo(finance.scenario, MonteCarloRequest(runs=RUNS))
    except Exception as exc:  # no data, or a broken table: the answer goes out without the warning (R3)
        logger.info("No cash-risk check: {}", exc)
        return None
    probability = float(result.probability_cash_out_within_12_months)
    if probability < warn_at:
        return None
    percent = round(probability * 100)
    sentence = (
        f"A warning: in {percent} % of {RUNS:,} simulated futures with no change to your plan, cash runs out within "
        "12 months, so protecting runway comes first."
    )
    return CashRisk(probability=probability, runs=RUNS, as_of=result.as_of, sentence=sentence, lineage=result.lineage)


def wants_warning(intent: str, metrics_asked: list[str]) -> bool:
    """A decision, or a question about cash (runway, burn), gets the warning. Greetings and other lookups do not."""
    return intent == "decision" or (intent == "finance" and bool(CASH_METRICS & set(metrics_asked)))
