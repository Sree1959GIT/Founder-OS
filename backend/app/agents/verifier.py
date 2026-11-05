"""Verifier (PRD F3): deterministic checks on agent answers.

1. Every number in the text must match a number the model was shown by its tools (each tool result carries lineage),
   within the written rounding ("$1.2M" covers 1,150,000-1,250,000) or 1 % relative, whichever is wider. A
   percentage may be written for a ratio (72.13 % for 0.7213). Years, YYYY-MM months, written dates ("15 Dec") and
   small counting words ("3 months", "2 options") are not treated as financial figures. Numbers in the founder's
   own message may be repeated; numbers in a Planner-written brief may not (that is LLM text).
2. A figure must keep its meaning. Each tool number is a `Fact` with the label and unit of its field, and the claim
   around the figure must agree: the written unit (money, months, percent, count), the quantity the clause names
   (runway, burn, payroll, cost per hire...) and whether it is a monthly flow or a balance. Matching the value is not
   enough: total payroll called "the cost of hiring a designer" fails. All of this is rules, never an LLM judge.
   A clause that names no known quantity cannot be judged, so a figure there only has to match by value and unit.
3. A Librarian answer must name at least one source path that its searches returned, and every
   `*.md`/`*.pdf`/`*.csv` path it names must be one of them.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

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
_DAY = r"(?:0?[1-9]|[12]\d|3[01])"
_ORDINAL = r"(?:st|nd|rd|th)"
# "15 Dec" can only be a date. "Dec 15" can also be "In March 15 customers churned", so the day must be an ordinal, or
# be followed by a year, the end of a clause or a word that goes with a date. Anything else stays a figure to check.
_DATE_NOUNS = r"(?:review|deadline|meeting|board|check-?in|date)\b"
WRITTEN_DATE_RE = re.compile(
    rf"\b{_DAY}{_ORDINAL}?\s+(?:of\s+)?{_MONTH_NAME}"
    rf"|\b{_MONTH_NAME}\s+{_DAY}{_ORDINAL}\b(?!\s?%)"
    rf"|\b{_MONTH_NAME}\s+{_DAY}\b(?!\s?%)(?=\s*(?:$|[,.;:!?)\]]|\d{{4}}\b|{_DATE_NOUNS}))"
)
PATH_RE = re.compile(r"[\w./-]+\.(?:markdown|md|pdf|csv|xlsx|txt)\b")
SMALL_INT_MAX = 12
REL_TOL = 0.01

_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}


FactKind = Literal["money", "months", "percent", "ratio", "count", "unknown"]

# What a label or a clause is about. Order does not matter; `_SPECIFIC` says which names replace a broader one.
CONCEPTS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern)
    for name, pattern in {
        "runway": r"\brunway\b|\bout of cash\b|\bzero[- ]cash\b|\bruns? out\b",
        "cash": r"(?<!out of )(?<!zero )(?<!zero-)\bcash\b(?![- ]?out)|\bbank balance\b|\bclosing balance\b",
        "net_burn": r"\bnet burn\b",
        "gross_burn": r"\bgross burn\b",
        "burn": r"\bburn\b",
        "mrr": r"\bmrr\b|\bmonthly recurring\b",
        "arr": r"\barr\b|\bannual recurring\b",
        "revenue": r"\brevenue\b",
        "margin": r"\bmargin\b",
        "cac": r"\bcac\b|\bacquisition cost\b",
        "ltv": r"\bltv\b|\blifetime value\b",
        "churn": r"\bchurn\b",
        "nrr": r"\bnrr\b|\bnet revenue retention\b",
        "payback": r"\bpayback\b",
        "arpa": r"\barpa\b",
        "growth": r"\bgrowth\b",
        "payroll": r"\bpayroll\b|\bheadcount\b|\bstaff costs?\b|\bwage bill\b",
        "hire_cost": r"\bcost per hire\b|\bper hire\b|\beach hire\b|\bper head\b|\bmonthly cost delta\b",
    }.items()
}
_SPECIFIC = {"net_burn": "burn", "gross_burn": "burn"}
_KIND_BY_NAME: list[tuple[re.Pattern[str], FactKind]] = [
    (re.compile(p), k)  # type: ignore[misc]
    for p, k in (
        (r"probability", "ratio"),
        (r"customers|^runs$|headcount$", "count"),
        (r"runway|_months$|^months$|payback", "months"),
        (r"(?:^|_)ratio$|margin$|churn$", "ratio"),
        (r"cash|burn|mrr|arr|revenue|cost|delta|payroll|cac|ltv|arpa|spend|receipts|balance|cogs", "money"),
    )
]
_STOCK_NAME = re.compile(r"(?:^|[_ ])cash$|^cash delta$|balance")
# More than one true description: a decision's added monthly cost is also how much its burn rises.
_ALSO_ABOUT = {
    "monthly_cost_delta": frozenset({"burn", "net_burn", "gross_burn"}),
    "probability_cash_out_within_12_months": frozenset({"runway"}),
}
_NAME_ALIASES = {"delta": "cash delta"}  # the scenario's cash difference at the end of the projection


_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}
_WRITTEN_CODE = re.compile(r"(?:[$€£₹]\s?)?(\d[\d,]*(?:\.\d+)?)\s?(USD|EUR|GBP|INR)\b")


def format_money(value: float, currency: str = "USD") -> str:
    """One way to write money everywhere: $11,423.62."""
    symbol = _SYMBOLS.get(currency)
    return f"{symbol}{value:,.2f}" if symbol else f"{value:,.2f} {currency}".strip()


def one_money_format(text: str) -> str:
    """ "11,423.62 USD" and "$11,423.62 USD" become "$11,423.62". The digits are not touched."""
    return _WRITTEN_CODE.sub(lambda m: f"{_SYMBOLS[m.group(2)]}{m.group(1)}", text)


def concepts_in(text: str) -> frozenset[str]:
    lowered = text.lower().replace("_", " ")
    found = {name for name, pattern in CONCEPTS.items() if pattern.search(lowered)}
    return frozenset(found - {broad for specific, broad in _SPECIFIC.items() if specific in found})


def _with_broader(concepts: frozenset[str]) -> frozenset[str]:
    """Net burn is also burn, so "burn is $172,280.47" holds. A claim of net burn does not hold for gross burn."""
    return concepts | {broad for specific, broad in _SPECIFIC.items() if specific in concepts}


@dataclass(frozen=True)
class Fact:
    """A number a tool showed the model, with the meaning of the field it came from.

    An empty `label` means an unlabelled number (a passage quoted from a note, whose citation backs it): only its value
    can be checked. A labelled fact with no `concepts` is about something outside the vocabulary.
    """

    value: float
    label: str = ""
    kind: FactKind = "unknown"
    unit: str = ""
    concepts: frozenset[str] = frozenset()
    stock: bool = False  # a balance or total at a point in time, not a flow per month

    def sentence(self) -> str:
        """The figure in a code-written sentence, for when the model's claim about it failed."""
        if self.kind == "ratio":
            written = f"{self.value * 100:,.2f} %"
        elif self.kind == "money" and self.unit:
            written = format_money(self.value, self.unit)
        elif self.kind == "count":
            written = f"{self.value:,.0f}"
        elif self.kind == "months":
            written = f"{self.value:,.2f} months"
        else:
            written = f"{self.value:,.2f} {self.unit}".strip()
        return f"{self.label}: {written}."


def fact_for(name: str, value: float, label: str | None = None, unit: str = "", concepts: str | None = None) -> Fact:
    """A fact from a tool field. `name` is the field name; the kind, concepts and stock flag follow from it."""
    name = _NAME_ALIASES.get(name, name)
    kind: FactKind = _kind_from_unit(unit) if unit else "unknown"
    if kind == "unknown":
        kind = next((k for pattern, k in _KIND_BY_NAME if pattern.search(name)), "unknown")
    return Fact(
        float(value),
        label or name.replace("_", " ").capitalize(),
        kind,
        unit,
        _with_broader(concepts_in(concepts if concepts is not None else name)) | _ALSO_ABOUT.get(name, frozenset()),
        _STOCK_NAME.search(name) is not None,
    )


def _kind_from_unit(unit: str) -> FactKind:
    if re.fullmatch(r"[A-Z]{3}", unit):
        return "money"
    return {"months": "months", "ratio": "ratio", "percent": "percent", "count": "count"}.get(unit, "unknown")  # type: ignore[return-value]


def column_fact(column: str, value: float) -> Fact:
    """A number from a query the model wrote. The column name is its own invention, so it proves no meaning."""
    return Fact(float(value), column or "Query result")


def facts_from_fields(value: Any, name: str = "", unit: str = "") -> list[Fact]:
    """Every number in a JSON-like value, labelled by the field it sits in. Dict keys label; lists inherit."""
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [fact_for(name, value, unit=unit)]
    if isinstance(value, dict):
        return [fact for key, item in value.items() for fact in facts_from_fields(item, str(key), unit)]
    if isinstance(value, list | tuple):
        return [fact for item in value for fact in facts_from_fields(item, name, unit)]
    return []


@dataclass(frozen=True)
class ClaimIssue:
    figure: str
    message: str
    fact: Fact | None = None


@dataclass
class VerifierReport:
    ok: bool
    unverified_numbers: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    claim_issues: list[ClaimIssue] = field(default_factory=list)


@dataclass(frozen=True)
class Figure:
    text: str
    value: float
    percent: bool
    rounding: float = 0.0  # half a unit of the last written digit, after scaling ("$1.2M" -> 50,000)
    start: int = 0
    end: int = 0
    currency: bool = False


def _without_dates(text: str) -> str:
    return WRITTEN_DATE_RE.sub(" ", MONTH_RE.sub(" ", text))


def extract_figures(text: str) -> list[Figure]:
    """Financial-looking numbers in `text` (dates, years and small counting integers are skipped).

    `start` and `end` index into `_without_dates(text)`.
    """
    cleaned = _without_dates(text)
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
        figures.append(
            Figure(
                m.group(0).strip(),
                value,
                suffix in ("%", "percent"),
                0.5 * 10**-decimals * scale,
                m.start(),
                m.end(),
                bool(m.group("cur")),
            )
        )
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


def _values(known: Iterable[Fact | float]) -> list[float]:
    return [k.value if isinstance(k, Fact) else float(k) for k in known]


def verify_numbers(text: str, known: Iterable[Fact | float], context: str = "") -> list[str]:
    """Figures in `text` that match neither a tool result nor a number in `context` (the founder's message)."""
    allowed = _values(known) + [f.value for f in extract_figures(context)]
    return [f.text for f in extract_figures(text) if not number_supported(f, allowed)]


# --- does the claim around a figure agree with what the figure is? ------------------------------------------------
_SENTENCE_RE = re.compile(r"(?<=[.!?])(\s+)")


def split_sentences(text: str) -> list[str]:
    """The pieces of `text`, with the whitespace between them kept as pieces, so joining gives `text` back."""
    return _SENTENCE_RE.split(text)


_CLAUSE_RE = re.compile(r",\s|;\s|:\s|\s(?:and|but|while|which|whereas)\s|\s[\u2013\u2014-]\s")
_RUNWAY_BY_AN_AMOUNT = re.compile(r"\brunway\b.*\bby\s+(?:the|that|this|the same)\s+(?:amount|sum|figure)\b", re.I)
_RUNWAY_JUST_BEFORE = re.compile(r"\brunway\W+(?:\w+\W+){0,3}$", re.I)
_MONTHLY_CLAIM = re.compile(r"\bmonthly\b|\bper month\b|\ba month\b|\beach month\b|/\s?mo(?:nth)?\b", re.I)
_COST_WORD = re.compile(r"\bcosts?\b|\bsalary\b|\bpay\b|\bspend\b|\bexpense\b|\badd(?:s|ing)?\b", re.I)
_HIRE_WORD = re.compile(r"\bhir(?:e|es|ing)\b", re.I)
_COST_OF_HIRING = re.compile(r"\b(?:cost|salary|pay)\s+(?:of|for)\s+(?:hiring|a new hire|each hire|one hire)\b", re.I)
_HIRE_ROLE = re.compile(r"\bhir(?:e|ing)\s+((?:[a-z0-9][a-z0-9-]*\s*){1,5})", re.I)
_BEFORE_THE_ROLE = frozenset(
    [
        "a",
        "an",
        "the",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "more",
        "new",
        "another",
        "some",
        "additional",
        "our",
    ]
)
_AFTER_THE_ROLE = frozenset(
    [
        "now",
        "soon",
        "next",
        "this",
        "that",
        "if",
        "when",
        "for",
        "in",
        "at",
        "to",
        "or",
        "and",
        "but",
        "before",
        "after",
        "by",
        "with",
        "on",
        "then",
        "them",
        "someone",
        "anyone",
    ]
)
_WRITTEN_UNIT: list[tuple[re.Pattern[str], FactKind]] = [
    (re.compile(r"\s?-?months?\b", re.I), "months"),
    (re.compile(r"\s?(?:USD|EUR|GBP|INR|dollars?)\b"), "money"),
    (re.compile(r"\s?(?:customers?|people|hires?|employees?|accounts?)\b", re.I), "count"),
]
_UNIT_WORDS: dict[FactKind, str] = {
    "money": "money",
    "months": "months",
    "percent": "a percentage",
    "ratio": "a ratio",
    "count": "a count",
    "unknown": "another unit",
}


def _hire_roles(context: str) -> set[str]:
    """What the founder is hiring: "hire two more SDRs" -> {"sdrs", "sdr"}, "hire the designer now" -> {"designer"}."""
    roles: set[str] = set()
    for match in _HIRE_ROLE.finditer(context):
        words = match.group(1).lower().split()
        while words and (words[0] in _BEFORE_THE_ROLE or words[0].isdigit()):
            words.pop(0)
        for word in words:
            if word in _AFTER_THE_ROLE:
                break
            roles |= {word, word.rstrip("s")}
    return roles


def _written_unit(clause: str, figure: Figure) -> FactKind:
    if figure.currency:
        return "money"
    if figure.percent:
        return "percent"
    after = clause[figure.end :]
    return next((kind for pattern, kind in _WRITTEN_UNIT if pattern.match(after)), "unknown")


def _units_agree(written: FactKind, fact: Fact) -> bool:
    if written == "unknown" or fact.kind == "unknown":
        return True
    if written == "percent":
        return fact.kind in ("percent", "ratio")
    return written == fact.kind


def _names_role(text: str, roles: set[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(role)}\b", lowered) for role in roles)


def _names_a_hire_cost(text: str, roles: set[str]) -> bool:
    return bool(_COST_OF_HIRING.search(text)) or (_names_role(text, roles) and bool(_COST_WORD.search(text)))


def _claimed_concepts(clause: str, sentence: str, written: FactKind, context: str) -> frozenset[str]:
    """What the clause says the figure is. Empty means it names nothing we can check.

    A comma must not break the claim: in "The cost of a designer, based on payroll, is $X" the last clause names
    nothing, and the sentence says what $X is. A clause that names its own quantity is left alone, so one sentence
    can compare several.
    """
    named = set(concepts_in(clause))
    if written == "months" and "cash" in named:  # "cash lasts 10.65 months" is a claim about runway
        named = (named - {"cash"}) | {"runway"}
    roles = _hire_roles(context)
    if _names_a_hire_cost(clause, roles):
        return frozenset({"hire_cost"})  # explicit: a broader word in the clause does not rescue it
    if _COST_WORD.search(clause) and (_HIRE_WORD.search(clause) or (roles and not named)):
        named.add("hire_cost")
    if named or written not in ("money", "unknown"):
        return frozenset(named)
    # The clause names nothing and the founder is deciding a hire, so a sum of money here is read as its cost.
    if (
        _names_a_hire_cost(sentence, roles)
        or (written == "money" and roles and _MONTHLY_CLAIM.search(clause))
        or (written == "money" and (_HIRE_WORD.search(sentence) or _names_role(sentence, roles)))
    ):
        return frozenset({"hire_cost"})
    return frozenset()


def _describe(fact: Fact) -> str:
    return f"{fact.label} ({_UNIT_WORDS[fact.kind]})" if fact.kind != "unknown" else fact.label


def check_sentence(sentence: str, known: Iterable[Fact | float], context: str = "") -> list[ClaimIssue]:
    """The ways this sentence attaches a tool figure to another quantity or unit."""
    facts = [k for k in known if isinstance(k, Fact)]
    issues: list[ClaimIssue] = []
    if _RUNWAY_BY_AN_AMOUNT.search(sentence):
        issues.append(ClaimIssue("", "runway is measured in months, so it cannot change by an amount of money"))
    founder = [f.value for f in extract_figures(context)]
    unlabelled = [k for k in known if isinstance(k, float | int)]
    for clause in _CLAUSE_RE.split(_without_dates(sentence)):
        for figure in extract_figures(clause):
            if number_supported(figure, founder):
                continue  # the founder's own number: they say what it means
            matches = [f for f in facts if number_supported(figure, [f.value])]
            if not matches or any(not f.label for f in matches) or number_supported(figure, unlabelled):
                continue  # no lineage is reported elsewhere; a quoted passage can only be checked by value
            issue = _check_figure(clause, sentence, figure, matches, context)
            if issue is not None:
                issues.append(issue)
    return issues


def _check_figure(clause: str, sentence: str, figure: Figure, matches: list[Fact], context: str) -> ClaimIssue | None:
    written = _written_unit(clause, figure)
    by_unit = [f for f in matches if _units_agree(written, f)]
    if not by_unit:
        return ClaimIssue(
            figure.text, f"{figure.text} is {_describe(matches[0])}, not {_UNIT_WORDS[written]}", matches[0]
        )
    before = _RUNWAY_JUST_BEFORE.search(clause[: figure.start])
    # "runway with cash of $1.8M" is about the cash; "runway is $308,437.67" is not about anything else.
    if written == "money" and before and concepts_in(before.group(0)) == {"runway"}:
        return ClaimIssue(figure.text, f"{figure.text} is {_describe(by_unit[0])}: runway is in months", by_unit[0])
    claimed = _claimed_concepts(clause, sentence, written, context)
    if claimed:
        about_it = [f for f in by_unit if (f.concepts & claimed) or (not f.concepts and "hire_cost" not in claimed)]
        if not about_it:
            wanted = ", ".join(sorted(c.replace("_", " ") for c in claimed))
            return ClaimIssue(figure.text, f"{figure.text} is {_describe(by_unit[0])}, not {wanted}", by_unit[0])
        by_unit = about_it
    if _MONTHLY_CLAIM.search(clause) and all(f.stock for f in by_unit):
        return ClaimIssue(
            figure.text,
            f"{figure.text} is {_describe(by_unit[0])}, a balance or total, not a monthly figure",
            by_unit[0],
        )
    return None


def check_claims(text: str, known: Iterable[Fact | float], context: str = "") -> list[ClaimIssue]:
    known = list(known)
    return [i for s in _SENTENCE_RE.split(text) if s.strip() for i in check_sentence(s, known, context)]


def repair_claims(
    text: str,
    known: Iterable[Fact | float],
    context: str,
    written_by_code: Callable[[list[ClaimIssue]], str],
    used: set[str] | None = None,
) -> tuple[str, list[ClaimIssue]]:
    """Replace each sentence that fails `check_sentence` with a code-written one. Returns (text, what failed).

    `used` holds replacements already written, so a reply checked in pieces does not repeat one.
    """
    used = set() if used is None else used
    known = list(known)
    parts: list[str] = []
    failed: list[ClaimIssue] = []
    for piece in _SENTENCE_RE.split(text):
        issues = check_sentence(piece, known, context) if piece.strip() else []
        if not issues:
            parts.append(piece)
            continue
        failed.extend(issues)
        replacement = written_by_code(issues)
        if replacement not in used:
            used.add(replacement)
            parts.append(replacement)
    return "".join(parts).strip(), failed


def named_paths(text: str, known: set[str]) -> set[str]:
    """Paths the text names. Known paths are matched whole, since a vault path may contain spaces."""
    found = {path for path in known if path in text}
    for path in sorted(found, key=len, reverse=True):
        text = text.replace(path, " ")
    return found | set(PATH_RE.findall(text))


def verify_citations(text: str, citations: list[Citation]) -> list[str]:
    """The answer must name at least one source path, and every path it names must have been returned."""
    issues: list[str] = []
    returned = {c.path for c in citations}
    named = named_paths(text, returned)
    if text.strip() and not named & returned:
        issues.append("the answer cites no vault source")
    for path in sorted(named - returned):
        issues.append(f"{path} was not returned by a search")
    return issues


def verify(
    text: str,
    known_numbers: Iterable[Fact | float],
    citations: list[Citation],
    *,
    needs_citations: bool,
    context: str = "",
) -> VerifierReport:
    known = list(known_numbers)
    unverified = verify_numbers(text, known, context)
    issues = [f"number without lineage: {n}" for n in unverified]
    claims = check_claims(text, known, context)
    issues += [f"wrong meaning: {c.message}" for c in claims]
    if needs_citations:
        issues += verify_citations(text, citations)
    return VerifierReport(ok=not issues, unverified_numbers=unverified, issues=issues, claim_issues=claims)
