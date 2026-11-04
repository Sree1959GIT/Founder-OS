"""Verifier (PRD F3): deterministic checks on agent answers.

1. Every number in the text must match a number the model was shown by its tools (each tool result carries lineage),
   within the written rounding ("$1.2M" covers 1,150,000-1,250,000) or 1 % relative, whichever is wider. A
   percentage may be written for a ratio (72.13 % for 0.7213). Years, YYYY-MM months, written dates ("15 Dec") and
   small counting words ("3 months", "2 options") are not treated as financial figures. Numbers in the founder's
   own message may be repeated; numbers in a Planner-written brief may not (that is LLM text).
2. A Librarian answer must name at least one source path that its searches returned, and every
   `*.md`/`*.pdf`/`*.csv` path it names must be one of them.
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
_MONTH_NAME = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?"
    r"|Nov(?:ember)?|Dec(?:ember)?)\b\.?"
)
_DAY = r"\d{1,2}(?:st|nd|rd|th)?\b(?!\s?%)"
WRITTEN_DATE_RE = re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MONTH_NAME}|\b{_MONTH_NAME}\s+{_DAY}")
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
    rounding: float = 0.0  # half a unit of the last written digit, after scaling ("$1.2M" -> 50,000)


def extract_figures(text: str) -> list[Figure]:
    """Financial-looking numbers in `text` (dates, years and small counting integers are skipped)."""
    cleaned = WRITTEN_DATE_RE.sub(" ", MONTH_RE.sub(" ", text))
    figures: list[Figure] = []
    for m in NUMBER_RE.finditer(cleaned):
        raw = m.group("num")
        value = float(raw.replace(",", ""))
        suffix = (m.group("suffix") or "").lower()
        is_int = "." not in raw and "," not in raw
        if not suffix and not m.group("cur") and is_int and (value <= SMALL_INT_MAX or 1900 <= value <= 2100):
            continue
        scale = _SCALE.get(suffix, 1.0)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value *= scale
        if m.group("sign"):
            value = -value
        figures.append(Figure(m.group(0).strip(), value, suffix in ("%", "percent"), 0.5 * 10**-decimals * scale))
    return figures


def _close(a: float, b: float, rounding: float = 0.0) -> bool:
    """Equal within the written rounding (e.g. "$1.2M" for 1,234,567) or REL_TOL, whichever is wider."""
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return abs(a - b) <= rounding + 1e-9 or (scale > 0 and abs(a - b) / scale <= REL_TOL)


def number_supported(figure: Figure, known: list[float]) -> bool:
    r = figure.rounding
    candidates = [(figure.value, r), (abs(figure.value), r)]
    if figure.percent:
        candidates.append((figure.value / 100, r / 100))
    else:
        candidates.append((figure.value * 100, r * 100))  # "0.72" written for a 72 % value is rare but harmless
    return any(_close(c, k, tol) or _close(c, abs(k), tol) for c, tol in candidates for k in known)


def verify_numbers(text: str, known: list[float], context: str = "") -> list[str]:
    """Figures in `text` that match neither a tool result nor a number in `context` (the founder's message)."""
    allowed = list(known) + [f.value for f in extract_figures(context)]
    return [f.text for f in extract_figures(text) if not number_supported(f, allowed)]


def verify_citations(text: str, citations: list[Citation]) -> list[str]:
    """The answer must name at least one source path, and every path it names must have been returned."""
    issues: list[str] = []
    returned = {c.path for c in citations}
    named = set(PATH_RE.findall(text))
    if text.strip() and not named & returned:
        issues.append("the answer cites no vault source")
    for path in sorted(named - returned):
        issues.append(f"{path} was not returned by a search")
    return issues


def named_paths(text: str) -> set[str]:
    return set(PATH_RE.findall(text))


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
