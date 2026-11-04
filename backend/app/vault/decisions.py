"""Past-decision records: the structured facts of a note under `decisions/` (or tagged `decision`).

A record is built by code from the note's frontmatter and body, so the status, dates, prediction and kill criteria
reach the agents exactly as written, whichever passage a search happened to return. Kill criteria come from the
frontmatter (`kill_criteria`, `kill_criterion`), a `Kill criteria` heading, or a sentence naming a kill criterion.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.vault.parsers import ParsedDocument, Section, as_str_list, markdown_sections

DECISIONS_FOLDER = "decisions/"
RECORD_HEADING = "Record"
# Frontmatter that says nothing beyond the note's name, so it does not earn a section of its own.
_NAME_ONLY_FIELDS = frozenset({"title", "aliases"})
_DECIDED_FIELDS = ("decided", "decision_date", "decided_on", "date")
_REVIEW_FIELDS = ("review_date", "review_by", "review")
_KILL_FIELDS = ("kill_criteria", "kill_criterion")
_PREDICTION_FIELDS = ("predictions", "prediction")

_ISO_PREFIX_RE = re.compile(r"\d{4}-\d{2}(-\d{2})?")
_KILL_HEADING_RE = re.compile(r"kill[ -]criteri(on|a)$", re.I)
_DECISION_HEADING_RE = re.compile(r"^(the )?decision$", re.I)
_KILL_SENTENCE_RE = re.compile(
    r"kill[ -]criteri(?:on|a)\b(?:\s+(?:is|are))?\s*[^\w\s]?\s*(?P<text>.+?)(?:(?<=[.!?])\s|$)", re.I
)
_FIRST_SENTENCE_RE = re.compile(r"(.+?[.!?])(?:\s|$)")
_WIKILINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
_HEADING_LINE_RE = re.compile(r"(?m)^#{1,6}[ \t].*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


class DecisionRecord(BaseModel):
    path: str
    title: str
    status: str = Field(default="unknown", description="As written in the note, e.g. decided, proposed, reversed")
    decided: str | None = Field(default=None, description="The decision date as written")
    review_date: str | None = None
    review_state: Literal["upcoming", "overdue", "unknown"] = "unknown"
    decision: str = Field(default="", description="What was decided: the first sentence of the Decision section")
    predictions: list[str] = Field(default_factory=list)
    kill_criteria: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    def with_review_state(self, today: dt.date) -> DecisionRecord:
        """Computed in code from today's date, so the model never does date arithmetic."""
        try:
            review = dt.date.fromisoformat(str(self.review_date)[:10])
        except ValueError:
            return self.model_copy(update={"review_state": "unknown"})
        return self.model_copy(update={"review_state": "overdue" if review < today else "upcoming"})

    def for_model(self) -> dict[str, Any]:
        return self.model_dump()

    def summary(self) -> str:
        """One line for the model, the Advisor's findings and the answer itself. Only what the note says."""
        parts = [f"status {self.status}"]
        if self.decided:
            parts.append(f"decided {self.decided}")
        if self.decision:
            parts.append(f"decision: {self.decision.rstrip('.')}")
        if self.kill_criteria and not all(c.rstrip(".") in self.decision for c in self.kill_criteria):
            parts.append(f"kill criteria: {'; '.join(c.rstrip('.') for c in self.kill_criteria)}")
        if self.predictions:
            parts.append(f"prediction: {'; '.join(self.predictions)}")
        if self.review_date:
            parts.append(f"review date {self.review_date}" + (" (overdue)" if self.review_state == "overdue" else ""))
        return f'"{self.title}" [{self.path}]: ' + ", ".join(parts) + "."

    def follow_up_question(self) -> str:
        if not self.kill_criteria:
            return f"What has changed since this was decided on {self.decided or 'that date'}?"
        if self.review_date and self.review_state == "overdue":
            return f"The {self.review_date} review date has passed: did it meet the kill criteria?"
        if self.review_date:
            return f"Is it on track to pass the kill criteria before the {self.review_date} review?"
        return "Is it on track to pass the kill criteria?"


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_text(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(_text(v) for v in value)
    return str(value).strip()


def frontmatter_section(parsed: ParsedDocument) -> Section | None:
    """A note's frontmatter as searchable text, so its fields reach the chunks, the embeddings and the answer.

    Notes with nothing but a name and tags get no section: it would only add a near-empty chunk to every search.
    """
    fields = {k: v for k, v in parsed.frontmatter.items() if k not in _NAME_ONLY_FIELDS and v not in (None, "", [])}
    if not set(fields) - {"tags"}:
        return None
    lines = [f"{key.replace('_', ' ').capitalize()}: {_text(value)}" for key, value in fields.items()]
    return Section(heading=RECORD_HEADING, text="\n".join(lines))


def is_decision_note(path: str, frontmatter: dict[str, Any]) -> bool:
    if path.startswith(DECISIONS_FOLDER):
        return True
    return "decision" in {tag.lower() for tag in as_str_list(frontmatter.get("tags"))}


def _first_field(frontmatter: dict[str, Any], names: tuple[str, ...]) -> Any:
    return next((frontmatter[n] for n in names if frontmatter.get(n) not in (None, "", [])), None)


def _as_items(value: Any) -> list[str]:
    """A frontmatter value as a list of statements. A single string stays whole: it may contain commas."""
    if value is None:
        return []
    return [_text(item) for item in value] if isinstance(value, list) else [_text(value)]


def _prose(text: str) -> str:
    """Section text as one line: no heading lines, wiki-links reduced to their display text."""
    without_headings = _HEADING_LINE_RE.sub(" ", text)
    linked = _WIKILINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), without_headings)
    return re.sub(r"\s+", " ", linked).strip()


def _last_heading(section: Section) -> str:
    return section.heading.rsplit(" > ", 1)[-1].strip()


def _kill_criteria(frontmatter: dict[str, Any], sections: list[Section]) -> list[str]:
    declared = _first_field(frontmatter, _KILL_FIELDS)
    if declared is not None:
        return _as_items(declared)
    for section in sections:
        if _KILL_HEADING_RE.search(_last_heading(section)):
            body = _HEADING_LINE_RE.sub("", section.text)
            items = [_prose(_BULLET_RE.sub("", line)) for line in body.splitlines() if line.strip()]
            if items:
                return items
    found: list[str] = []
    for section in sections:
        for match in _KILL_SENTENCE_RE.finditer(_prose(section.text)):
            sentence = match.group("text").strip().rstrip(".")
            if sentence and sentence not in found:
                found.append(sentence)
    return found


def _decision_sentence(sections: list[Section]) -> str:
    for section in sections:
        if _DECISION_HEADING_RE.match(_last_heading(section)):
            prose = _prose(section.text)
            first = _FIRST_SENTENCE_RE.match(prose)
            return first.group(1) if first else prose
    return ""


def build_record(path: str, parsed: ParsedDocument) -> DecisionRecord | None:
    """The record of a decision note, or None for any other file."""
    if parsed.kind != "markdown" or not is_decision_note(path, parsed.frontmatter):
        return None
    frontmatter = parsed.frontmatter
    sections, _ = markdown_sections(parsed.body)
    decided = _first_field(frontmatter, _DECIDED_FIELDS)
    if decided is None:  # `decisions/2026-09-hire-two-sdrs.md`: the file name is the convention for the date
        from_name = _ISO_PREFIX_RE.match(path.rsplit("/", 1)[-1])
        decided = from_name.group(0) if from_name else None
    review = _first_field(frontmatter, _REVIEW_FIELDS)
    return DecisionRecord(
        path=path,
        title=parsed.title,
        status=_text(frontmatter.get("status") or "unknown"),
        decided=None if decided is None else _text(decided),
        review_date=None if review is None else _text(review),
        decision=_decision_sentence(sections),
        predictions=_as_items(_first_field(frontmatter, _PREDICTION_FIELDS)),
        kill_criteria=_kill_criteria(frontmatter, sections),
        tags=as_str_list(frontmatter.get("tags")),
    )
