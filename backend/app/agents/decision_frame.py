"""The frame of a decision, built by code before any agent argues about it.

What kind of decision is this? What does it really cost? What are the alternatives? Does it move toward or away from
the company's goals? Seen live: left to the model, a Dubai office was costed as "1 hire", a goal was reported as a
decision, and the options contradicted each other. So all of this is code, for every decision type:

- **Type**: rules on the founder's words, then the Planner's label (`classify_decision`).
- **Cost model**: one-off and monthly components. What the data does not hold is a starting placeholder labelled
  "assumption, confirm", never a verified figure, and the founder's own numbers replace it (`parse_inputs`). Low, base
  and high runway effects come from `run_scenario`, so no model does the arithmetic.
- **Options**: realistic alternatives for this type, each with its own cost and runway effect.
- **Goal check**: every goal in `profile/company.md`, compared with this decision.
- **Starter outcomes**: a measurable prediction and kill criteria, derived from the cost model.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field, model_validator

from app.agents.verifier import Fact, extract_figures, format_money, split_sentences
from app.engine.scenario import Adjustments

DecisionType = Literal["hire", "new_office", "pricing", "spend", "fundraise", "new_product", "other"]
ASSUMPTION_LABEL = "assumption, confirm"
COMPANY_NOTE = "profile/company.md"
COSTS_ONLY = "Costs only: no new revenue from this decision is assumed."

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}

# First cue in the founder's words wins: "open a Dubai office and hire two" is an office, "hire two to launch it" is
# a hire.
_TYPE_CUES: list[tuple[DecisionType, re.Pattern[str]]] = [
    (
        "fundraise",
        re.compile(
            r"\b(fund-?rais\w*|raise (a |an |our |some |more |new )?(\w+ )?(round|seed|series|money|funds|funding|"
            r"capital|equity)|venture debt|bridge (round|loan)|safe note|term sheet)\b",
            re.I,
        ),
    ),
    (
        "pricing",
        re.compile(
            r"\b(prices?|pricing|discounts?|(raise|increase|cut|lower|reduce) (our |the )?(prices?|fees|rates))\b",
            re.I,
        ),
    ),
    (
        "new_office",
        re.compile(
            r"\b(open\w*|set\w*[- ]up|start\w*|establish\w*|launch\w*|expand\w*|enter\w*)\b[^.?!]{0,50}?"
            r"\b(office|branch|region|entity|subsidiary|hub|market|country)\b|"
            r"\b(new|second) (sales )?(office|region|branch)\b|"
            r"\bexpand\w* (in)?to\b"
            r"(?![^.?!]*\b(product\w*|pric\w*|tiers?|customers?|segments?|enterprise|features?)\b)",
            re.I,
        ),
    ),
    (
        "new_product",
        re.compile(
            r"\b(new|second|another) product\b|\bproduct line\b|"
            r"\b(launch\w*|build\w*)\b[^.?!]{0,40}?\b(product|add-?on|module)\b",
            re.I,
        ),
    ),
    ("hire", re.compile(r"\b(hir(e|es|ing)|recruit\w*|headcount|contractors?|layoffs?)\b", re.I)),
    (
        "spend",
        re.compile(
            r"\b(spend\w*|budget\w*|invest\w*|marketing|advertis\w*|ad campaign|campaigns?|buy|purchase|sponsor\w*|"
            r"cut (our )?(costs?|burn)|software|vendor|tool)\b",
            re.I,
        ),
    ),
]
_PLANNER_LABELS: list[tuple[DecisionType, re.Pattern[str]]] = [
    ("hire", re.compile(r"hir|headcount|people|staff", re.I)),
    ("new_office", re.compile(r"expan|office|region|market entry|geograph", re.I)),
    ("pricing", re.compile(r"pric|discount", re.I)),
    ("fundraise", re.compile(r"fund|financ|investment round", re.I)),
    ("new_product", re.compile(r"product", re.I)),
    ("spend", re.compile(r"spend|cost|budget|marketing", re.I)),
]
TYPE_NAMES: dict[str, str] = {
    "hire": "hiring decision",
    "new_office": "new office or region",
    "pricing": "pricing change",
    "spend": "spending change",
    "fundraise": "fundraise",
    "new_product": "new product line",
    "other": "other decision",
}


def classify_decision(message: str, planner_label: str | None = None) -> DecisionType:
    first = re.split(r"\n", message.strip(), maxsplit=1)[0]
    found = [(m.start(), kind) for kind, cue in _TYPE_CUES if (m := cue.search(first))]
    if found:
        return min(found, key=lambda item: item[0])[1]
    for kind, label in _PLANNER_LABELS:
        if planner_label and label.search(planner_label):
            return kind
    return "other"


_OFFICE_PLACE = re.compile(
    r"\b(?:open\w*|set\w*[- ]up|start\w*|establish\w*|launch\w*)\s+(?:an?|our|the|a new)?\s*"
    r"([A-Z][\w-]+(?: [A-Z][\w-]+)?)\s+(?:office|branch|entity|subsidiary|hub)\b"
    r"|\b(?:office|branch|entity|hub) in ([A-Z][\w-]+(?: [A-Z][\w-]+)?)"
    r"|\b(?:expand\w*|enter\w*)\s+(?:into |to )?(?:the )?([A-Z][\w-]+(?: [A-Z][\w-]+)?)"
)


def _place(message: str) -> str:
    match = _OFFICE_PLACE.search(message)
    return next((g for g in match.groups() if g), "") if match else ""


# --- the cost components ---------------------------------------------------------------------------------------------
Cadence = Literal["one_off", "monthly", "count", "percent", "points"]
_UNITS = {"count": "people", "percent": "%", "points": "pts"}  # money items take the model's currency


@dataclass(frozen=True)
class ItemTemplate:
    """A cost component. `low`, `base` and `high` are starting placeholders, not market data: the founder confirms."""

    key: str
    name: str
    cadence: Cadence
    low: float
    base: float
    high: float
    keywords: str = ""
    question: str = ""


_COUNT = r"(\d{1,3}|one|two|three|four|five|six|seven|eight|nine)"
_TEMPLATES: dict[str, list[ItemTemplate]] = {
    "new_office": [
        ItemTemplate(
            "setup",
            "Setup and licences",
            "one_off",
            15000,
            30000,
            60000,
            r"set-?up|licen[cs]e|licen[cs]es|incorporation|registration|fit-?out",
            "what setup and licences would cost",
        ),
        ItemTemplate(
            "rent",
            "Rent or desk",
            "monthly",
            2000,
            5000,
            12000,
            r"rent|desk|lease|office space",
            "the monthly rent or desk",
        ),
        ItemTemplate(
            "hires",
            "Local hires",
            "count",
            1,
            2,
            3,
            r"(?:local )?(?:hires?|people|persons?|reps?|staff|team)",
            "how many local hires",
        ),
        ItemTemplate("travel", "Travel", "monthly", 1000, 3000, 6000, r"travel"),
        ItemTemplate("compliance", "Compliance and accounting", "monthly", 500, 1500, 3000, r"complian\w*|accounting"),
    ],
    "pricing": [
        ItemTemplate(
            "price",
            "Price change",
            "percent",
            10,
            10,
            10,
            r"prices?|pricing|discounts?|rates?|fees?",
            "the size of the price change",
        ),
        ItemTemplate(
            "churn",
            "Extra monthly churn it causes",
            "points",
            0.2,
            0.5,
            1.0,
            r"churn",
            "how much extra monthly churn you expect",
        ),
        ItemTemplate(
            "notice",
            "Customer notice and billing changes",
            "one_off",
            2000,
            5000,
            10000,
            r"notice|billing|migration",
        ),
    ],
    "new_product": [
        ItemTemplate(
            "build",
            "Build and launch",
            "one_off",
            40000,
            80000,
            160000,
            r"build|launch|development",
            "what building and launching it would cost",
        ),
        ItemTemplate(
            "hires",
            "Dedicated team",
            "count",
            1,
            2,
            4,
            r"(?:team of |dedicated )?(?:hires?|people|engineers?|staff)",
            "how many people it needs",
        ),
        ItemTemplate(
            "gtm",
            "Go-to-market",
            "monthly",
            1000,
            3000,
            8000,
            r"marketing|go-?to-?market|gtm",
            "the monthly go-to-market budget",
        ),
        ItemTemplate("hosting", "Hosting and support", "monthly", 500, 1500, 4000, r"hosting|support|infrastructure"),
    ],
    "spend": [
        ItemTemplate(
            "amount",
            "Added monthly spend",
            "monthly",
            5000,
            10000,
            20000,
            r"spend\w*|budget|marketing|campaigns?|invest\w*|a month|monthly|per month",
            "the monthly amount",
        ),
        ItemTemplate(
            "once", "One-off cost", "one_off", 0, 0, 0, r"one-?off|one time|once|up ?front", "any one-off cost"
        ),
    ],
    "fundraise": [
        ItemTemplate(
            "fees",
            "Legal and adviser fees",
            "one_off",
            15000,
            30000,
            60000,
            r"legal|fees?|advis\w*",
            "the legal and adviser fees",
        ),
        ItemTemplate(
            "round", "Cash raised", "one_off", 0, 0, 0, r"round|raise|raising|seed|series|bridge", "the round size"
        ),
    ],
}

_MONEY = re.compile(
    r"(?P<sym>[$€£₹])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?(?P<scale>k\b|m\b|thousand\b|million\b)?",
    re.I,
)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}
_CLAUSE = re.compile(r"[;\n]|,\s(?!\d{3})|\.\s|\s(?:and|plus)\s")


def _amount(match: re.Match[str]) -> float:
    return float(match.group("num").replace(",", "")) * _SCALE.get((match.group("scale") or "").lower(), 1.0)


def _value_in_clause(item: ItemTemplate, clause: str) -> float | None:
    if not re.search(rf"\b(?:{item.keywords})\b", clause, re.I):
        return None
    if item.cadence == "count":
        # "a two-person team" and "a two person team" are a count of two
        match = re.search(rf"\b{_COUNT}[\s-]+(?:\w+ )?(?:{item.keywords})\b", clause, re.I)
        if match is None:
            return None
        word = match.group(1).lower()
        return float(word) if word.isdigit() else float(_NUMBER_WORDS[word])
    if item.cadence in ("percent", "points"):
        match = re.search(r"(-?\d+(?:\.\d+)?)\s?(?:%|percent|points?|pts?\b)", clause, re.I)
        return float(match.group(1)) if match else None
    money = [
        m for m in _MONEY.finditer(clause) if not re.match(r"\s?(%|months?|people|hires?)", clause[m.end() :], re.I)
    ]
    return _amount(money[-1]) if money else None


def units_of(decision_type: str) -> tuple[bool, bool]:
    """Whether this kind of decision counts people, and whether it has a percentage of its own: how a bare number or
    a stray "%" in the founder's change is to be read (founder re-test R3)."""
    items = _TEMPLATES.get(decision_type, [])
    counts = decision_type == "hire" or any(i.cadence == "count" for i in items)
    return counts, any(i.cadence in ("percent", "points") for i in items)


def parse_inputs(text: str, decision_type: str) -> dict[str, float]:
    """The founder's own numbers for this decision's components. A later statement replaces an earlier one."""
    found: dict[str, float] = {}
    items = _TEMPLATES.get(decision_type, [])
    for clause in _CLAUSE.split(text):
        for item in items:
            value = _value_in_clause(item, clause)
            if value is not None:
                found[item.key] = value
                break
    return found


# --- the model of the costs ------------------------------------------------------------------------------------------
class CostItem(BaseModel):
    key: str
    name: str
    cadence: Cadence
    low: float
    base: float
    high: float
    basis: Literal["assumption", "founder", "data"] = "assumption"
    unit: str = Field(
        "", description="What low, base and high are in: a currency code, '%', 'pts', 'people' or 'months'"
    )

    @model_validator(mode="after")
    def _own_unit(self) -> CostItem:
        """Every row says what its numbers are (founder re-test 44: a 10 % price change showed as "$10")."""
        if not self.unit:
            self.unit = _UNITS.get(self.cadence, "")
        return self

    @property
    def varies(self) -> bool:
        return not self.low == self.base == self.high


class CostCase(BaseModel):
    name: Literal["low", "base", "high"]
    one_off: float
    monthly: float
    base_runway_months: float | None = None
    scenario_runway_months: float | None = None
    runway_change_months: float | None = None
    mrr_in_3_months: float | None = None


class CostModel(BaseModel):
    subject: str
    items: list[CostItem]
    cases: list[CostCase]
    cost_per_person_monthly: float | None = None
    currency: str = "USD"
    as_of: str = ""
    growth_mode: str = "trend"
    formula: str = "run_scenario: spend_change_monthly + new_hires x average loaded cost, plus one_off_cost once"
    sources: list[str] = Field(default_factory=list)
    scope_note: str = COSTS_ONLY

    def case(self, name: str) -> CostCase:
        return next(c for c in self.cases if c.name == name)

    @property
    def assumption_count(self) -> int:
        return sum(i.basis == "assumption" for i in self.items)

    @model_validator(mode="after")
    def _money_units(self) -> CostModel:
        for item in self.items:
            if not item.unit:
                item.unit = self.currency
        return self

    def money(self, value: float) -> str:
        return format_money(value, self.currency)

    def item_line(self, item: CostItem) -> str:
        label = "you said" if item.basis == "founder" else ASSUMPTION_LABEL
        if item.cadence == "count":
            span = f"{item.base:.0f}" if not item.varies else f"{item.base:.0f} ({item.low:.0f} to {item.high:.0f})"
            each = self.money(self.cost_per_person_monthly) if self.cost_per_person_monthly is not None else "unknown"
            return (
                f"{item.name}: {span} people ({label}), each at your average loaded cost of {each} a month, "
                "from your payroll data, not a quote for these roles."
            )
        if item.cadence == "percent":
            return f"{item.name}: {item.base:+g} % ({label})."
        if item.cadence == "points":
            span = f"{item.base:+g}" if not item.varies else f"{item.base:+g} ({item.low:+g} to {item.high:+g})"
            return f"{item.name}: {span} percentage points ({label})."
        cadence = "one-off" if item.cadence == "one_off" else "a month"
        span = self.money(item.base)
        if item.varies:
            span += f" ({self.money(item.low)} to {self.money(item.high)})"
        return f"{item.name}: {span} {cadence} ({label})."

    def _cost_words(self, case: CostCase) -> str:
        """Cash coming in (a raise) is not a cost paid "up front"."""
        if case.one_off < 0:
            return f"net cash in of {self.money(-case.one_off)} and {self.money(case.monthly)} a month"
        return f"{self.money(case.one_off)} up front and {self.money(case.monthly)} a month"

    def case_line(self, case: CostCase) -> str:
        cost = self._cost_words(case)
        if case.scenario_runway_months is None or case.base_runway_months is None:
            return f"{case.name.capitalize()} case: {cost}; projected runway does not run out in the model."
        return (
            f"{case.name.capitalize()} case: {cost}; projected runway {case.base_runway_months:.2f} to "
            f"{case.scenario_runway_months:.2f} months ({case.runway_change_months or 0:+.2f} months)."
        )

    def sentence(self) -> str:
        """The model in one sentence, in words a founder can act on. Written by code."""
        base = self.case("base")
        label = ASSUMPTION_LABEL if self.assumption_count else "your figures"
        lead = f"{self.subject} is modelled at {self._cost_words(base)} ({label})"
        if base.scenario_runway_months is None or base.base_runway_months is None:
            return f"{lead}. {self.scope_note}".strip()
        low, high = self.case("low"), self.case("high")
        span = ""
        if low.runway_change_months != high.runway_change_months:
            span = (
                f"; from {low.runway_change_months or 0:+.2f} months in the low case "
                f"to {high.runway_change_months or 0:+.2f} in the high case"
            )
        change = f"{base.runway_change_months or 0:+.2f} months"
        return (
            f"{lead}, moving projected runway from {base.base_runway_months:.2f} to "
            f"{base.scenario_runway_months:.2f} months ({change}){span}. {self.scope_note}"
        ).strip()


class OptionCost(BaseModel):
    name: str
    note: str = ""
    one_off: float = 0.0
    monthly: float = 0.0
    runway_change_months: float | None = None
    modelled: bool = Field(True, description="False: the scenario routine cannot express this option")
    is_full: bool = Field(False, description="The option the cost model describes")
    trade_off: str = Field("", description="Why it may lose even when it costs less: control, speed, what it teaches")
    basis: str = ASSUMPTION_LABEL

    def line(self, currency: str) -> str:
        if not self.modelled and not self.one_off and not self.monthly:
            return f"{self.name}: cost not modelled. {self.note}".strip()
        cost = f"{format_money(self.one_off, currency)} up front, {format_money(self.monthly, currency)} a month"
        if not self.modelled:
            effect = "runway effect not modelled"
        elif self.runway_change_months is None:
            effect = "runway does not run out in the model"
        else:
            effect = f"runway {self.runway_change_months:+.2f} months"
        label = f" ({self.basis})" if self.basis and (self.one_off or self.monthly) else ""
        return f"{self.name}: {cost}, {effect}{label}. {self.note}".strip()


GoalStatus = Literal["moves_away", "moves_towards", "open_question", "not_affected", "not_checked"]


class GoalCheck(BaseModel):
    goal: str
    status: GoalStatus
    sentence: str


class BaselineFigure(BaseModel):
    metric: str
    label: str
    value: float
    unit: str
    as_of: str
    sources: list[str] = Field(default_factory=list)

    def sentence(self) -> str:
        return f"{self.label} is {written_value(self.value, self.unit)} as of {self.as_of}."

    def line(self) -> str:
        files = ", ".join(self.sources)
        return f"{self.sentence()} (From your data{': ' + files if files else ''}, computed by a routine.)"


class Outcome(BaseModel):
    """A forecast or a stop rule: a metric, a threshold and a date. Code writes these when the model's are not."""

    metric: str
    threshold: str
    by: str
    probability: float = 0.5

    def statement(self) -> str:
        return f"{self.metric} {self.threshold} by {self.by}"


class DecisionFrame(BaseModel):
    type: DecisionType = "other"
    subject: str = "This decision"
    message: str = ""
    cost_model: CostModel | None = None
    options: list[OptionCost] = Field(default_factory=list)
    default_option: str = ""
    goals: list[GoalCheck] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    baseline: list[BaselineFigure] = Field(default_factory=list)
    hires: int | None = None
    predictions: list[Outcome] = Field(default_factory=list)
    kill_criteria: list[Outcome] = Field(default_factory=list)
    currency: str = "USD"
    as_of: str = ""
    facts: list[Fact] = Field(default_factory=list, exclude=True)

    @property
    def non_hire(self) -> bool:
        return self.type != "hire"

    @property
    def assumption_count(self) -> int:
        return self.cost_model.assumption_count if self.cost_model else 0

    def cost_sentence(self) -> str:
        if self.cost_model is not None:
            return self.cost_model.sentence()
        if self.type == "hire":
            return ""
        return "The cost of this is not modelled yet: tell me what it costs up front and each month."

    def goal_sentences(self) -> list[str]:
        """What the founder must hear plainly: moving away from a goal, or a goal that is still an open question."""
        order = {"moves_away": 0, "open_question": 1}
        wanted = [g for g in self.goals if g.status in order]
        return [g.sentence for g in sorted(wanted, key=lambda g: order[g.status])]

    def for_agents(self) -> str:
        """A short block for an agent's instructions. It must fit an 8k context."""
        lines = [f"\n\nDecision type: {TYPE_NAMES[self.type]}."]
        if self.cost_model is not None and self.non_hire:
            lines.append(
                f"Cost model, computed in code: {self.cost_model.sentence()} Labelled assumptions are placeholders the "
                "founder must confirm: always call them assumptions. This is not one hire: never give a one-hire cost "
                "as the cost of this decision."
            )
        if self.options:
            names = ", ".join(o.name for o in self.options)
            lines.append(
                f"The options being compared: {names}. The easiest to undo is {self.default_option}. Speak to these "
                "options, not only the largest one, and never advise against what an option depends on."
            )
        if self.goals:
            lines.append(
                "Company goals, from profile/company.md. These are goals and open questions, NOT decisions: "
                + " ".join(f'"{g.goal}"' for g in self.goals)
            )
        return "\n".join(lines)

    def findings_block(self) -> list[str]:
        lines = [f"Decision type: {TYPE_NAMES[self.type]}."]
        if self.cost_model is not None and self.non_hire:
            lines.append("Cost of this decision, computed in code (state this; no other figure is its cost):")
            lines.append(f"- {self.cost_model.sentence()}")
        sentences = self.goal_sentences()
        if sentences:
            lines.append("Goal check, computed in code (say this plainly):")
            lines.extend(f"- {s}" for s in sentences)
        return lines


def written_value(value: float, unit: str) -> str:
    if unit == "months":
        return f"{value:.2f} months"
    if unit == "ratio":
        return f"{value * 100:.2f} %"
    if unit == "percent":
        return f"{value:.2f} %"
    if re.fullmatch(r"[A-Z]{3}", unit):
        return format_money(value, unit)
    return f"{value:g} {unit}".strip()


# --- building it -----------------------------------------------------------------------------------------------------
def _in_months(today: dt.date, months: int) -> str:
    """The same day `months` later, or the month's last day if that month is shorter."""
    index = today.month - 1 + months
    year, month = today.year + index // 12, index % 12 + 1
    for day in range(today.day, 27, -1):
        try:
            return dt.date(year, month, day).isoformat()
        except ValueError:
            continue
    return dt.date(year, month, min(today.day, 28)).isoformat()


def _scenario_case(
    finance: Any, name: Literal["low", "base", "high"], one_off: float, monthly: float, hires: int, **levers: float
) -> tuple[CostCase, Any]:
    adjustments = Adjustments(one_off_cost=one_off, spend_change_monthly=monthly, new_hires=hires, **levers)
    result = finance.scenario.run(adjustments, horizon=12)
    base = None if result.base_runway_months is None else float(result.base_runway_months)
    scenario = None if result.scenario_runway_months is None else float(result.scenario_runway_months)
    change = None if base is None or scenario is None else round(scenario - base, 2)
    mrr = float(result.points[2].scenario_mrr) if len(result.points) > 2 else None
    each = next((float(a.value) for a in result.assumptions if a.name == "cost_per_hire"), 0.0)
    return (
        CostCase(
            name=name,
            one_off=round(one_off, 2),
            monthly=round(monthly + hires * each, 2),
            base_runway_months=base,
            scenario_runway_months=scenario,
            runway_change_months=change,
            mrr_in_3_months=mrr,
        ),
        result,
    )


def _items(kind: str, inputs: dict[str, float], message: str) -> list[CostItem]:
    items: list[CostItem] = []
    for template in _TEMPLATES.get(kind, []):
        value = inputs.get(template.key)
        low, base, high = template.low, template.base, template.high
        if kind == "pricing" and template.key == "price" and _LOWERS_PRICE.search(message):
            low, base, high = -low, -base, -high
        if kind == "pricing" and template.key == "churn" and _LOWERS_PRICE.search(message):
            low, base, high = -0.5, -0.2, 0.0  # a cut: churn may ease, or not move at all
        if value is not None:
            if kind == "pricing" and template.key == "price" and _LOWERS_PRICE.search(message):
                value = -abs(value)
            low = base = high = value
        items.append(
            CostItem(
                key=template.key,
                name=template.name,
                cadence=template.cadence,
                low=low,
                base=base,
                high=high,
                basis="founder" if value is not None else "assumption",
            )
        )
    if kind == "spend" and _CUTS_SPEND.search(message):
        for item in items:
            if item.key == "amount":
                item.low, item.base, item.high = -abs(item.low), -abs(item.base), -abs(item.high)
                item.name = "Monthly spend saved"
    return [i for i in items if i.base or i.low or i.high or i.basis == "founder" or i.key in ("price", "churn")]


_LOWERS_PRICE = re.compile(r"\b(discounts?|(cut|lower|reduce|drop)\w* (our |the )?(prices?|fees|rates))\b", re.I)
_CUTS_SPEND = re.compile(r"\b(cut|reduce|lower|save|trim)\w*\b", re.I)


def _total(items: list[CostItem], cadence: str, which: str) -> float:
    return sum(getattr(i, which) for i in items if i.cadence == cadence and i.key != "round")


def _lever(items: list[CostItem], key: str, which: str) -> float:
    return next((float(getattr(i, which)) for i in items if i.key == key), 0.0)


def _cost_model(kind: str, subject: str, items: list[CostItem], finance: Any) -> tuple[CostModel, Any]:
    cases: list[CostCase] = []
    result: Any = None
    raised = next((i.base for i in items if i.key == "round"), 0.0)
    for which in ("low", "base", "high"):
        levers: dict[str, float] = {}
        if kind == "pricing":
            levers = {
                "price_change_pct": _lever(items, "price", which),
                "churn_change_pts": _lever(items, "churn", which),
            }
        hires = round(sum(getattr(i, which) for i in items if i.cadence == "count"))
        case, run = _scenario_case(
            finance,
            which,  # type: ignore[arg-type]
            _total(items, "one_off", which) - raised,
            _total(items, "monthly", which),
            hires,
            **levers,
        )
        cases.append(case)
        if which == "base":
            result = run
    each = next((float(a.value) for a in result.assumptions if a.name == "cost_per_hire"), None)
    model = CostModel(
        subject=subject,
        items=items,
        cases=cases,
        cost_per_person_monthly=each,
        currency=result.currency,
        as_of=result.as_of,
        growth_mode=result.growth_mode,
        sources=list(result.lineage.source_files),
    )
    return model, result


def _modelled_default(options: list[OptionCost], default: str) -> str:
    """Never propose an option the routine could not cost over ones it could (founder re-test 43): the cheapest
    costed option short of the full model is proposed instead."""
    chosen = next((o for o in options if o.name == default), None)
    if chosen is None or chosen.modelled:
        return default
    costed = [o for o in options if o.modelled and not o.is_full and o.runway_change_months is not None]
    if not costed:
        return default
    return max(costed, key=lambda o: o.runway_change_months or 0.0).name


def _option(
    finance: Any, name: str, note: str, one_off: float = 0, monthly: float = 0, hires: int = 0, **levers: float
) -> OptionCost:
    case, _ = _scenario_case(finance, "base", one_off, monthly, hires, **levers)
    return OptionCost(
        name=name,
        note=note,
        one_off=case.one_off,
        monthly=case.monthly,
        runway_change_months=case.runway_change_months if case.scenario_runway_months is not None else None,
    )


_TRADE_OFFS = {
    "Travel-led pilot": "you learn more slowly from trips than from a local presence, and win customers later.",
    "One remote rep": "one person is a key-person risk, and hiring takes time before you learn anything.",
    "Partner or distributor": "a partner keeps the customer relationship and a share, so you have less control of "
    "price and learn less about demand.",
    "Free-zone desk": "it adds a licence and a local hire, which take more commitment and are harder to undo.",
    "Full office": "it is the slowest to set up and the hardest to undo.",
    "No price change": "it teaches you nothing about what customers would pay.",
    "New customers only": "two price lists are more work, and revenue moves slowly because only new customers pay it.",
    "Design-partner pilot": "a few customers may not show demand from the wider market.",
    "Add-on to the current product": "it tests the current customers only, and takes one person away from the roadmap.",
    "Partner or white-label": "you depend on someone else's product and keep less margin and control.",
    "Full product line": "it needs a team before you have evidence of demand.",
    "Not now": "you learn nothing about demand, and the question comes back later.",
    "No change": "it teaches you nothing about whether more spending would work.",
    "Half the amount, as a test": "a smaller test takes longer to give a clear answer.",
    "The full amount": "it commits the most before you have evidence that it works.",
    "No raise: cut burn instead": "real cuts slow the plan and take time to show in the cash.",
    "Bridge from existing investors": "it depends on their appetite, and buys time rather than a new plan.",
    "Venture debt": "interest and covenants reduce your control if the plan slips.",
    "Priced round": "it takes the most time and dilution.",
    "A contractor for a fixed term": "a contractor builds less lasting knowledge in the team.",
    "Do not hire now": "the work waits, and you learn nothing about whether the role pays back.",
    "Hire one first, then review": "one person gives a slower and less certain answer.",
}


def _trade_off(name: str) -> str:
    if name in _TRADE_OFFS:
        return _TRADE_OFFS[name]
    if name.startswith("Change prices by"):
        return "it risks more churn while you learn how customers react."
    if name.startswith("Hire "):
        return "it commits the most before you have evidence that it works."
    return ""


def _options(
    kind: str, subject: str, finance: Any, model: CostModel | None, hires: int | None
) -> tuple[list[OptionCost], str]:
    """Realistic alternatives for this type, each costed by the same routine. The second value is the safe default."""
    base = model.case("base") if model is not None else None
    full = (
        OptionCost(
            name="",
            one_off=base.one_off,
            monthly=base.monthly,
            runway_change_months=base.runway_change_months,
            is_full=True,
        )
        if base is not None
        else None
    )

    def named(name: str, note: str) -> OptionCost:
        return full.model_copy(update={"name": name, "note": note}) if full else OptionCost(name=name, note=note)

    if kind == "new_office":
        return [
            _option(finance, "Travel-led pilot", "Sell from home with regular trips; easy to stop.", monthly=3000),
            _option(finance, "One remote rep", "One person on the ground, no premises.", hires=1, monthly=500),
            _option(finance, "Partner or distributor", "A local partner sells for a share; less control.", 5000, 1000),
            _option(finance, "Free-zone desk", "A licensed desk and one local hire.", 15000, 2000, 1),
            named("Full office", "The full model above; the hardest to undo."),
        ], "Travel-led pilot"
    if kind == "pricing" and model is not None:
        price = _lever(model.items, "price", "base")
        churn = _lever(model.items, "churn", "base")
        notice = _lever(model.items, "notice", "base")
        half = price / 2
        return [
            _option(finance, "No price change", "Keep prices as they are."),
            _option(
                finance,
                "New customers only",
                "Existing customers keep their price, so their churn is assumed not to change.",
                notice,
                price_change_pct=price,
                price_applies_to_existing=0.0,
            ),
            _option(
                finance,
                f"Change prices by {half:+g} %",
                "A smaller step, for less churn risk.",
                notice,
                price_change_pct=half,
                churn_change_pts=churn / 2,
            ),
            named(f"Change prices by {price:+g} %", "The full change, for all customers."),
        ], "New customers only"
    if kind == "new_product":
        return [
            _option(finance, "Design-partner pilot", "Build for a few customers who help pay for it.", 10000, 1000),
            _option(
                finance, "Add-on to the current product", "One person, inside the existing product.", 30000, 500, 1
            ),
            _option(finance, "Partner or white-label", "Resell someone else's product first.", 10000, 2000),
            named("Full product line", "The full model above; a dedicated team."),
            _option(finance, "Not now", "Keep the team on the current product."),
        ], "Design-partner pilot"
    if kind == "spend" and model is not None:
        amount = _lever(model.items, "amount", "base")
        return [
            _option(finance, "No change", "Keep spending as it is."),
            _option(finance, "Half the amount, as a test", "Learn at half the cost.", monthly=amount / 2),
            named("The full amount", "The full model above."),
        ], "Half the amount, as a test"
    if kind == "fundraise":
        return [
            _option(finance, "No raise: cut burn instead", "Keeps ownership; needs real cuts.", monthly=-10000),
            _option(finance, "Bridge from existing investors", "Small and quick; less dilution.", 5000),
            _option(finance, "Venture debt", "No dilution, but interest and covenants.", 10000, 3000),
            named("Priced round", "The full fees above; the most time and dilution."),
        ], "Bridge from existing investors"
    if kind == "hire" and hires is not None:
        options = [
            _option(finance, f"Hire {hires} as asked", "At your average loaded cost.", hires=hires).model_copy(
                update={"basis": "your payroll data"}
            ),
            OptionCost(
                name="A contractor for a fixed term",
                note="Similar monthly cost, and it ends when you stop; the routine cannot model the end date yet.",
                modelled=False,
            ),
            _option(finance, "Do not hire now", "Keep the team as it is."),
        ]
        if hires > 1:
            first = _option(finance, "Hire one first, then review", "Test before adding more.", hires=1)
            options.insert(1, first.model_copy(update={"basis": "your payroll data"}))
            return options, "Hire one first, then review"
        return options, "A contractor for a fixed term"
    return [], ""


_DECIDE_GOAL = re.compile(r"^\s*(decide|choose|determine|work out|figure out)\b", re.I)
_RUNWAY_GOAL = re.compile(
    r"runway\b.*?\b(?:past|above|over|beyond|to|at least|more than)\s+(\d+(?:\.\d+)?)\s*months", re.I
)
_NO_FINANCING = re.compile(r"without (new |more |any )?(financ\w*|funding|raising|investors?)", re.I)
_METRIC_GOAL = re.compile(r"\b(under|below|above|over|past|at least)\s+(\d+(?:\.\d+)?)\s*(%|percent)", re.I)
_GOALS_HEADING = re.compile(r"^#{1,6}\s*.*\bgoals?\b", re.I)
_LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_CONTENT_STOP = frozenset(
    {
        *("a", "an", "and", "the", "our", "of", "to", "in", "on", "for", "with", "by", "from", "whether", "or"),
        *("open", "decide", "choose", "new", "second", "next", "this", "that", "should", "we", "write", "memo"),
        *("decision", "month", "months", "sales"),
    }
)
_WIKILINK = re.compile(r"\s*\(see \[\[[^\]]*\]\]\)|\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")


def goals_from_note(content: str) -> list[str]:
    """The list under a heading that names goals, in the note's own words."""
    goals: list[str] = []
    inside = False
    for line in content.splitlines():
        if line.lstrip().startswith("#"):
            inside = bool(_GOALS_HEADING.match(line.strip()))
            continue
        match = _LIST_LINE.match(line) if inside else None
        if match:
            goals.append(_WIKILINK.sub(lambda m: m.group(1) or "", match.group(1)).strip().rstrip("."))
    return goals


def _company_goals(ctx: Any) -> list[str]:
    try:
        return goals_from_note(str(ctx.vault.vault.read_note(COMPANY_NOTE).get("content", "")))
    except Exception as exc:  # no vault, no note: the goal check says so rather than failing the run
        logger.info("No company goals: {}", type(exc).__name__)
        return []


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _CONTENT_STOP}


def _goal_about_this(goal: str, kind: str, message: str) -> bool:
    if kind == "new_office" and re.search(r"\b(region|office|market|expan\w*|countr\w*|branch)\b", goal, re.I):
        return True
    return bool(_words(goal) & _words(message))


def _check_goal(goal: str, frame: DecisionFrame, finance: Any) -> GoalCheck:
    change = None
    if frame.cost_model is not None:
        change = frame.cost_model.case("base").runway_change_months
    quote = f'"{goal}"'
    if _DECIDE_GOAL.match(goal):
        if _goal_about_this(goal, frame.type, frame.message):
            return GoalCheck(
                goal=goal,
                status="open_question",
                sentence=(
                    f"Your goal {quote} is still an open question, not a decision: "
                    "nothing on record says you have decided it."
                ),
            )
        return GoalCheck(goal=goal, status="not_affected", sentence=f"Your goal {quote} is not touched by this.")
    if frame.type == "fundraise" and _NO_FINANCING.search(goal):
        return GoalCheck(
            goal=goal,
            status="moves_away",
            sentence=f"This moves you away from your goal {quote}: a raise is new financing.",
        )
    target = _RUNWAY_GOAL.search(goal)
    if target:
        runway = next((b for b in frame.baseline if b.metric == "runway"), None)
        today = (
            f"runway is {runway.value:.2f} months today, against your {float(target.group(1)):g}-month target"
            if runway
            else "today's runway is unknown"
        )
        if change is None:
            return GoalCheck(
                goal=goal,
                status="not_checked",
                sentence=f"Your goal {quote}: {today}, and the effect of this on runway is not modelled yet.",
            )
        if change < 0:
            return GoalCheck(
                goal=goal,
                status="moves_away",
                sentence=(
                    f"This moves you away from your goal {quote}: {today}, and the base case changes projected runway "
                    f"by {change:+.2f} months."
                ),
            )
        if change > 0:
            return GoalCheck(
                goal=goal,
                status="moves_towards",
                sentence=(
                    f"This moves you toward your goal {quote}: {today}, and the base case changes projected runway "
                    f"by {change:+.2f} months."
                ),
            )
        return GoalCheck(
            goal=goal,
            status="not_affected",
            sentence=f"Your goal {quote}: {today}, and the base case does not change it.",
        )
    if _METRIC_GOAL.search(goal) and re.search(r"churn", goal, re.I):
        extra = 0.0
        if frame.cost_model is not None:
            extra = _lever(frame.cost_model.items, "churn", "base")
        current = _metric(finance, "logo_churn")
        today = (
            f"logo churn is {written_value(current.value, current.unit)} today"
            if current
            else "logo churn is unknown today"
        )
        if extra > 0:
            return GoalCheck(
                goal=goal,
                status="moves_away",
                sentence=(
                    f"This moves you away from your goal {quote}: {today}, and the base case assumes {extra:+g} "
                    f"percentage points more each month ({ASSUMPTION_LABEL})."
                ),
            )
        return GoalCheck(
            goal=goal,
            status="not_affected",
            sentence=f"Your goal {quote}: {today}, and this is not modelled to change it.",
        )
    return GoalCheck(
        goal=goal,
        status="not_checked",
        sentence=f"Your goal {quote}: compare this with it yourself; no routine measures it.",
    )


def _metric(finance: Any, name: str) -> BaselineFigure | None:
    try:
        result = finance.metrics.compute(name)
    except Exception as exc:  # no data for this metric: the frame leaves it out
        logger.info("No {} for the decision frame: {}", name, type(exc).__name__)
        return None
    if result.value is None:
        return None
    return BaselineFigure(
        metric=result.metric,
        label=result.label,
        value=float(result.value),
        unit=result.unit,
        as_of=result.as_of,
        sources=list(result.lineage.source_files),
    )


_BASELINE: dict[str, tuple[str, ...]] = {
    "pricing": ("runway", "mrr", "arpa", "logo_churn", "gross_margin"),
    "new_product": ("runway", "net_burn", "mrr"),
    "fundraise": ("runway", "net_burn", "mrr"),
    "spend": ("runway", "net_burn", "cac"),
}
_RELEVANT_METRICS: dict[str, frozenset[str]] = {
    "hire": frozenset({"runway", "net_burn", "gross_burn"}),
    "new_office": frozenset({"runway", "net_burn", "gross_burn", "arpa", "cac", "ltv", "ltv_cac"}),
    "pricing": frozenset({"runway", "mrr", "arr", "arpa", "logo_churn", "revenue_churn", "nrr", "gross_margin"}),
    "spend": frozenset({"runway", "net_burn", "gross_burn", "cac", "cac_payback"}),
    "fundraise": frozenset({"runway", "net_burn", "gross_burn", "mrr", "arr", "revenue_growth"}),
    "new_product": frozenset({"runway", "net_burn", "gross_burn", "mrr", "arpa"}),
    "other": frozenset({"runway", "net_burn"}),
}


def relevant_metric(frame: DecisionFrame | None, metric: str) -> bool:
    return frame is None or metric in _RELEVANT_METRICS[frame.type]


def starter_outcomes_for(
    frame: DecisionFrame, option_name: str, today: dt.date | None = None
) -> tuple[list[Outcome], list[Outcome]]:
    """The starters for the option actually proposed: a pilot's stop rule is not a full office's budget."""
    option = next((o for o in frame.options if o.name == option_name), None)
    return _starter_outcomes(frame, today or dt.date.today(), option)


def names_goal(goal: str, text: str) -> bool:
    """Has the text told the founder about this goal? Its exact words, or a sentence on "your goal" close to them."""
    if goal.casefold() in text.casefold():
        return True
    wanted = {w[:5] for w in _words(goal)}
    if not wanted:
        return False
    return any(
        re.search(r"\bgoals?\b", sentence, re.I)
        and len(wanted & {w[:5] for w in _words(sentence)}) >= 0.6 * len(wanted)
        for sentence in split_sentences(text)
    )


def _starter_outcomes(
    frame: DecisionFrame, today: dt.date, option: OptionCost | None = None
) -> tuple[list[Outcome], list[Outcome]]:
    """A measurable forecast and stop rules, from the model's own numbers. Starters: the founder sets the odds."""
    six = _in_months(today, 6)
    three = _in_months(today, 3)
    runway = next((b for b in frame.baseline if b.metric == "runway"), None)
    model = frame.cost_model

    def money(value: float) -> str:
        return format_money(value, frame.currency)

    predictions: list[Outcome] = []
    kills: list[Outcome] = []
    if model is not None:
        base, high = model.case("base"), model.case("high")
        partial = option is not None and not option.is_full
        if option is not None and partial:
            # An option has one estimate, so its limit is half as much again. The full model's MRR and round are
            # not its results. Churn stays below as a ceiling: no smaller change should pass it.
            base = CostCase(
                name="base",
                one_off=option.one_off,
                monthly=option.monthly,
                runway_change_months=option.runway_change_months,
            )
            high = CostCase(
                name="high",
                one_off=round(option.one_off * 1.5, 2),
                monthly=round(option.monthly * 1.5, 2),
                runway_change_months=option.runway_change_months,
            )
        spend_cap = round(high.one_off + 6 * high.monthly, 2)
        if spend_cap > 0:
            kills.append(Outcome(metric="Total spent on this", threshold=f"> {money(spend_cap)}", by=six))
        yearly = round(12 * base.monthly, 2)
        if frame.type == "new_office" and yearly > 0:
            place = _place(frame.message) or "new-region"
            predictions.append(Outcome(metric=f"Qualified {place} pipeline", threshold=f">= {money(yearly)}", by=six))
            kills.append(
                Outcome(metric=f"Qualified {place} pipeline", threshold=f"< {money(round(yearly / 2, 2))}", by=six)
            )
        elif frame.type == "new_product" and base.monthly > 0:
            predictions.append(
                Outcome(
                    metric="Monthly revenue from the new line",
                    threshold=f">= {money(base.monthly)}",
                    by=_in_months(today, 12),
                )
            )
            kills.append(Outcome(metric="Paying customers on the new line", threshold="< 3", by=six))
        elif frame.type == "pricing":
            churn = _metric_value(frame, "logo_churn")
            extra = _lever(model.items, "churn", "base")
            high_extra = _lever(model.items, "churn", "high")
            if churn is not None:
                predictions.append(
                    Outcome(metric="Monthly logo churn", threshold=f"<= {churn * 100 + extra:.2f} %", by=three)
                )
                kills.append(
                    Outcome(metric="Monthly logo churn", threshold=f"> {churn * 100 + high_extra:.2f} %", by=three)
                )
            if base.mrr_in_3_months is not None:
                predictions.append(Outcome(metric="MRR", threshold=f">= {money(base.mrr_in_3_months)}", by=three))
        elif frame.type == "spend" and base.monthly > 0:
            predictions.append(
                Outcome(metric="New MRR from this spend", threshold=f">= {money(base.monthly)}", by=three)
            )
            kills.append(
                Outcome(metric="New MRR from this spend", threshold=f"< {money(round(base.monthly / 2, 2))}", by=three)
            )
        elif frame.type == "hire" and base.monthly > 0:
            predictions.append(
                Outcome(metric="Monthly revenue from this work", threshold=f">= {money(base.monthly)}", by=six)
            )
        elif frame.type == "fundraise":
            raised = next((i.base for i in model.items if i.key == "round"), 0.0)
            if raised and not partial:
                predictions.append(Outcome(metric="Cash raised", threshold=f">= {money(raised)}", by=six))
        change = base.runway_change_months
        high_change = high.runway_change_months
        if runway is not None and change is not None:
            floor = runway.value + change
            predictions.append(Outcome(metric="Runway (actual burn)", threshold=f">= {floor:.2f} months", by=six))
        if runway is not None and high_change is not None:
            # Under the forecast, and under today: a floor already passed would fire at once.
            floor = min(runway.value + high_change, runway.value) - (
                0.5 if high_change == change or high_change >= 0 else 0
            )
            kills.append(Outcome(metric="Runway (actual burn)", threshold=f"< {floor:.2f} months", by=six))
    elif runway is not None:
        predictions.append(Outcome(metric="Runway (actual burn)", threshold=f">= {runway.value:.2f} months", by=six))
        kills.append(Outcome(metric="Runway (actual burn)", threshold=f"< {runway.value - 1:.2f} months", by=six))
    if not predictions:
        predictions.append(
            Outcome(metric="Main result this decision is for", threshold=">= the target you set", by=six)
        )
    if not kills:
        kills.append(Outcome(metric="Total spent on this", threshold="> the limit you set", by=six))
    return predictions[:3], kills[:3]


def _metric_value(frame: DecisionFrame, metric: str) -> float | None:
    return next((b.value for b in frame.baseline if b.metric == metric), None)


def _facts(frame: DecisionFrame) -> list[Fact]:
    """Everything the frame states, so an agent may repeat it, with a label that keeps its meaning."""
    facts: list[Fact] = []

    def money(value: float, label: str) -> None:
        facts.append(Fact(float(value), label, "money", frame.currency))

    def months(value: float | None, label: str) -> None:
        if value is not None:
            facts.append(Fact(float(value), label, "months", "months", frozenset({"runway"})))

    model = frame.cost_model
    if model is not None:
        if model.cost_per_person_monthly is not None:
            facts.append(
                Fact(
                    model.cost_per_person_monthly,
                    "Average loaded cost per person",
                    "money",
                    frame.currency,
                    frozenset({"hire_cost"}),
                )
            )
        for item in model.items:
            for value in (item.low, item.base, item.high):
                if item.cadence in ("one_off", "monthly"):
                    money(value, f"{item.name} ({ASSUMPTION_LABEL})")
                else:
                    facts.append(Fact(float(value), f"{item.name} ({ASSUMPTION_LABEL})"))
        for case in model.cases:
            money(case.one_off, f"{case.name} case up-front cost ({ASSUMPTION_LABEL})")
            money(case.monthly, f"{case.name} case monthly cost ({ASSUMPTION_LABEL})")
            months(case.base_runway_months, "Projected runway without this decision")
            months(case.scenario_runway_months, f"Projected runway, {case.name} case")
            months(case.runway_change_months, f"Change in projected runway, {case.name} case")
    for option in frame.options:
        facts.extend(Fact(f.value) for f in extract_figures(option.name))  # "Change prices by +5 %"
        money(option.one_off, f"{option.name}: up-front cost ({ASSUMPTION_LABEL})")
        money(option.monthly, f"{option.name}: monthly cost ({ASSUMPTION_LABEL})")
        months(option.runway_change_months, f"{option.name}: change in projected runway")
    for goal in frame.goals:
        facts.extend(Fact(f.value) for f in extract_figures(goal.goal))  # the founder's own, from the company profile
    for figure in frame.baseline:
        if figure.unit == "months":
            months(figure.value, figure.label)
        elif figure.unit == "ratio":
            facts.append(Fact(figure.value, figure.label, "ratio", "", frozenset({"churn"})))
        else:
            money(figure.value, figure.label)
    return facts


def _subject(kind: str, message: str) -> str:
    place = _place(message)
    return {
        "new_office": f"A full {place} office" if place else "A full new office",
        "pricing": "This price change",
        "new_product": "A full new product line",
        "spend": "This spending change",
        "fundraise": "This fundraise",
        "hire": "This hire",
    }.get(kind, "This decision")


def build_frame(
    message: str, ctx: Any, planner_label: str | None = None, today: dt.date | None = None
) -> DecisionFrame:
    """Never raises: with no data or no vault, the frame simply says less and the run goes on."""
    today = today or dt.date.today()
    kind = classify_decision(message, planner_label)
    frame = DecisionFrame(type=kind, subject=_subject(kind, message), message=message)
    finance = getattr(ctx, "finance", None)
    templates = _TEMPLATES.get(kind, [])
    frame.questions = [t.question for t in templates if t.question][:3]
    if kind == "other":
        frame.questions = ["what this costs up front", "what it costs each month"]
    try:
        names = _BASELINE.get(kind, ("runway", "net_burn"))
        # Stop rules are checked against today's churn whatever the decision. Metrics lists only what is relevant.
        names = names if "logo_churn" in names else (*names, "logo_churn")
        frame.baseline = [f for f in (_metric(finance, n) for n in names) if f is not None]
        frame.currency = next((b.unit for b in frame.baseline if re.fullmatch(r"[A-Z]{3}", b.unit)), "USD")
        frame.as_of = frame.baseline[0].as_of if frame.baseline else ""
        if kind == "hire":
            _frame_hire(frame, finance)
        elif templates:
            inputs = parse_inputs(message, kind)
            items = _items(kind, inputs, message)
            model, _ = _cost_model(kind, frame.subject, items, finance)
            if kind == "pricing":
                pct = _lever(items, "price", "base")
                model.subject = frame.subject = f"A {pct:+g} % price change"
                model.scope_note = "The price and churn effects are in these runway figures."
            if kind == "fundraise":
                model.scope_note = "Fees and cash raised only: dilution and founder time are not modelled."
            frame.cost_model = model
            frame.currency = model.currency
            frame.options, frame.default_option = _options(kind, frame.subject, finance, model, None)
    except Exception as exc:  # no financial data yet, or a bad input: an unmodelled frame, not a failed run
        logger.info("No cost model for this decision: {}: {}", type(exc).__name__, exc)
        frame.cost_model = None
    frame.options = [o.model_copy(update={"trade_off": _trade_off(o.name)}) for o in frame.options]
    frame.default_option = _modelled_default(frame.options, frame.default_option)
    frame.goals = [_check_goal(goal, frame, finance) for goal in _company_goals(ctx)]
    frame.predictions, frame.kill_criteria = _starter_outcomes(frame, today)
    frame.facts = _facts(frame)
    return frame


_HIRES_ASKED = re.compile(
    r"\bhir(?:e|ing)\s+(?:(?:another|more|new|additional)\s+)?"
    r"(a(?!\s+(?:couple|few|lot|bit|good|bad|great|smart|wise)\b)|an|one|two|three|four|five|six|seven|eight|nine"
    r"|\d{1,3}(?!\s*%))\b"
    r"|\bhir(?:e|ing)\s+(another)\b",
    re.I,
)


_COUNT_WORDS = r"(one|two|three|four|five|six|seven|eight|nine|\d{1,3})"
# A follow-up that sets the size: "make it a two person team", "a team of 3", "only 2 people".
_HIRES_TEAM = re.compile(
    rf"\b{_COUNT_WORDS}[\s-]+(?:person|people|persons|hires?)\b|\bteam\s+of\s+{_COUNT_WORDS}\b", re.I
)


def _hires_word(message: str) -> str | None:
    """How many people, from the founder's words. A later statement (a follow-up) replaces an earlier one."""
    found = [(m.start(), (m.group(1) or "one")) for m in _HIRES_ASKED.finditer(message)]
    found += [(m.start(), m.group(1) or m.group(2)) for m in _HIRES_TEAM.finditer(message)]
    return max(found)[1].lower() if found else None


def _frame_hire(frame: DecisionFrame, finance: Any) -> None:
    word = _hires_word(frame.message)
    if word is None:
        frame.questions = ["how many people you mean"]
        return
    hires = int(word) if word.isdigit() else {"a": 1, "an": 1, **_NUMBER_WORDS}[word]
    frame.hires = hires
    frame.questions = []
    item = CostItem(key="hires", name="New hires", cadence="count", low=hires, base=hires, high=hires, basis="founder")
    frame.cost_model, _ = _cost_model("hire", "This hire", [item], finance)
    frame.options, frame.default_option = _options("hire", frame.subject, finance, frame.cost_model, hires)


# --- the lane's question ---------------------------------------------------------------------------------------------
def inputs_question(frame: DecisionFrame) -> str:
    """Asked once, while the team works. It names no figures, because the lane never does."""
    wanted = frame.questions
    if not wanted:
        return ""
    joined = wanted[0] if len(wanted) == 1 else f"{', '.join(wanted[:-1])} and {wanted[-1]}"
    topic = frame.subject[0].lower() + frame.subject[1:] if frame.subject.startswith(("A ", "This ")) else frame.subject
    return f"While the team works, for {topic}: tell me {joined}. Until you do, I use assumptions you can correct."
