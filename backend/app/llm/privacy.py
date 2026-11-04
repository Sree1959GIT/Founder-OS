"""The privacy filter on every cloud payload (PRD R2, F3): raw financial rows never leave the PC.

Deterministic, no model involved, and applied by the router to every message it sends to a cloud provider, whichever
agent wrote it:

- **Tool results** keep summarised metrics, with a lineage id instead of the SQL, source rows and intermediate inputs.
  Query rows and any other table of numbers are replaced by a row count.
- **Text** (prompts, the founder's message, findings, vault passages) loses lines that look like data rows, and email
  addresses. A sentence containing a number stays: a summarised figure is what cloud agents are meant to see.

The filter is deliberately greedy about shapes, not meanings. Telling apart sensitive prose by what it says is a job
for the decision model (F7), which arrives in M3c.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.llm.base import Message

ROWS_REMOVED = "[{n} data rows removed by the privacy filter]"
EMAIL_REMOVED = "[email removed]"
# Fields of tool results that hold raw data or how to find it.
_RAW_KEYS = frozenset({"rows", "sql", "source_rows", "source_files", "sources", "inputs", "points"})
# Lists of numbers that are summaries by construction, not data rows.
_SUMMARY_LISTS = frozenset({"metrics", "assumptions", "options", "owners", "decisions", "results"})
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_NUMERIC_CELL = re.compile(r"^[\s$€£₹(-]*\d[\d.]*\s*[%)]?\s*$")
_WORD = re.compile(r"[A-Za-z]{2,}")
_MAX_WORDS_IN_A_ROW = 8


@dataclass
class FilterReport:
    rows_removed: int = 0
    emails_removed: int = 0

    @property
    def total(self) -> int:
        return self.rows_removed + self.emails_removed


def _looks_like_a_row(line: str) -> bool:
    """A CSV or table line with at least two numeric cells. "We have 3, 4 or 5 options" has too many words to be one."""
    cleaned = _THOUSANDS.sub("", line.strip().strip("|"))
    separator = next((s for s in ("|", "\t", ",", ";") if s in cleaned), None)
    if separator is None:
        return False
    cells = cleaned.split(separator)
    if len(cells) < 3 or len(_WORD.findall(cleaned)) > _MAX_WORDS_IN_A_ROW:
        return False
    return sum(1 for cell in cells if _NUMERIC_CELL.match(cell)) >= 2


def filter_text(text: str, report: FilterReport | None = None) -> str:
    report = report if report is not None else FilterReport()
    kept: list[str] = []
    pending = 0

    def flush() -> None:
        nonlocal pending
        if pending:
            kept.append(ROWS_REMOVED.format(n=pending))
            report.rows_removed += pending
            pending = 0

    for line in text.split("\n"):
        if _looks_like_a_row(line):
            pending += 1
            continue
        flush()
        kept.append(line)
    flush()
    cleaned, emails = _EMAIL.subn(EMAIL_REMOVED, "\n".join(kept))
    report.emails_removed += emails
    return cleaned


def _is_table(value: list[Any]) -> bool:
    if len(value) < 2:
        return False
    return all(
        isinstance(row, dict | list | tuple)
        and any(isinstance(v, int | float) and not isinstance(v, bool) for v in _cells(row))
        for row in value
    )


def _cells(row: Any) -> list[Any]:
    return list(row.values()) if isinstance(row, dict) else list(row)


def _scrub(value: Any, report: FilterReport, key: str = "") -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for name, item in value.items():
            if name == "lineage" and isinstance(item, dict):
                out["lineage_id"] = f"{value.get('metric', 'value')}@{item.get('period') or value.get('as_of', '')}"
            elif name in _RAW_KEYS:
                if isinstance(item, list) and name in ("rows", "points"):
                    report.rows_removed += len(item)
                    out[f"{name}_removed"] = len(item)
            else:
                out[name] = _scrub(item, report, name)
        return out
    if isinstance(value, list):
        if key not in _SUMMARY_LISTS and _is_table(value):
            report.rows_removed += len(value)
            return ROWS_REMOVED.format(n=len(value))
        return [_scrub(item, report, key) for item in value]
    if isinstance(value, str):
        return filter_text(value, report)
    return value


def filter_tool_result(content: str, report: FilterReport | None = None) -> str:
    report = report if report is not None else FilterReport()
    try:
        data = json.loads(content)
    except ValueError:  # cut at MAX_TOOL_CHARS, or not JSON: all that can be judged is its text
        return filter_text(content, report)
    return json.dumps(_scrub(data, report), ensure_ascii=False, default=str)


def filter_messages(messages: list[Message]) -> tuple[list[Message], FilterReport]:
    """What a cloud provider may see of `messages`. The originals stay as they are for the local fallback."""
    report = FilterReport()
    filtered = [
        m.model_copy(
            update={
                "content": filter_tool_result(m.content, report) if m.role == "tool" else filter_text(m.content, report)
            }
        )
        for m in messages
    ]
    return filtered, report
