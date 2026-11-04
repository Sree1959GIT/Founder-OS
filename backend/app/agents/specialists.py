"""What the specialist agents (PRD F3) need beyond the shared runtime: team cues, rule answers, risks and the memo.

Everything here is code, not model judgement: which types a message calls for, the risk register built from the
Devil's Advocate's lines, and the memo file (path, review date, metrics with lineage, predictions in the calibration
store). The model supplies only the prose and its forecasts, and those go through the Verifier like any other answer.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.agents.events import Artifact
from app.agents.verifier import Fact, extract_figures, verify_numbers
from app.engine.calibration import PredictionIn
from app.vault.manager import NoteExistsError

REVIEW_AFTER_DAYS = 30
MAX_TEAM = 8
REGULATORY_NOTE = "This flags points to verify with a qualified adviser; it is not legal or tax advice."
SCOUT_LOCAL_NOTE = "This comes from your vault only: cloud is off, so no web research was done."
PLACEHOLDER_PREDICTION = "This decision meets its goal by the review date (placeholder: replace it with your own)."
PLACEHOLDER_KILL = "None set yet: decide what result by the review date would make you stop."
FIGURE_REMOVED = "[figure removed: no lineage]"

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
    ("people_ops", re.compile(r"\b(capacity|key[- ]person|execution plan|team structure|org chart|reorg\w*)\b", re.I)),
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
    "regulatory_tax": "Written without the language model, so nothing specific was checked.",
    "market_scout": "Written without the language model, and nothing relevant was found in the vault.",
}


def team_for_message(message: str) -> list[str]:
    """The specialist types a message asks for, in the order the table lists them."""
    return [agent_type for agent_type, cue in _CUES if cue.search(message)]


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
class MemoPrediction(BaseModel):
    statement: str
    probability: float

    @field_validator("probability", mode="before")
    @classmethod
    def _as_fraction(cls, value: Any) -> float:
        """A model can write 70 or "70%". A forecast is never certain, so it stays inside 1 % to 99 %."""
        number = float(str(value).strip().rstrip("%"))
        number = number / 100 if number > 1 else number
        return min(0.99, max(0.01, number))


class MemoDraft(BaseModel):
    """The prose of a memo, from the model. Code adds the path, dates, metrics and lineage."""

    title: str = ""
    decision: str = ""
    context: str = ""
    options: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    predictions: list[MemoPrediction] = Field(default_factory=list)
    kill_criteria: list[str] = Field(default_factory=list)

    def prose(self) -> str:
        return "\n".join(
            [
                self.title,
                self.decision,
                self.context,
                *self.options,
                *self.rejected,
                *self.assumptions,
                *(p.statement for p in self.predictions),
                *self.kill_criteria,
            ]
        )


MEMO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "decision": {"type": "string", "description": "What is being decided or recommended, one sentence"},
        "context": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "rejected": {"type": "array", "items": {"type": "string"}, "description": "Option, then why it was rejected"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "predictions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string", "description": "Checkable by the review date"},
                    "probability": {"type": "number", "description": "0 to 1"},
                },
                "required": ["statement", "probability"],
            },
        },
        "kill_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "decision", "context", "options", "assumptions", "predictions", "kill_criteria"],
}


class MemoRef(BaseModel):
    path: str
    title: str
    status: str
    review_date: str
    predictions: list[str]
    kill_criteria: list[str]
    verified: bool


def rule_draft(message: str) -> MemoDraft:
    """No model: a memo that records the question and says plainly what the founder still has to fill in."""
    return MemoDraft(
        title=memo_title(message),
        decision=f"Not decided yet: {message}",
        context="Written without the language model, from the team's findings below.",
        options=["Go ahead", "Run a small pilot first", "Do not do this now"],
        assumptions=["None recorded yet: add the ones this depends on."],
    )


def with_required_fields(draft: MemoDraft, message: str) -> MemoDraft:
    """A memo always has a title, a prediction and a kill criterion, even when the model left them out."""
    return draft.model_copy(
        update={
            "title": draft.title.strip() or memo_title(message),
            "decision": draft.decision.strip() or f"Not decided yet: {message}",
            "predictions": draft.predictions or [MemoPrediction(statement=PLACEHOLDER_PREDICTION, probability=0.5)],
            "kill_criteria": [c for c in draft.kill_criteria if c.strip()] or [PLACEHOLDER_KILL],
        }
    )


_ASKS = re.compile(r"^(should|shall|can|could|would|do|does|will)\s+(we|i)\s+", re.I)
_WANTS = re.compile(r"^(i|we)\s+(want|plan|need|would like|are thinking of|am thinking of)\s+(to\s+)?", re.I)
_SLUG_STOP = frozenset({"a", "an", "the", "our", "my", "to", "of", "in", "on", "for"})


def memo_title(message: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", message.strip())[0].rstrip("?.! ")
    first = _WANTS.sub("", _ASKS.sub("", first))
    return (first[:1].upper() + first[1:])[:80] or "Decision"


def memo_slug(title: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in _SLUG_STOP]
    return "-".join(words[:7]) or "decision"


def without_unbacked_figures(draft: MemoDraft, known: list[Fact], message: str) -> MemoDraft:
    """A memo is kept for years: a figure with no lineage is removed from it, not just flagged."""

    def clean(text: str) -> str:
        unbacked = set(verify_numbers(text, known, message))
        for figure in extract_figures(text):
            if figure.text in unbacked:
                text = text.replace(figure.text, FIGURE_REMOVED)
        return text

    return MemoDraft(
        title=clean(draft.title),
        decision=clean(draft.decision),
        context=clean(draft.context),
        options=[clean(x) for x in draft.options],
        rejected=[clean(x) for x in draft.rejected],
        assumptions=[clean(x) for x in draft.assumptions],
        predictions=[p.model_copy(update={"statement": clean(p.statement)}) for p in draft.predictions],
        kill_criteria=[clean(x) for x in draft.kill_criteria],
    )


def _bullets(items: list[str], blank: str = "None recorded.") -> str:
    return "\n".join(f"- {item}" for item in items) if items else blank


def _metric_lines(upstream: list[Any]) -> list[str]:
    """The team's numbers as the routines returned them, each with where it came from."""
    lines: list[str] = []
    seen: set[str] = set()
    for result in upstream:
        for artifact in result.artifacts:
            if artifact.kind == "metric_card" and artifact.data.get("metric") not in seen:
                seen.add(artifact.data.get("metric"))
                lineage = artifact.lineage[0] if artifact.lineage else None
                source = f"; formula: {lineage.formula}; files: {', '.join(lineage.source_files)}" if lineage else ""
                data = artifact.data
                lines.append(
                    f"- {data.get('label')}: {data.get('value')} {data.get('unit')} (as of {data.get('as_of')}{source})"
                )
        if result.decision_impact is not None:
            sentence = result.decision_impact.sentence()
            if sentence not in seen:
                seen.add(sentence)
                lines.append(f"- {sentence} (computed by `run_scenario`)")
    return lines


def render_body(draft: MemoDraft, upstream: list[Any]) -> str:
    findings = [
        f"- **{r.name}{'' if r.verified else ' (not verified)'}:** {_one_line(r.text)}"
        for r in upstream
        if r.status == "done" and r.text
    ]
    predictions = [f"{p.probability:.0%}: {p.statement}" for p in draft.predictions]
    return "\n\n".join(
        [
            f"# {draft.title}",
            f"## Decision\n{draft.decision}",
            f"## Context\n{draft.context or 'None recorded.'}",
            f"## Options\n{_bullets(draft.options)}",
            f"## Rejected alternatives\n{_bullets(draft.rejected)}",
            f"## Assumptions\n{_bullets(draft.assumptions)}",
            f"## Metrics\n{_bullets(_metric_lines(upstream), 'No metrics were computed for this decision.')}",
            f"## Predictions\n{_bullets(predictions)}",
            f"## Kill criteria\n{_bullets(draft.kill_criteria)}",
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
    today: dt.date | None = None,
) -> tuple[MemoRef, Artifact]:
    """Writes `decisions/YYYY-MM-DD-<slug>.md` as `proposed` (the founder decides) and stores the predictions."""
    if ctx.vault is None:
        raise ValueError("the vault is not available, so the memo could not be written")
    today = today or dt.date.today()
    review = (today + dt.timedelta(days=REVIEW_AFTER_DAYS)).isoformat()
    predictions = [f"{p.probability:.0%}: {p.statement}" for p in draft.predictions]
    frontmatter = {
        "title": draft.title,
        "date": today.isoformat(),
        "status": "proposed",
        "review_date": review,
        "predictions": predictions,
        "kill_criteria": draft.kill_criteria,
        "verified": verified,
        "tags": ["decision"],
    }
    body = render_body(draft, upstream)
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
        for prediction in draft.predictions:
            ctx.finance.calibration.add(
                PredictionIn(
                    statement=prediction.statement[:500],
                    probability=prediction.probability,
                    owner="memo_writer",
                    decision=written,
                    resolve_by=dt.date.fromisoformat(review),
                )
            )
    ref = MemoRef(
        path=written,
        title=draft.title,
        status="proposed",
        review_date=review,
        predictions=predictions,
        kill_criteria=draft.kill_criteria,
        verified=verified,
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
