"""Verifier (PRD F3): deterministic checks on agent answers.

1. Every number in the text must match a number the agent's tools produced (each tool result carries lineage), within
   rounding: 1 % relative, and a percentage may be written for a ratio (72.13 % for 0.7213) and vice versa.
   Years, YYYY-MM months and small counting words ("3 months", "2 options") are not treated as financial figures.
   Numbers that appear in the brief or the founder's message may be repeated.
2. A Librarian answer must cite at least one source, and every `*.md`/`*.pdf`/`*.csv` path it mentions must be one
   its searches returned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agents.events import Citation

NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<sign>[-\u2212])?(?P<cur>[$€£₹])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<suffix>%|percent\b|[kKmMbB]\b|bn\b|million\b|thousand\b|billion\b)?"
)
MONTH_RE = re.compile(r"\b(19|20)\d{2}-(0[1-9]|1[0-2])(-\d{2})?\b")
PATH_RE = re.compile(r"[\w./-]+\.(?:md|pdf|csv|xlsx|txt)\b")
SMALL_INT_MAX = 12
REL_TOL = 0.01

_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}


@dataclass
class VerifierReport:
    ok: bool
    unverified_numbers: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Figure:
    text: str
    value: float
    percent: bool


def extract_figures(text: str) -> list[Figure]:
    """Financial-looking numbers in `text` (dates, years and small counting integers are skipped)."""
    cleaned = MONTH_RE.sub(" ", text)
    figures: list[Figure] = []
    for m in NUMBER_RE.finditer(cleaned):
        raw = m.group("num")
        value = float(raw.replace(",", ""))
        suffix = (m.group("suffix") or "").lower()
        is_int = "." not in raw and "," not in raw
        if not suffix and not m.group("cur") and is_int and (value <= SMALL_INT_MAX or 1900 <= value <= 2100):
            continue
        value *= _SCALE.get(suffix, 1.0)
        if m.group("sign"):
            value = -value
        figures.append(Figure(m.group(0).strip(), value, suffix in ("%", "percent")))
    return figures


def _close(a: float, b: float) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) / scale <= REL_TOL


def number_supported(figure: Figure, known: list[float]) -> bool:
    candidates = [figure.value, abs(figure.value)]
    if figure.percent:
        candidates.append(figure.value / 100)
    else:
        candidates.append(figure.value * 100)  # "0.72" written for a 72 % value is rare but harmless
    return any(_close(c, k) or _close(c, abs(k)) for c in candidates for k in known)


def verify_numbers(text: str, known: list[float], context: str = "") -> list[str]:
    """Figures in `text` that match neither a tool result nor a number in `context` (brief / user message)."""
    allowed = list(known) + [f.value for f in extract_figures(context)]
    return [f.text for f in extract_figures(text) if not number_supported(f, allowed)]


def verify_citations(text: str, citations: list[Citation]) -> list[str]:
    issues: list[str] = []
    cited = {c.path for c in citations}
    if text.strip() and not cited:
        issues.append("the answer cites no vault source")
    for path in sorted(set(PATH_RE.findall(text))):
        if path not in cited:
            issues.append(f"{path} was not returned by a search")
    return issues


def verify(
    text: str,
    known_numbers: list[float],
    citations: list[Citation],
    *,
    needs_citations: bool,
    context: str = "",
) -> VerifierReport:
    unverified = verify_numbers(text, known_numbers, context)
    issues = [f"number without lineage: {n}" for n in unverified]
    if needs_citations:
        issues += verify_citations(text, citations)
    return VerifierReport(ok=not issues, unverified_numbers=unverified, issues=issues)
