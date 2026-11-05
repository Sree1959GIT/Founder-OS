"""The privacy filter on every cloud payload (PRD R2, F3): raw financial rows never leave the PC.

Deterministic, no model involved, and applied by the router to every message it sends to a cloud provider, whichever
agent wrote it:

- **Tool results** keep summarised metrics, with a lineage id instead of the SQL, source rows and intermediate inputs.
  Query rows and any other table of numbers are replaced by a row count.
- **Text** (prompts, the founder's message, findings, vault passages) loses lines that look like data rows, and email
  addresses. A sentence containing a number stays: a summarised figure is what cloud agents are meant to see.
- **Names** of customers, people and companies, inside any free text, become stable pseudonyms ("Customer_017"), from a
  `NameIndex` over the customers table and the vault. The router puts the real names back in the reply, on the PC. If
  the names cannot be read, the call stays local: privacy fails closed.

The filter is deliberately greedy about shapes, not meanings. A person's name that is in neither source is only caught
after a title ("Dr Rao"). Telling apart sensitive prose by what it says is a job for a decision model (F7).
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from app.llm.base import Message

ROWS_REMOVED = "[{n} data rows removed by the privacy filter]"
EMAIL_REMOVED = "[email removed]"
RESULT_WITHHELD = "This tool result was too long to filter, so it was not sent. Ask for less."
# Fields of tool results that hold raw data or how to find it.
_RAW_KEYS = frozenset({"rows", "sql", "source_rows", "source_files", "sources", "inputs", "points"})
# Lists of numbers that are summaries by construction, not data rows.
_SUMMARY_LISTS = frozenset({"metrics", "assumptions", "options", "owners", "decisions", "results"})
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_NUMERIC_CELL = re.compile(r"^[\s$€£₹(-]*\d[\d.]*\s*[kKmMbB]?\s*[%)]?\s*$")
_WORD = re.compile(r"[A-Za-z]{2,}")
_MAX_WORDS_IN_A_ROW = 8


@dataclass
class FilterReport:
    rows_removed: int = 0
    emails_removed: int = 0
    names_replaced: int = 0

    @property
    def total(self) -> int:
        return self.rows_removed + self.emails_removed + self.names_replaced


class NamesUnavailable(Exception):
    """The names could not be read, so a cloud payload cannot be cleaned: the call must stay local."""


NameSource = Callable[[], Iterable[tuple[str, str]]]  # yields (kind, name); kind is customer | person | company
_PSEUDONYM_WORD = {"customer": "Customer", "person": "Person", "company": "Company"}
_PSEUDONYM = re.compile(r"\b(?:Customer|Person|Company)_\d{3}\b")
_PARTIAL_PSEUDONYM = re.compile(
    r"(?:C|Cu|Cus|Cust|Custo|Custom|Custome|Customer|P|Pe|Per|Pers|Perso|Person|Co|Com|Comp|Compa|Compan|Company)(?:_\d{0,2})?$|(?:Customer|Person|Company)_\d{0,2}$"
)
_TITLED_PERSON = re.compile(r"\b(?:Mr|Mrs|Ms|Mx|Dr|Prof)\.?\s+[A-Z][a-z]+(?:[ -][A-Z][a-z]+)?")
# A short form stands for its full name only when it could not be an ordinary word in a business note.
_COMMON_WORDS = frozenset(
    {
        *("global", "first", "growth", "starter", "enterprise", "general", "national", "united", "american", "central"),
        *("north", "south", "east", "west", "new", "the", "blue", "green", "red", "black", "white", "open", "data"),
        *("digital", "cloud", "logic", "media", "systems", "group", "partners", "capital", "software", "labs", "tech"),
        *("analytics", "solutions", "services", "consulting", "logistics", "health", "energy", "finance", "foods"),
        *("market", "sales", "customer", "company", "person", "summit", "bright", "prime", "smart", "apex", "will"),
        *("mark", "may", "june", "april", "august", "grace", "hope", "faith", "rose", "dawn", "bill", "frank"),
    }
)


class NameIndex:
    """The names that must not leave the PC, read from `sources` and cached briefly.

    A pseudonym stays the same for the life of the process, so a model can reason across messages and the reply can be
    mapped back. Full names match in any case; a short form ("Ironcrest" for "Ironcrest Media") matches as capitalised,
    and only when it is unique and not an ordinary word.
    """

    def __init__(self, sources: list[NameSource], ttl_s: float = 60.0) -> None:
        self.sources = sources
        self.ttl_s = ttl_s
        self._loaded_at: float | None = None
        self._pseudonyms: dict[str, str] = {}  # casefolded name -> pseudonym
        self._real: dict[str, str] = {}  # pseudonym -> the name as written in the source
        self._counts: dict[str, int] = {}
        self._full: re.Pattern[str] | None = None
        self._short: re.Pattern[str] | None = None
        self._short_to_pseudonym: dict[str, str] = {}

    def _pseudonym_for(self, kind: str, name: str) -> str:
        key = name.casefold()
        if key not in self._pseudonyms:
            word = _PSEUDONYM_WORD.get(kind, "Company")
            self._counts[word] = self._counts.get(word, 0) + 1
            pseudonym = f"{word}_{self._counts[word]:03d}"
            self._pseudonyms[key] = pseudonym
            self._real[pseudonym] = name
        return self._pseudonyms[key]

    def _short_forms(self, kind: str, name: str) -> list[str]:
        words = name.split()
        if len(words) < 2:
            return []
        wanted = words if kind == "person" else words[:1]
        return [w for w in wanted if len(w) >= (3 if kind == "person" else 5) and w.lower() not in _COMMON_WORDS]

    def refresh(self) -> None:
        """Raises `NamesUnavailable` if a source fails: an unclean payload must not go out."""
        now = time.monotonic()
        if self._loaded_at is not None and now - self._loaded_at < self.ttl_s:
            return
        names: list[tuple[str, str]] = []
        try:
            for source in self.sources:
                names.extend((kind, str(name).strip()) for kind, name in source() if str(name or "").strip())
        except Exception as exc:
            raise NamesUnavailable(f"{type(exc).__name__}: {exc}") from exc
        seen_short: dict[str, str | None] = {}
        full = sorted({name for _, name in names}, key=len, reverse=True)
        for kind, name in names:
            pseudonym = self._pseudonym_for(kind, name)
            for short in self._short_forms(kind, name):
                if short.casefold() not in {n.casefold() for n in full}:
                    seen_short[short] = pseudonym if seen_short.get(short, pseudonym) == pseudonym else None
        self._short_to_pseudonym = {s: p for s, p in seen_short.items() if p is not None}
        self._full = _alternation(full, re.I) if full else None
        self._short = _alternation(sorted(self._short_to_pseudonym, key=len, reverse=True), 0) or None
        self._loaded_at = now

    def scrub(self, text: str, report: FilterReport) -> str:
        def count(replacement: str) -> str:
            report.names_replaced += 1
            return replacement

        if self._full is not None:
            text = self._full.sub(lambda m: count(self._pseudonyms[m.group().casefold()]), text)
        if self._short is not None:
            text = self._short.sub(lambda m: count(self._short_to_pseudonym[m.group()]), text)
        return _TITLED_PERSON.sub(lambda m: count(self._pseudonym_for("person", m.group())), text)

    def restore(self, text: str) -> str:
        """The reply, with the real names back. It only ever runs on the PC."""
        return _PSEUDONYM.sub(lambda m: self._real.get(m.group(), m.group()), text)

    def restore_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.restore(value)
        if isinstance(value, dict):
            return {k: self.restore_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.restore_value(v) for v in value]
        return value


def _alternation(names: list[str], flags: int) -> re.Pattern[str] | None:
    if not names:
        return None
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", flags)


class StreamRestorer:
    """Real names back in a stream, holding back a tail that could still become a pseudonym."""

    def __init__(self, names: NameIndex | None) -> None:
        self.names = names
        self._held = ""

    def feed(self, delta: str) -> str:
        if self.names is None:
            return delta
        text = self._held + delta
        partial = _PARTIAL_PSEUDONYM.search(text)
        cut = partial.start() if partial else len(text)
        self._held = text[cut:]
        return self.names.restore(text[:cut])

    def flush(self) -> str:
        text, self._held = self._held, ""
        return self.names.restore(text) if self.names is not None else text


def _looks_like_a_row(line: str) -> bool:
    """A delimited line with a number standing alone in a cell: "Acme, 12000" or "| Acme | $1.2M |".

    Strict on purpose: a filter that lets a data row through is worse than one that drops a list of numbers. "In Q3, 12
    customers left" stays, because no cell is only a number.
    """
    cleaned = _THOUSANDS.sub("", line.strip().strip("|"))
    separator = next((s for s in ("|", "\t", ",", ";") if s in cleaned), None)
    if separator is None:
        return False
    cells = cleaned.split(separator)
    if len(cells) < 2 or len(_WORD.findall(cleaned)) > _MAX_WORDS_IN_A_ROW:
        return False
    return any(_NUMERIC_CELL.match(cell) for cell in cells)


def filter_text(text: str, report: FilterReport | None = None, names: NameIndex | None = None) -> str:
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
    return names.scrub(cleaned, report) if names is not None else cleaned


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


def _scrub(value: Any, report: FilterReport, key: str = "", names: NameIndex | None = None) -> Any:
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
                out[name] = _scrub(item, report, name, names)
        return out
    if isinstance(value, list):
        if key not in _SUMMARY_LISTS and _is_table(value):
            report.rows_removed += len(value)
            return ROWS_REMOVED.format(n=len(value))
        return [_scrub(item, report, key, names) for item in value]
    if isinstance(value, str):
        return filter_text(value, report, names)
    return value


def filter_tool_result(content: str, report: FilterReport | None = None, names: NameIndex | None = None) -> str:
    report = report if report is not None else FilterReport()
    try:
        data = json.loads(content)
    except ValueError:  # cut at MAX_TOOL_CHARS, or not JSON: its fields cannot be judged, so it does not leave the PC
        report.rows_removed += 1
        return json.dumps({"withheld": RESULT_WITHHELD})
    return json.dumps(_scrub(data, report, "", names), ensure_ascii=False, default=str)


def filter_messages(messages: list[Message], names: NameIndex | None = None) -> tuple[list[Message], FilterReport]:
    """What a cloud provider may see of `messages`. The originals stay as they are for the local fallback."""
    if names is not None:
        names.refresh()
    report = FilterReport()
    filtered = []
    for m in messages:
        update: dict[str, Any] = {
            "content": (
                filter_tool_result(m.content, report, names)
                if m.role == "tool"
                else filter_text(m.content, report, names)
            )
        }
        if names is not None and m.tool_calls:  # an earlier search may have put a customer's name in its arguments
            update["tool_calls"] = [
                c.model_copy(update={"arguments": _scrub(c.arguments, report, "", names)}) for c in m.tool_calls
            ]
        filtered.append(m.model_copy(update=update))
    return filtered, report
