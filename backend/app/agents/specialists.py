"""What the specialist agents (PRD F3) need beyond the shared runtime: team cues, rule answers, risks and the memo.

Everything here is code, not model judgement: which types a message calls for, the risk register built from the
Devil's Advocate's lines, and the memo file (path, review date, metrics with lineage, predictions in the calibration
store). The model supplies only the prose and its forecasts, and those go through the Verifier like any other answer.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.agents.decision_frame import (
    ASSUMPTION_LABEL,
    BaselineFigure,
    DecisionFrame,
    relevant_metric,
    starter_outcomes_for,
)
from app.agents.events import Artifact
from app.agents.guards import guarded, without_contradictions
from app.agents.verifier import Fact, split_sentences, verify_numbers
from app.engine.calibration import PredictionIn
from app.vault.manager import NoteExistsError

REVIEW_AFTER_DAYS = 30
MAX_TEAM = 8
REGULATORY_NOTE = "This flags points to verify with a qualified adviser; it is not legal or tax advice."
SCOUT_LOCAL_NOTE = "This comes from your vault only: cloud is off, so no web research was done."

# Words that call for a type whatever the plan says. A small model can leave a specialist out; the founder asked.
_CUES: list[tuple[str, re.Pattern[str]]] = [
    (
        "market_scout",
        re.compile(r"\b(markets?|competitors?|competition|market size|open\w* (an?|our) .*(office|branch))\b", re.I),
    ),
    (
        "regulatory_tax",
        re.compile(r"\b(regulat\w*|tax\w*|legal|complian\w*|licen[cs]\w*|open\w* (an?|our) .*(office|branch))\b", re.I),
    ),
    ("revenue_customer", re.compile(r"\b(pricing|price|prices|churn|pipeline|segments?|upsell|discounts?)\b", re.I)),
    (
        "people_ops",
        re.compile(
            r"\b(capacity|key[- ]person|execution plan|team structure|org chart|reorg\w*|who would own)\b", re.I
        ),
    ),
    ("prioritiser", re.compile(r"\b(prioriti[sz]\w*|rank|which of|score these|2x2)\b", re.I)),
    (
        "perspective_lens",
        re.compile(r"\b(investor|largest customer|competitor ceo|lens|perspective|point of view)\b", re.I),
    ),
    (
        "devils_advocate",
        re.compile(
            r"\b(pre-?mortem|red[- ]team|what could go wrong|downside|devil'?s advocate|risks?|"
            r"open\w* (an?|our) .*(office|branch))\b",
            re.I,
        ),
    ),
    ("memo_writer", re.compile(r"\b(memo|record (the|this) decision|write (it|this) up)\b", re.I)),
]
_NEEDS_NUMBERS = frozenset({"devils_advocate", "memo_writer", "revenue_customer", "people_ops", "prioritiser"})
_LENS_NAME = re.compile(r"\b(investor|largest customer|competitor ceo)\b", re.I)

RULE_TEXT: dict[str, str] = {
    "devils_advocate": (
        "Pre-mortem, written without the language model: assume this failed after 6 months.\n"
        "- Risk: it cost more and took longer than planned. Likelihood: medium. Impact: high. "
        "Mitigation: set a spending limit and a stop date before starting.\n"
        "- Risk: the demand it assumes is not there. Likelihood: medium. Impact: high. "
        "Mitigation: test with a small pilot first.\n"
        "- Risk: it pulls the team off the core business. Likelihood: medium. Impact: medium. "
        "Mitigation: name one owner and protect current priorities."
    ),
    "people_ops": (
        "Written without the language model. Check who would own this, what they stop doing, and whether it depends "
        "on one person."
    ),
    "prioritiser": (
        "Written without the language model, so nothing was scored. Give the options and how much value and "
        "feasibility matter to you, and the scoring routine will rank them."
    ),
    "perspective_lens": (
        "Written without the language model. Ask what this viewpoint would need to believe for this to be a good "
        "decision, and what would change its mind."
    ),
    "regulatory_tax": (
        "Written without the language model, so nothing specific was checked. Points to verify with your adviser:\n"
        "- Whether this needs a licence, registration or filing where it happens.\n"
        "- What tax it creates, and where.\n"
        "- Which employment rules apply to anyone hired or moved for it.\n"
        "- What it changes in your contracts, customer terms and data handling."
    ),
    "market_scout": "Written without the language model, and nothing relevant was found in the vault.",
}


def team_for_message(message: str) -> list[str]:
    """The specialist types a message asks for, in the order the table lists them."""
    return [agent_type for agent_type, cue in _CUES if cue.search(message)]


_LOOKUP = re.compile(r"\b(my notes|my journal|did we decide|board update)\b", re.I)
_DECISION_SHAPED = re.compile(r"\b(should|would|could|if|who are)\b", re.I)
_ONLY_WHEN_DECIDING = frozenset({"revenue_customer", "market_scout"})


def calls_for_team(message: str) -> bool:
    """True when the founder's words ask for a specialist, so the message is not a plain lookup.

    "What is our churn?" is a metric and "What do my notes say about pricing?" is a search, though both name a
    specialist's subject. "What would a discount do to churn?" needs the specialist.
    """
    types = set(team_for_message(message))
    if not types or _LOOKUP.search(message):
        return False
    return bool(types - _ONLY_WHEN_DECIDING) or bool(_DECISION_SHAPED.search(message))


def needs_analyst(types: list[str]) -> bool:
    return "financial_analyst" not in types and any(t in _NEEDS_NUMBERS for t in types)


def lens_name(brief: str) -> str | None:
    """ "Investor: would you fund this?" -> "Investor"."""
    match = _LENS_NAME.search(brief)
    if match:
        return match.group(1).capitalize()
    head, colon, _ = brief.partition(":")
    return head.strip()[:30] if colon and head.strip() else None


def default_brief(agent_type: str, message: str) -> str:
    return {
        "market_scout": f"Market size, competitors and local conditions for: {message}",
        "regulatory_tax": f"Compliance and tax points to verify for: {message}",
        "revenue_customer": f"Pricing, churn, pipeline and segment value for: {message}",
        "people_ops": f"Hiring, capacity, key-person risk and execution plan for: {message}",
        "prioritiser": f"Score and rank the options in: {message}",
        "perspective_lens": f"Investor: how would an investor see this? {message}",
        "devils_advocate": f"Pre-mortem: it failed after 6 months. Why? {message}",
        "memo_writer": f"Write the decision memo for: {message}",
    }.get(agent_type, message)


# --- the Devil's Advocate's risk register ----------------------------------------------------------------------------
_RISK_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*(.+)$")
_RISK_FIELD = re.compile(r"\b(risk|likelihood|impact|mitigation)\s*:\s*", re.I)


def _risk_from_line(line: str) -> dict[str, str]:
    parts = _RISK_FIELD.split(line)
    fields = {
        parts[i].lower(): parts[i + 1].strip(" .;,*") for i in range(1, len(parts) - 1, 2) if parts[i + 1].strip()
    }
    risk = fields.get("risk") or (parts[0].strip(" .;,*") if parts[0].strip(" .;,*") else line.strip())
    return {
        "risk": risk,
        "likelihood": fields.get("likelihood", "not rated").lower(),
        "impact": fields.get("impact", "not rated").lower(),
        "mitigation": fields.get("mitigation", ""),
    }


def risks_from_text(text: str) -> list[dict[str, str]]:
    """One row per list line. A model that wrote prose instead still gets a register, one row per sentence."""
    lines = [m.group(1) for line in text.splitlines() if (m := _RISK_LINE.match(line))]
    if not lines:
        lines = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    return [_risk_from_line(line) for line in lines][:8]


def risk_register(agent_id: str, text: str) -> Artifact:
    return Artifact(
        id=f"art_{uuid.uuid4().hex[:10]}",
        kind="risk_register",
        title="Risk register",
        agent_id=agent_id,
        data={"risks": risks_from_text(text)},
    )


# --- the memo --------------------------------------------------------------------------------------------------------
_OUTCOME_COMPARE = re.compile(
    r"(>=|<=|>|<|≥|≤|\bat least\b|\bat most\b|\bmore than\b|\bless than\b|\bfewer than\b|\bover\b|\bunder\b|"
    r"\bbelow\b|\babove\b|\bexceeds?\b)",
    re.I,
)
_A_TASK = re.compile(
    r"^\s*(?:the\s+)?(?:complete|completed|finish|finished|conduct|conducted|research|researched|prepare|prepared|"
    r"draft|drafted|engage|engaged|obtain|obtained|identify|identified|finalise|finalize|review|reviewed|meet with|"
    r"talk to|speak to|consult)\b|\b(?:research|study|analysis|report|plan|assessment|review)\b[^.]*\b(?:done|"
    r"complete|completed|finished|delivered|ready)\b",
    re.I,
)
_WITHIN = re.compile(r"\b(?:within|in|after)\s+(\d{1,2}|one|two|three|six|nine|twelve)\s+(months?|weeks?)\b", re.I)
_WORD_COUNT = {"one": 1, "two": 2, "three": 3, "six": 6, "nine": 9, "twelve": 12}
_ISO_DAY = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_MONTH_YEAR = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(20\d{2})\b",
    re.I,
)
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def outcome_date(text: str, today: dt.date) -> dt.date | None:
    """The date in a forecast or a stop rule, or None. A date already past checks nothing."""
    found: dt.date | None = None
    if match := _ISO_DAY.search(text):
        try:
            found = dt.date.fromisoformat(match.group(1))
        except ValueError:
            return None
    elif match := _MONTH_YEAR.search(text):
        index = _MONTHS.index(match.group(1).lower()[:3]) + 1
        found = dt.date(int(match.group(2)), index, calendar.monthrange(int(match.group(2)), index)[1])
    elif match := _WITHIN.search(text):
        word = match.group(1).lower()
        count = int(word) if word.isdigit() else _WORD_COUNT[word]
        days = count * 7 if match.group(2).lower().startswith("week") else count * 30
        found = today + dt.timedelta(days=days)
    return found if found is not None and found > today else None


class _Measurable(BaseModel):
    """A metric, a threshold and a date. A model can give the three fields, or one sentence that has all three."""

    statement: str = ""
    metric: str = ""
    threshold: str = ""
    by: str = ""

    def text(self) -> str:
        if self.metric and self.threshold:
            return f"{self.metric.strip()} {self.threshold.strip()} by {self.by.strip()}".strip()
        return self.statement.strip()

    def is_measurable(self, today: dt.date) -> bool:
        text = self.text()
        has_number = re.search(r"\d", _ISO_DAY.sub(" ", _MONTH_YEAR.sub(" ", _WITHIN.sub(" ", text)))) is not None
        return (
            has_number
            and _OUTCOME_COMPARE.search(text) is not None
            and outcome_date(text, today) is not None
            and _A_TASK.search(self.metric or text) is None
        )


class MemoPrediction(_Measurable):
    probability: float = 0.5
    starter: bool = Field(False, description="Written by code from the cost model; the founder sets the odds")

    @field_validator("probability", mode="before")
    @classmethod
    def _as_fraction(cls, value: Any) -> float:
        """A model can write 70 or "70%". A forecast is never certain, so it stays inside 1 % to 99 %."""
        number = float(str(value).strip().rstrip("%"))
        number = number / 100 if number > 1 else number
        return min(0.99, max(0.01, number))

    def line(self) -> str:
        odds = f"{self.probability:.0%}" + (" (starter: set your own)" if self.starter else "")
        return f"{odds}: {self.text()}"


class MemoCriterion(_Measurable):
    starter: bool = False

    def line(self) -> str:
        rule = re.sub(r"^stop if ", "", self.text(), flags=re.I)
        return f"Stop if {rule}" + (" (starter: confirm)" if self.starter else "")


class MemoOption(BaseModel):
    name: str
    note: str = ""


def _as_option(value: Any) -> Any:
    if isinstance(value, str):
        name, _, note = value.partition(":")
        return {"name": name.strip(), "note": note.strip()}
    return value


class MemoDraft(BaseModel):
    """The prose of a memo, from the model. Code adds the path, dates, costs, metrics and lineage."""

    title: str = ""
    chosen: str = Field("", description="The one option recommended")
    why_chosen: str = ""
    decision: str = Field("", description="Written by code from `chosen` once the memo is final")
    context: str = ""
    options: list[MemoOption] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list, description="Written by code: every option but the chosen one")
    assumptions: list[str] = Field(default_factory=list)
    predictions: list[MemoPrediction] = Field(default_factory=list)
    kill_criteria: list[MemoCriterion] = Field(default_factory=list)
    open_numbers: list[str] = Field(default_factory=list, description="Figures with no source, for you to confirm")

    @field_validator("options", mode="before")
    @classmethod
    def _options(cls, value: Any) -> Any:
        return [_as_option(v) for v in value] if isinstance(value, list) else value

    @field_validator("predictions", "kill_criteria", mode="before")
    @classmethod
    def _outcomes(cls, value: Any) -> Any:
        return [{"statement": v} if isinstance(v, str) else v for v in value] if isinstance(value, list) else value

    def prose(self) -> str:
        """What the Verifier checks. A target in a forecast or stop rule is a stated aim, listed for the founder."""
        return "\n".join(
            [
                self.title,
                self.why_chosen,
                self.decision,
                self.context,
                *(o.note for o in self.options),
                *self.rejected,
                *self.assumptions,
            ]
        )


def memo_schema(frame: DecisionFrame | None) -> dict[str, Any]:
    names = [o.name for o in frame.options] if frame is not None else []
    outcome = {
        "metric": {"type": "string", "description": "A result in the business that can be measured"},
        "threshold": {"type": "string", "description": "A comparison and a number you chose for this decision"},
        "by": {"type": "string", "description": "A future date, YYYY-MM-DD"},
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "chosen": {
                "type": "string",
                "description": "The one option you recommend",
                **({"enum": names} if names else {}),
            },
            "why_chosen": {"type": "string", "description": "One or two sentences to the founder, as 'you'"},
            "context": {"type": "string"},
            "options": {
                "type": "array",
                "description": "Each option with one line for or against it",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", **({"enum": names} if names else {})},
                        "note": {"type": "string"},
                    },
                    "required": ["name", "note"],
                },
            },
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "predictions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {**outcome, "probability": {"type": "number", "description": "0 to 1"}},
                    "required": ["metric", "threshold", "by", "probability"],
                },
            },
            "kill_criteria": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "object", "properties": outcome, "required": ["metric", "threshold", "by"]},
            },
        },
        "required": ["title", "chosen", "why_chosen", "context", "options", "predictions", "kill_criteria"],
    }


class MemoRef(BaseModel):
    path: str
    title: str
    status: str
    review_date: str
    chosen: str = ""
    decision_type: str = ""
    predictions: list[str]
    kill_criteria: list[str]
    open_numbers: list[str] = Field(default_factory=list)
    assumptions_to_confirm: int = 0
    verified: bool


GENERIC_OPTIONS = ["Go ahead", "Run a small pilot first", "Do not do this now"]


def rule_draft(message: str) -> MemoDraft:
    """No model: a memo that records the question and says plainly what the founder still has to fill in."""
    return MemoDraft(
        title=memo_title(message),
        context="Written without the language model, from the team's findings below.",
        options=[MemoOption(name=name) for name in GENERIC_OPTIONS],
    )


_MEMO_PREFIX = re.compile(r"^(decision\s+)?memo\s*[:\-\u2013\u2014]\s*", re.I)
_ASKS = re.compile(r"^(should|shall|can|could|would|do|does|will)\s+(we|i)\s+", re.I)
_WANTS = re.compile(r"^(i|we)\s+(want|plan|need|would like|are thinking of|am thinking of)\s+(to\s+)?", re.I)
_SLUG_STOP = frozenset({"a", "an", "the", "our", "my", "to", "of", "in", "on", "for"})
_OPTION_STOP = frozenset({"a", "an", "the", "of", "to", "in", "for", "and", "or", "with", "first", "as", "now", "this"})


def memo_title(message: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", message.strip())[0].rstrip("?.! ")
    first = _WANTS.sub("", _ASKS.sub("", first))
    return (first[:1].upper() + first[1:])[:80] or "Decision"


def memo_slug(title: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in _SLUG_STOP]
    return "-".join(words[:7]) or "decision"


def _option_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _OPTION_STOP}


def _best_option(text: str, names: list[str]) -> tuple[str, float]:
    """The option `text` most clearly names, and how much of the option's name it covers."""
    words = _option_words(text)
    best, score = "", 0.0
    for name in names:
        wanted = _option_words(name)
        share = len(wanted & words) / len(wanted) if wanted else 0.0
        if share > score:
            best, score = name, share
    return best, score


def _chosen_option(draft: MemoDraft, names: list[str], default: str) -> tuple[str, bool]:
    """(the one chosen option, whether the model really chose it)."""
    wanted = draft.chosen.strip().casefold()
    exact = next((n for n in names if n.casefold() == wanted), None)
    if exact:
        return exact, True
    for text in (draft.chosen, draft.why_chosen, draft.decision):
        best, score = _best_option(text, names)
        if score >= 0.6:
            return best, True
    return (default if default in names else names[0]), False


# What a good reason for setting an option aside talks about, when it costs no more than the one proposed.
_STATES_A_REASON = re.compile(
    r"\b(?:control\w*|speed|slow\w*|fast\w*|quick\w*|time|revers\w*|undo|lock\w*|commit\w*|learn\w*|depend\w*|"
    r"quality|dilut\w*|trust|share|margin\w*|complian\w*|licen[cs]\w*|risk\w*|evidence|relationship\w*|covenant\w*|"
    r"interest|demand)\b",
    re.I,
)


def _costs_no_more(name: str, chosen: str, frame: DecisionFrame | None) -> bool:
    costs = {o.name: o for o in frame.options} if frame is not None else {}
    this, proposed = costs.get(name), costs.get(chosen)
    if this is None or proposed is None or not (this.modelled and proposed.modelled):
        return False
    if this.runway_change_months is None or proposed.runway_change_months is None:
        return False
    return this.runway_change_months >= proposed.runway_change_months


def _why_not(name: str, chosen: str, frame: DecisionFrame | None) -> str:
    """A reason from the numbers and the option's own trade-off, when the model gave none.

    An option that costs no more than the one proposed always says why it was set aside: control, speed, what it
    teaches. Seen live: "Not proposed, though it takes no more runway than Travel-led pilot", and nothing else.
    """
    costs = {o.name: o for o in frame.options} if frame is not None else {}
    this, proposed = costs.get(name), costs.get(chosen)
    trade_off = this.trade_off if this is not None else ""
    if this is None or proposed is None or this.runway_change_months is None or proposed.runway_change_months is None:
        return trade_off.capitalize() if trade_off else "Not chosen for now: its cost cannot be compared yet."
    if _costs_no_more(name, chosen, frame):
        return (
            f"Takes no more runway than {chosen} ({this.runway_change_months:+.2f} against "
            f"{proposed.runway_change_months:+.2f} months), but {trade_off or 'it teaches you less.'}"
        )
    if this.modelled and proposed.modelled:
        return (
            f"Takes more runway than {chosen}: {this.runway_change_months:+.2f} against "
            f"{proposed.runway_change_months:+.2f} months."
        )
    return trade_off.capitalize() if trade_off else "Not chosen for now: its runway effect is not modelled yet."


def _option_reason(name: str, draft: MemoDraft, frame: DecisionFrame | None = None) -> str:
    """The model's own line on this option, when it gave one. Repeating the option's description is not a line."""
    given = next((o.note for o in draft.options if o.name.casefold() == name.casefold() and o.note), "")
    described = next((o.note for o in frame.options if o.name == name), "") if frame is not None else ""
    if given and given.strip(" .").casefold() != described.strip(" .").casefold():
        return given
    for line in draft.rejected:
        if _best_option(line, [name])[1] >= 0.6:
            _, colon, why = line.partition(":")
            return why.strip() if colon else line
    return ""


_SPEND_WORDS = re.compile(r"\b(spend\w*|spent|cost\w*|budget)\b", re.I)
_RUNWAY_WORD = re.compile(r"\brunway\b", re.I)
_BELOW = re.compile(r"(<=?|≤|\bbelow\b|\bunder\b|\bless than\b|\bfewer than\b)", re.I)


_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|m|thousand|million)?\b", re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}


def _limit_in(criterion: MemoCriterion) -> float | None:
    """The number the rule stops at: from its threshold when it has one. "$400k" is 400,000; "11 months" is 11."""
    text = criterion.threshold or _ISO_DAY.sub(" ", criterion.text())
    found = list(_AMOUNT.finditer(text))
    if not found:
        return None
    # "Spend in the first 6 months > $300,000": the number after the comparison is the limit.
    after = next(
        (m for m in found if re.search(r"[<>≤≥]|\b(?:over|above|below|under|than)\b", text[: m.start()])), None
    )
    match = after or found[0]
    return float(match.group(1).replace(",", "")) * _SCALE.get((match.group(2) or "").lower(), 1)


def _kill_fits_the_model(criterion: MemoCriterion, frame: DecisionFrame | None, chosen: str = "") -> bool:
    """A stop rule cannot fire at once: a spend limit under what is proposed, or a runway floor already passed."""
    if frame is None:
        return True
    text = criterion.text()
    limit = _limit_in(criterion)
    if limit is None:
        return True
    runway = next((b.value for b in frame.baseline if b.metric == "runway"), None)
    if _RUNWAY_WORD.search(text):
        return runway is None or not _BELOW.search(text) or limit < runway
    churn = next((b.value for b in frame.baseline if b.metric == "logo_churn"), None)
    if churn is not None and re.search(r"\bchurn\b", text, re.I) and not _BELOW.search(text):
        return limit > churn * 100  # seen live: "churn above 1.5%", with churn at 1.67 % today
    if frame.cost_model is not None and _SPEND_WORDS.search(text):
        option = next((o for o in frame.options if o.name == chosen and o.modelled), None)
        cost = option if option is not None else frame.cost_model.case("base")
        return abs(limit) >= cost.one_off + cost.monthly
    return True


def _final_outcomes(
    draft: MemoDraft, frame: DecisionFrame | None, chosen: str, today: dt.date
) -> tuple[list[MemoPrediction], list[MemoCriterion]]:
    predictions = [p for p in draft.predictions if p.is_measurable(today)][:3]
    kills = [k for k in draft.kill_criteria if k.is_measurable(today) and _kill_fits_the_model(k, frame, chosen)][:3]
    if frame is not None:
        starter_predictions, starter_kills = starter_outcomes_for(frame, chosen, today)
    else:
        starter_predictions, starter_kills = [], []
    if not predictions:
        predictions = [
            MemoPrediction(metric=o.metric, threshold=o.threshold, by=o.by, probability=o.probability, starter=True)
            for o in starter_predictions
        ]
    # Whatever else stops it, one rule must tie it to what it costs.
    limit = next((o for o in starter_kills if _SPEND_WORDS.search(o.metric) or _RUNWAY_WORD.search(o.metric)), None)
    tied_to_cost = any(_SPEND_WORDS.search(k.text()) or _RUNWAY_WORD.search(k.text()) for k in kills)
    if frame is not None and frame.cost_model is not None and kills and limit is not None and not tied_to_cost:
        kills = [*kills[:2], MemoCriterion(metric=limit.metric, threshold=limit.threshold, by=limit.by, starter=True)]
    if not kills:
        kills = [MemoCriterion(metric=o.metric, threshold=o.threshold, by=o.by, starter=True) for o in starter_kills]
    return predictions, kills


def _reject_line(option: MemoOption, chosen: str, frame: DecisionFrame | None) -> str:
    """The model's reason stands, unless a cheaper option gets one that says nothing about why it lost."""
    if option.note and (not _costs_no_more(option.name, chosen, frame) or _STATES_A_REASON.search(option.note)):
        return option.note
    return _why_not(option.name, chosen, frame)


def with_required_fields(
    draft: MemoDraft, message: str, frame: DecisionFrame | None = None, today: dt.date | None = None
) -> MemoDraft:
    """Exactly one chosen option, every other one rejected, and a Decision that matches: all written by code."""
    today = today or dt.date.today()
    title = _MEMO_PREFIX.sub("", draft.title.strip())
    costed = bool(frame is not None and frame.options)
    names = [o.name for o in frame.options] if frame is not None and costed else []
    if not names:
        names = list(dict.fromkeys(o.name.strip() for o in draft.options if o.name.strip())) or list(GENERIC_OPTIONS)
    if frame is not None and costed:
        default = frame.default_option
    else:
        default = next((n for n in names if "pilot" in n.lower()), names[0])
    chosen, model_chose = _chosen_option(draft, names, default)
    why = draft.why_chosen.strip() or draft.decision.strip()
    _, score = _best_option(why, [n for n in names if n != chosen])
    # A reason that argues for another option would contradict the choice, so it does not go in the Decision.
    if score >= 0.6 and _best_option(why, [chosen])[1] < score:
        why = ""
    if not model_chose:
        why = "Chosen by rule as the easiest option to undo: the draft named no option from the list."
    decision = f"Proposed: {chosen}. {why}".strip() + " You have not decided yet: this is a recommendation."
    options = [MemoOption(name=n, note=_option_reason(n, draft, frame)) for n in names]
    rejected = [f"{o.name}: {_reject_line(o, chosen, frame)}" for o in options if o.name != chosen]
    predictions, kills = _final_outcomes(draft, frame, chosen, today)
    return draft.model_copy(
        update={
            "title": memo_title(title) if title else memo_title(message),
            "chosen": chosen,
            "why_chosen": why,
            "decision": decision,
            "options": options,
            "rejected": rejected,
            "predictions": predictions,
            "kill_criteria": kills,
        }
    )


_LIST_MARK = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _pull_unbacked(text: str, known: list[Fact], context: str, moved: list[str]) -> str:
    """A figure with no source leaves the text and goes on the list for the founder to confirm.

    Its whole sentence goes, or its whole line in a list: half a risk line would make no sense on its own.
    """
    if not verify_numbers(text, known, context):
        return text
    lines: list[str] = []
    for line in text.splitlines():
        if not verify_numbers(line, known, context):
            lines.append(line)
        elif _LIST_MARK.match(line):
            moved.append(_LIST_MARK.sub("", line).strip())
        else:
            kept: list[str] = []
            for piece in split_sentences(line):
                if piece.strip() and verify_numbers(piece, known, context):
                    moved.append(piece.strip())
                else:
                    kept.append(piece)
            lines.append("".join(kept).strip())
    return "\n".join(line for line in lines if line.strip()).strip()


def without_unbacked_figures(draft: MemoDraft, known: list[Fact], message: str) -> MemoDraft:
    """A memo is kept for years: a figure with no lineage is never stated as fact, and never left as a scar."""
    moved: list[str] = list(draft.open_numbers)

    def clean(text: str) -> str:
        return _pull_unbacked(text, known, message, moved)

    title = draft.title if not verify_numbers(draft.title, known, message) else memo_title(message)
    options = [o.model_copy(update={"note": clean(o.note)}) for o in draft.options]
    decision = clean(draft.decision)
    rejected = [r for r in (clean(x) for x in draft.rejected) if r]
    context = clean(draft.context)
    assumptions = [a for a in (clean(x) for x in draft.assumptions) if a]
    targets = [
        f"Target in a forecast: {p.text()}"
        for p in draft.predictions
        if not p.starter and verify_numbers(p.text(), known, message)
    ]
    targets += [
        f"Target in a stop rule: {k.text()}"
        for k in draft.kill_criteria
        if not k.starter and verify_numbers(k.text(), known, message)
    ]
    return draft.model_copy(
        update={
            "title": title,
            "decision": decision,
            "context": context,
            "options": options,
            "rejected": rejected,
            "assumptions": assumptions,
            "open_numbers": list(dict.fromkeys([*moved, *targets])),
        }
    )


_OUR_WORDS = {"we": "you", "We": "You", "us": "you", "our": "your", "Our": "Your", "ours": "yours", "Ours": "Yours"}
_OUR_WORD = re.compile(r"\b(?:we|We|us|our|Our|ours|Ours)\b")  # lower case only for "us": "US" is a place
_SAYS_CHECKED = re.compile(
    r"\b(?:is|are|has been|have been|was|were)\s+(?:\w+\s+)?(?:confirmed|verified|validated|assessed|evaluated)\b", re.I
)


def in_your_words(draft: MemoDraft, frame: DecisionFrame | None, records: list[Any]) -> MemoDraft:
    """A memo speaks to the founder too, and never reports a goal or a proposal as a decision.

    Nor does it contradict the goal check, or list as an assumption that the assumptions were checked. Seen live:
    "aligns with the goal of extending runway" beside -0.21 months, and "Cost model assumptions are confirmed."
    """

    def say(text: str) -> str:
        return guarded(_OUR_WORD.sub(lambda m: _OUR_WORDS[m.group()], text), frame, records, chosen=draft.chosen)

    def reasons(text: str, if_blank: str = "See the Goal check in this memo.") -> str:
        """A section is never left blank because its only sentence was the contradiction."""
        return say(without_contradictions(text, frame, draft.chosen)) or (if_blank if text.strip() else "")

    def rejected_line(line: str) -> str:
        name = line.split(":", 1)[0].strip()
        return reasons(line, f"{name}: not proposed. See the Goal check in this memo.")

    return draft.model_copy(
        update={
            "title": _OUR_WORD.sub(lambda m: _OUR_WORDS[m.group()], draft.title),
            "context": reasons(draft.context),
            "why_chosen": reasons(draft.why_chosen),
            "decision": reasons(draft.decision, f"Proposed: {draft.chosen}."),
            "options": [o.model_copy(update={"note": reasons(o.note)}) for o in draft.options],
            "rejected": [rejected_line(r) for r in draft.rejected],
            "assumptions": [say(a) for a in draft.assumptions if not _SAYS_CHECKED.search(a)],
        }
    )


def _bullets(items: list[str], blank: str = "None recorded.") -> str:
    return "\n".join(f"- {item}" for item in items) if items else blank


def _metric_lines(upstream: list[Any], frame: DecisionFrame | None) -> list[str]:
    """One plain sentence per figure that bears on this decision, with where it came from in a few words."""
    lines: list[str] = []
    seen: set[str] = set()
    if frame is not None:
        for figure in (f for f in frame.baseline if relevant_metric(frame, f.metric)):
            seen.add(figure.metric)
            lines.append(figure.line())
    for result in upstream:
        for artifact in result.artifacts:
            if artifact.kind != "metric_card" or artifact.data.get("metric") in seen:
                continue
            data = artifact.data
            metric = str(data.get("metric"))
            if not relevant_metric(frame, metric) or data.get("value") is None:
                continue
            seen.add(metric)
            figure = BaselineFigure(
                metric=metric,
                label=str(data.get("label")),
                value=float(data["value"]),
                unit=str(data.get("unit")),
                as_of=str(data.get("as_of")),
                sources=list(artifact.lineage[0].source_files) if artifact.lineage else [],
            )
            lines.append(figure.line())
        if result.decision_impact is not None:
            sentence = result.decision_impact.sentence()
            if sentence not in seen:
                seen.add(sentence)
                files = ", ".join(next(iter(result.lineage)).source_files) if result.lineage else ""
                lines.append(f"{sentence} (Computed by the scenario routine{' from ' + files if files else ''}.)")
    return lines


def _cost_section(frame: DecisionFrame | None) -> str:
    model = frame.cost_model if frame is not None else None
    if model is None:
        return "Not modelled: no figures are available for this decision yet."
    lines = [model.item_line(item) for item in model.items]
    lines += [model.case_line(case) for case in model.cases]
    lines.append(model.scope_note)
    source = ", ".join(model.sources)
    lines.append(
        f"Runway effects come from the scenario routine{' over ' + source if source else ''}, as of {model.as_of}. "
        "Projected runway includes growth assumptions, so it differs from the runway on actual burn."
    )
    return _bullets(lines)


def _option_lines(draft: MemoDraft, frame: DecisionFrame | None) -> list[str]:
    costs = {o.name: o for o in frame.options} if frame is not None else {}
    lines = []
    for option in draft.options:
        known = costs.get(option.name)
        line = known.line(frame.currency) if known is not None and frame is not None else option.name
        if option.note and known is not None:
            # The model often copies the note code already wrote into the line.
            if option.note.strip(" .").casefold() not in line.casefold():
                line = f"{line} {option.note}"
        elif option.note:
            line = f"{line}: {option.note}"
        lines.append(f"{line} **(proposed)**" if option.name == draft.chosen else line)
    return lines


def _assumption_lines(draft: MemoDraft, frame: DecisionFrame | None) -> list[str]:
    lines = []
    if frame is not None and frame.assumption_count:
        lines.append(
            f"The cost model above rests on {frame.assumption_count} placeholder inputs, not quotes or market data "
            f"({ASSUMPTION_LABEL}). Tell me the real figures and I re-run it."
        )
    return lines + draft.assumptions


def _goal_lines(frame: DecisionFrame | None, chosen: str = "") -> list[str]:
    if frame is None:
        return []
    lines = [g.sentence for g in frame.goals]
    option = next((o for o in frame.options if o.name == chosen), None)
    if lines and option is not None and not option.is_full and option.runway_change_months is not None:
        lines.insert(
            0,
            f"The proposed option, {chosen}, changes projected runway by {option.runway_change_months:+.2f} months. "
            "The lines below use the base case of the full model.",
        )
    return lines


def render_body(draft: MemoDraft, upstream: list[Any], frame: DecisionFrame | None = None) -> str:
    moved: list[str] = list(draft.open_numbers)
    findings = []
    for r in upstream:
        if r.status != "done" or not r.text:
            continue
        before = len(moved)
        text = _pull_unbacked(r.text, r.known_facts, r.brief, moved)
        moved[before:] = [f"{r.name}: {line}" for line in moved[before:]]
        if text:
            findings.append(f"**{r.name}{'' if r.verified else ' (not verified)'}:** {_one_line(text)}")
    predictions = [p.line() for p in draft.predictions]
    return "\n\n".join(
        [
            f"# {draft.title}",
            f"## Decision\n{draft.decision}",
            f"## Context\n{draft.context or 'None recorded.'}",
            f"## Goal check\n{_bullets(_goal_lines(frame, draft.chosen), 'No goals found in profile/company.md.')}",
            f"## Cost model\n{_cost_section(frame)}",
            f"## Options\n{_bullets(_option_lines(draft, frame))}",
            f"## Rejected alternatives\n{_bullets(draft.rejected)}",
            f"## Assumptions\n{_bullets(_assumption_lines(draft, frame))}",
            f"## Open numbers to confirm\n{_bullets(list(dict.fromkeys(moved)), 'None.')}",
            f"## Metrics\n{_bullets(_metric_lines(upstream, frame), 'No metrics were computed for this decision.')}",
            f"## Predictions\n{_bullets(predictions)}",
            f"## Kill criteria\n{_bullets([k.line() for k in draft.kill_criteria])}",
            f"## Team findings\n{_bullets(findings)}",
        ]
    )


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def write_memo(
    ctx: Any,
    draft: MemoDraft,
    upstream: list[Any],
    *,
    verified: bool,
    agent_id: str,
    frame: DecisionFrame | None = None,
    today: dt.date | None = None,
) -> tuple[MemoRef, Artifact]:
    """Writes `decisions/YYYY-MM-DD-<slug>.md` as `proposed` (the founder decides) and stores the predictions."""
    if ctx.vault is None:
        raise ValueError("the vault is not available, so the memo could not be written")
    today = today or dt.date.today()
    review = (today + dt.timedelta(days=REVIEW_AFTER_DAYS)).isoformat()
    predictions = [p.line() for p in draft.predictions]
    kills = [k.line() for k in draft.kill_criteria]
    # Placeholder figures are never "verified", however well the prose checks out.
    assumptions = frame.assumption_count if frame is not None else 0
    is_verified = verified and not assumptions
    frontmatter = {
        "title": draft.title,
        "written": today.isoformat(),  # not `date`: the vault reads that as the day it was decided
        "status": "proposed",
        "decision_type": frame.type if frame is not None else "other",
        "proposed_option": draft.chosen,
        "review_date": review,
        "predictions": predictions,
        "kill_criteria": kills,
        "assumptions_to_confirm": assumptions,
        "verified": is_verified,
        "tags": ["decision"],
    }
    body = render_body(draft, upstream, frame)
    base = f"decisions/{today.isoformat()}-{memo_slug(draft.title)}"
    written = ""
    for attempt in range(1, 100):
        path = f"{base}.md" if attempt == 1 else f"{base}-{attempt}.md"
        try:
            written = ctx.vault.vault.write_note(path, frontmatter=frontmatter, body=body, create_only=True)
            break
        except NoteExistsError:
            continue
    if not written:
        raise ValueError(f"could not find a free file name for {base}")
    ctx.vault.apply_changes({written})
    if ctx.finance is not None:
        # A starter is arithmetic on the cost model, not a forecast anyone made, so it is not scored.
        for prediction in [p for p in draft.predictions if not p.starter]:
            ctx.finance.calibration.add(
                PredictionIn(
                    statement=prediction.text()[:500],
                    probability=prediction.probability,
                    owner="memo_writer",
                    decision=written,
                    resolve_by=outcome_date(prediction.text(), today) or dt.date.fromisoformat(review),
                )
            )
    ref = MemoRef(
        path=written,
        title=draft.title,
        status="proposed",
        review_date=review,
        chosen=draft.chosen,
        decision_type=frame.type if frame is not None else "other",
        predictions=predictions,
        kill_criteria=kills,
        open_numbers=draft.open_numbers,
        assumptions_to_confirm=assumptions,
        verified=is_verified,
    )
    artifact = Artifact(
        id=f"art_{uuid.uuid4().hex[:10]}",
        kind="decision_memo",
        title=draft.title,
        agent_id=agent_id,
        data={**ref.model_dump(), "markdown": body},
        lineage=[lin for r in upstream for lin in r.lineage],
    )
    return ref, artifact
