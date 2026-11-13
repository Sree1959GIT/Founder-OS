"""What the Advisor says aloud (founder decision 2026-11-13, PRD §12). Code only: no model writes a spoken word here.

- Spoken numbers are rounded and colloquial, made from the verified figure: "around 10 thousand dollars", "about 1.8
  million dollars", "about ten and a half months", "about four in five". Exact figures and lineage stay on screen.
- A team run starts with one or two sentences on who is on the team and each one's focus; each stage gets one short
  line on what its agents produced.
- The answer is never read aloud. The spoken turn is a summary: the outcome, the one thing that matters, then an
  offer of more ("Want me to go through the risks?"), which the founder accepts or declines.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.verifier import split_sentences

_ONES = [
    "zero",
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
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_CURRENCY_WORDS = {"USD": "dollars", "INR": "rupees", "EUR": "euros", "GBP": "pounds", "AED": "dirhams"}
_SYMBOLS = {"$": "USD", "₹": "INR", "€": "EUR", "£": "GBP"}
_INDIAN = {"INR"}
_SCALES = [(1e9, "billion"), (1e6, "million"), (1e3, "thousand")]
_INDIAN_SCALES = [(1e7, "crore"), (1e5, "lakh"), (1e3, "thousand")]
_WRITTEN_SCALES = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "million": 1e6,
    "bn": 1e9,
    "billion": 1e9,
    "lakh": 1e5,
    "lakhs": 1e5,
    "crore": 1e7,
    "crores": 1e7,
}
# Shares that read better as a fraction, said only of a share "of" something (never of a price change or a rate).
_SHARES = [
    (10, "one in ten"),
    (20, "one in five"),
    (25, "a quarter"),
    (33.3, "a third"),
    (40, "two in five"),
    (50, "half"),
    (60, "three in five"),
    (66.7, "two thirds"),
    (75, "three quarters"),
    (80, "four in five"),
    (90, "nine in ten"),
]


def words(n: int) -> str:
    """0 to 99 in words; anything else as digits."""
    if 0 <= n < 20:
        return _ONES[n]
    if 20 <= n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens - 2] + (f"-{_ONES[ones]}" if ones else "")
    return str(n)


def _trim(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _rounded(value: float, indian: bool = False) -> tuple[str, bool]:
    """A size in words ("1.8 million", "10 thousand", "12.5 lakh") and whether that is the exact value."""
    v = abs(value)
    for size, name in _INDIAN_SCALES if indian else _SCALES:
        if v >= size * 0.95:
            n = v / size
            # "12.5 lakh" keeps its half: a lakh is a large step. "172 thousand" is said as "170 thousand".
            whole_from = 100 if indian else 10
            shown = round(n, -1) if n >= 100 else round(n) if n >= whole_from else round(n, 1)
            return f"{_trim(shown)} {name}", abs(shown * size - v) <= 0.0005 * v
    shown = round(v, -1) if v >= 100 else round(v) if v >= 10 else round(v, 1)
    return _trim(shown), abs(shown - v) <= 0.0005 * max(v, 1.0)


def _about(text: str, exact: bool, word: str = "about") -> str:
    return text if exact else f"{word} {text}"


def say_money(value: float, currency: str = "USD") -> str:
    """ "around 10 thousand dollars", "about 1.8 million dollars", "about 12.5 lakh rupees"."""
    unit = _CURRENCY_WORDS.get(currency.upper(), currency.upper())
    if abs(value) < 0.005:
        return f"zero {unit}"
    size, exact = _rounded(value, indian=currency.upper() in _INDIAN)
    small = not re.search(r"million|billion|crore", size)
    sign = "minus " if value < 0 else ""
    return f"{sign}{_about(size, exact, 'around' if small else 'about')} {unit}"


def say_percent(value: float, share: bool = False) -> str:
    """ "about 72 percent"; of a share, "about four in five"."""
    v = abs(value)
    sign = "minus " if value < 0 else ""
    if share:
        near, phrase = min(_SHARES, key=lambda s: abs(s[0] - v))
        if abs(near - v) <= 2.5:
            return sign + _about(phrase, abs(near - v) < 0.4)
    shown = round(v) if v >= 10 else round(v, 1)
    return f"{sign}{_about(_trim(shown), abs(shown - v) < 0.005)} percent"


def say_months(value: float) -> str:
    """ "about ten and a half months", "about a week", "two months"."""
    v = abs(value)
    if v < 0.15:
        return "a few days"
    if v < 0.875:
        return "about a week" if v < 0.4 else "about two weeks" if v < 0.6 else "about three weeks"
    half_steps = round(v * 2)
    whole, half = divmod(half_steps, 2)
    exact = abs(half_steps / 2 - v) < 0.02
    if whole > 36:
        return _about(f"{round(v)} months", abs(round(v) - v) < 0.02)
    if half:
        return _about(f"{words(whole)} and a half months", exact)
    return _about("a month" if whole == 1 else f"{words(whole)} months", exact)


def _ordinal(day: int) -> str:
    suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def say_date(iso: str) -> str:
    """ "2027-09" as "September 2027"; "2026-12-08" as "the 8th of December 2026". Anything else unchanged."""
    match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?", iso.strip())
    if match is None:
        return iso
    year, month, day = match.group(1), calendar.month_name[int(match.group(2))], match.group(3)
    return f"the {_ordinal(int(day))} of {month} {year}" if day else f"{month} {year}"


_NUM = r"\d[\d,]*(?:\.\d+)?"
_MONEY = re.compile(
    rf"(?P<sign>[-+]?)(?P<sym>[$₹€£])\s?(?P<num>{_NUM})"
    r"(?:\s?(?P<scale>k|mn|m|bn|thousand|million|billion|lakhs?|crores?)\b)?"
)
_MONEY_CODE = re.compile(rf"(?P<sign>[-+]?)(?P<num>{_NUM})\s(?P<code>USD|INR|EUR|GBP|AED)\b")
_PERCENT = re.compile(r"(?P<sign>[-+]?)(?P<num>\d+(?:\.\d+)?)\s?(?:%|percent\b)(?P<of>\s+of\b)?")
_MONTH_RANGE = re.compile(r"(?P<a>\d+(?:\.\d+)?)\s+to\s+(?P<b>\d+(?:\.\d+)?)\s+months\b")
_MONTHS = re.compile(r"(?P<sign>[-+]?)(?P<num>\d+(?:\.\d+)?)[\s-]+months?\b")
_ISO_DATE = re.compile(r"\b\d{4}-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?\b")
_BIG_NUMBER = re.compile(r"(?<![\w.])(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)(?![\w%])")
_SIGNED_ASIDE = re.compile(r"\s*\((?:[-+]\d[\d.,]*|removed:[^)]*)\)")
_YEAR = re.compile(r"(?:19|20)\d{2}")


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def spoken_text(text: str, currency: str = "USD") -> str:
    """Any sentence with its figures said the spoken way. Words are untouched; only the numbers change."""

    def money(m: re.Match[str]) -> str:
        value = _number(m["num"]) * _WRITTEN_SCALES.get((m["scale"] or "").lower(), 1.0)
        said = say_money(value, _SYMBOLS.get(m["sym"], currency))
        return f"minus {said}" if m["sign"] == "-" else said

    def money_code(m: re.Match[str]) -> str:
        said = say_money(_number(m["num"]), m["code"])
        return f"minus {said}" if m["sign"] == "-" else said

    def percent(m: re.Match[str]) -> str:
        said = say_percent(float(m["num"]), share=bool(m["of"]))
        sign = "minus " if m["sign"] == "-" else ""
        return f"{sign}{said}{' of' if m['of'] else ''}"

    def months(m: re.Match[str]) -> str:
        said = say_months(float(m["num"]))
        return f"down {said}" if m["sign"] == "-" else f"up {said}" if m["sign"] == "+" else said

    def big(m: re.Match[str]) -> str:
        if "," not in m["num"] and _YEAR.fullmatch(m["num"]):
            return m["num"]  # a year is said as it is
        size, exact = _rounded(_number(m["num"]), indian=currency.upper() in _INDIAN)
        return _about(re.sub(r"^1 (?=[a-z])", "a ", size), exact)

    out = _SIGNED_ASIDE.sub("", text.replace(chr(0x2212), "-"))  # a typeset minus sign reads as a hyphen
    out = re.sub(r"\[[^\]]*\]", "", out)
    out = _MONEY.sub(money, out)
    out = _MONEY_CODE.sub(money_code, out)
    out = _PERCENT.sub(percent, out)
    out = _MONTH_RANGE.sub(lambda m: f"{say_months(float(m['a']))} to {say_months(float(m['b']))}", out)
    out = _MONTHS.sub(months, out)
    out = _ISO_DATE.sub(lambda m: say_date(m.group(0)), out)
    out = _BIG_NUMBER.sub(big, out)
    out = re.sub(r"\babout (about|around)\b", r"\1", out)
    return re.sub(r"\s{2,}", " ", out).replace(" ,", ",").replace(" .", ".").strip()


# --- the team, at the start and stage by stage -----------------------------------------------------------------------
_FOCUS = {
    "financial_analyst": "on the numbers",
    "librarian": "on your notes and past decisions",
    "market_scout": "on the market",
    "revenue_customer": "on revenue and customers",
    "people_ops": "on people and operations",
    "regulatory_tax": "on regulation and tax",
    "prioritiser": "on priorities",
    "perspective_lens": "for another point of view",
    "devils_advocate": "on what could go wrong",
    "memo_writer": "to write it up",
}
_PRODUCED = {
    "financial_analyst": "has priced it",
    "librarian": "has checked your notes",
    "market_scout": "has looked at the market",
    "revenue_customer": "has looked at revenue and customers",
    "people_ops": "has looked at people and operations",
    "regulatory_tax": "has flagged the regulatory points",
    "prioritiser": "has ranked the options",
    "perspective_lens": "has given another view",
    "devils_advocate": "has listed the risks",
    "memo_writer": "has drafted the memo",
}


def _joined(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


_SAID_AS = {
    "Regulatory & Tax": "Regulatory and Tax adviser",
    "People & Ops": "People and Ops adviser",
    "Revenue & Customer": "Revenue and Customer analyst",
}


def _the(name: str) -> str:
    for written, said in _SAID_AS.items():
        name = name.replace(written, said)
    return f"the {name.replace('&', 'and')}"


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def team_line(team: list[dict[str, Any]]) -> str:
    """Who is on the team and each one's focus, in one or two sentences. Nothing for a one-agent lookup."""
    members = [f"{_the(str(m.get('name', 'an agent')))} {_FOCUS.get(str(m.get('type')), 'on it')}" for m in team]
    if len(members) < 2:
        return ""
    count = words(len(members)).capitalize()
    if len(members) <= 4:
        return f"{count} on this: {_joined(members)}."
    return f"{count} on this: {_joined(members[:3])}. Then {_joined(members[3:])}."


def produced_line(wave: list[dict[str, Any]]) -> str:
    """One short line on what the agents of a stage produced. No figures and no content: the screen has those."""
    done = [m for m in wave if m.get("status", "done") == "done"]
    parts = [f"{_the(str(m.get('name')))} {_PRODUCED.get(str(m.get('type')), 'is done')}" for m in done]
    stopped = [_the(str(m.get("name"))) for m in wave if m.get("status", "done") != "done"]
    line = ""
    if parts:
        line = f"{_capital(_joined(parts))}."
    if stopped:
        line += f" {_capital(_joined(stopped))} did not finish."
    if any(not m.get("verified", True) for m in done):
        line += " Part of that is unverified."
    return line.strip()


# --- the answer, as a short spoken summary ---------------------------------------------------------------------------
@dataclass
class Segment:
    """More, on offer: the question that offers it, and the two or three sentences said if the founder accepts."""

    key: str  # risks | options | detail | rest
    offer: str
    lines: list[str]


@dataclass
class Spoken:
    lead: list[str]
    more: list[Segment] = field(default_factory=list)


def _label_words(label: str) -> tuple[str, str]:
    """ "Net burn (monthly)" as ("net burn", " a month"); an acronym keeps its capitals."""
    suffix = " a month" if re.search(r"\(monthly\)", label, re.I) else ""
    name = re.sub(r"\s*\([^)]*\)", "", label).strip()
    first = name.split(" ", 1)[0] if name else ""
    if first and not (first.isupper() or "/" in first):
        name = name[0].lower() + name[1:]
    return name, suffix


def metric_lead(label: str, value: float | None, unit: str, metric: str = "") -> str:
    """The outcome of a one-metric question, from the routine's own figure."""
    name, suffix = _label_words(label)
    if value is None:
        return f"I can't work out your {name} from the data."
    if re.fullmatch(r"[A-Z]{3}", unit):
        said = say_money(float(value), unit)
    elif unit == "months":
        said = say_months(float(value))
    elif unit == "ratio":
        said = f"about {_trim(float(value))} to one" if metric == "ltv_cac" else say_percent(float(value) * 100)
    elif unit == "percent":
        said = say_percent(float(value))
    elif unit == "count":
        said = _rounded(float(value))[0]
    elif unit == "date":
        said = say_date(str(value))
    else:
        said = f"{value} {unit}".strip()
    return f"Your {name} is {said}{suffix}."


def cash_risk_line(probability: float) -> str:
    return (
        f"One warning: in {say_percent(probability * 100, share=True)} of the simulated futures, cash runs out "
        "within a year."
    )


def _cost_words(option: Any, currency: str) -> str:
    if not getattr(option, "modelled", True):
        return "its cost is not modelled"
    one_off, monthly = float(option.one_off or 0), float(option.monthly or 0)
    if one_off and monthly:
        return f"{say_money(one_off, currency)} up front and {say_money(monthly, currency)} a month"
    if monthly:
        return f"{say_money(monthly, currency)} a month"
    return f"{say_money(one_off, currency)} up front" if one_off else "no new cost"


def _runway_words(change: float | None) -> str:
    if change is None:
        return ""
    if abs(change) < 0.02:
        return ", with no real change to your runway"
    if change < 0:
        return f", which shortens your runway by {say_months(change)}"
    return f", which adds {say_months(change)} to your runway"


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in split_sentences(text) if p.strip()]


def _chunks(lines: list[str], size: int = 3, limit: int = 2) -> list[list[str]]:
    return [lines[i : i + size] for i in range(0, len(lines), size)][:limit]


def summarise(result: Any) -> Spoken:
    """The spoken turn for a finished run: the outcome and the one thing that matters, then offers of more.

    `result` is a `ChatResult`. Figures come from its metrics, decision frame and cash-risk check (all code), said
    through the normaliser. Only an answer with neither a metric nor a frame is taken from the checked text, and then
    only its first two sentences.
    """
    answer = str(getattr(result, "answer", "") or "")
    if getattr(result, "status", "done") != "done":
        return Spoken(lead=_sentences(answer)[:2])
    frame = getattr(result, "decision_frame", None)
    metrics = list(getattr(result, "metrics", []) or [])
    risk = getattr(result, "cash_risk", None)
    state = getattr(getattr(result, "verification", None), "state", "verified")
    currency = getattr(frame, "currency", None) or "USD"
    sentences = _sentences(answer)
    lead: list[str] = []
    more: list[Segment] = []
    if frame is not None and frame.options:
        proposed = next((o for o in frame.options if o.name == frame.default_option), frame.options[0])
        lead.append(
            f"My proposal is {proposed.name}: {_cost_words(proposed, currency)}"
            f"{_runway_words(proposed.runway_change_months if proposed.modelled else None)}."
        )
        away = next((g.goal for g in frame.goals if g.status == "moves_away"), "")
        if risk is not None:
            lead.append(cash_risk_line(risk.probability))
        elif away:
            lead.append(f"The thing to weigh: it moves you away from your goal, {spoken_text(away, currency)}.")
        if state == "not_verified":
            lead.append("Part of this is unverified, so check the screen.")
        elif getattr(result, "assumptions_to_confirm", 0):
            lead.append("The costs are assumptions for you to confirm.")
        advocate = next(
            (a for a in getattr(result, "agents", []) if a.type == "devils_advocate" and a.status == "done"), None
        )
        risks = [spoken_text(s, currency) for s in _sentences(advocate.text)][:3] if advocate is not None else []
        if risks:
            more.append(Segment("risks", "Want me to go through the risks?", risks))
        others = [o for o in frame.options if o.name != proposed.name][:4]
        if others:
            listed = "; ".join(f"{o.name}, {_cost_words(o, currency)}" for o in others)
            more.append(Segment("options", "Want the other options?", [f"The other options: {listed}."]))
    elif metrics and getattr(result, "intent", "") == "finance":
        first = metrics[0]
        lead.append(metric_lead(first.label, first.value, first.unit, first.metric))
        if risk is not None:
            lead.append(cash_risk_line(risk.probability))
        if state == "not_verified":
            lead.append("Part of this is unverified, so check the screen.")
        detail = [spoken_text(s, currency) for s in sentences if "simulated futures" not in s][:3]
        if detail:
            more.append(Segment("detail", "Want the detail?", detail))
    else:
        said = [spoken_text(s, currency) for s in sentences]
        lead.extend(said[:2])
        if state == "not_verified" and lead:
            lead.append("Part of this is unverified, so check the screen.")
        for chunk in _chunks(said[2:]):
            more.append(Segment("rest", "Want me to go on?", chunk))
    return Spoken(lead=lead[:3], more=more)
