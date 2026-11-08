"""A figure may only be stated for a period the tools covered (founder review 49).

The scenario engine projects a set number of months (12 by default). "What will our MRR be in 2031?" must not get the
month-12 figure as if it were 2031. Code works out which period the question asks about and which months the
projection covers. If the question is beyond them, code writes the answer's first sentence: what the projection
covers, with its last month's figure, labelled as an assumption. Then the prose may add no figure of its own.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

from pydantic import BaseModel

from app.agents.verifier import extract_figures, split_sentences
from app.engine.scenario import ScenarioResult

ASSUMPTION = "assumption, confirm"
_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10, "a": 1, "an": 1}
_N = r"(\d{1,2}|one|two|three|four|five|six|ten|an?)"
_MONTH_YEAR = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?,?\s+(20\d\d)\b", re.I)
_YEAR = re.compile(r"\b(20\d\d)\b")
_IN_YEARS = re.compile(rf"\b(?:in\s+{_N}\s+years?|{_N}\s+years?\s+(?:from now|out|ahead|time))\b", re.I)
_IN_MONTHS = re.compile(rf"\b(?:in\s+{_N}\s+months?|{_N}\s+months?\s+(?:from now|out|ahead|time))\b", re.I)
_NEXT_YEAR = re.compile(r"\bnext\s+year\b", re.I)


class Projection(BaseModel):
    """What the first run_scenario covered: its months and its last month's figures (computed in code)."""

    as_of: str
    first_month: str
    last_month: str
    months: int
    mrr: float
    cash: float
    adjusted: bool
    currency: str = "USD"

    @classmethod
    def of(cls, result: ScenarioResult) -> Projection | None:
        if not result.points:
            return None
        last = result.points[-1]
        adjusted = result.adjustments.model_dump() != type(result.adjustments)().model_dump()
        return cls(
            as_of=result.as_of,
            first_month=result.points[0].month,
            last_month=last.month,
            months=len(result.points),
            mrr=float(last.scenario_mrr if adjusted else last.base_mrr),
            cash=float(last.scenario_cash if adjusted else last.base_cash),
            adjusted=adjusted,
            currency=result.currency,
        )


class AskedPeriod(BaseModel):
    label: str  # in the founder's words: "2031", "next year", "in 5 years"
    end: str  # the last month it asks about, "YYYY-MM"


def _ym(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _plus(start: str, months: int) -> str:
    year, month = (int(p) for p in start[:7].split("-"))
    total = year * 12 + (month - 1) + months
    return _ym(total // 12, total % 12 + 1)


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS[word.lower()]


def asked_period(message: str, as_of: str | None) -> AskedPeriod | None:
    """The latest period the question asks about, or None if it names none. `as_of` ("YYYY-MM") anchors "next year"."""
    base = (as_of or date.today().strftime("%Y-%m"))[:7]
    found: list[AskedPeriod] = []
    for m in _MONTH_YEAR.finditer(message):
        found.append(AskedPeriod(label=m.group(0), end=_ym(int(m.group(2)), _MONTHS[m.group(1).lower()])))
    if not found:
        found += [AskedPeriod(label=m.group(1), end=_ym(int(m.group(1)), 12)) for m in _YEAR.finditer(message)]
    if m := _NEXT_YEAR.search(message):
        found.append(AskedPeriod(label=m.group(0), end=_ym(int(base[:4]) + 1, 12)))
    if m := _IN_YEARS.search(message):
        found.append(AskedPeriod(label=m.group(0), end=_plus(base, 12 * _count(m.group(1) or m.group(2)))))
    if m := _IN_MONTHS.search(message):
        found.append(AskedPeriod(label=m.group(0), end=_plus(base, _count(m.group(1) or m.group(2)))))
    return max(found, key=lambda p: p.end) if found else None


def month_words(ym: str) -> str:
    year, month = ym[:7].split("-")
    return f"{calendar.month_abbr[int(month)]} {year}"


def beyond(message: str, projection: Projection | None, as_of: str | None = None) -> AskedPeriod | None:
    """The asked period, when it lies after the last month the tools covered (the projection, or the data month)."""
    anchor = projection.as_of if projection is not None else as_of
    asked = asked_period(message, anchor)
    if asked is None:
        return None
    covered = projection.last_month[:7] if projection is not None else (anchor or "")[:7]
    if not covered:
        return asked if asked.end > date.today().strftime("%Y-%m") else None
    return asked if asked.end > covered else None


def _money(value: float) -> str:
    return f"${value:,.2f}"


def horizon_lead(message: str, asked: AskedPeriod, projection: Projection | None) -> str:
    """Code's first sentence when the question is beyond what the projection covers."""
    if projection is None:
        return (
            f"No projection covers {asked.label}: the scenario model projects at most 12 months ahead of your "
            "latest data, so there is no figure for that date."
        )
    last = month_words(projection.last_month)
    text = message.lower()
    wants_cash = re.search(r"\b(cash|runway|burn|bank)\b", text) is not None
    wants_mrr = re.search(r"\b(mrr|revenue|arr|sales)\b", text) is not None or not wants_cash
    parts = []
    if wants_mrr:
        parts.append(f"MRR of {_money(projection.mrr)}")
    if wants_cash:
        parts.append(f"cash of {_money(projection.cash)}")
    return (
        f"The model projects {projection.months} months, to {last}, so it has no figure for {asked.label}. "
        f"Its last month, {last}, shows {' and '.join(parts)}, which assumes today's trend holds ({ASSUMPTION})."
    )


def beyond_issue(asked: AskedPeriod, projection: Projection | None) -> str:
    """For the badge: the answer rests on a projection that stops before the asked period."""
    if projection is None:
        return f"{asked.label} is beyond any projection"
    return f"{asked.label} is beyond the projection, which ends {month_words(projection.last_month)}"


def names_period(sentence: str, asked: AskedPeriod) -> bool:
    return asked.label.lower() in sentence.lower()


def without_uncovered(text: str, asked: AskedPeriod) -> tuple[str, int]:
    """An agent's sentences that state a figure for the uncovered period are taken out (counted, not shown)."""
    kept: list[str] = []
    removed = 0
    for sentence in split_sentences(text):
        if names_period(sentence, asked) and extract_figures(sentence):
            removed += 1
            continue
        kept.append(sentence)
    return "".join(kept).strip(), removed
