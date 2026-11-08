"""What the answer's badge says, in one of three states, from the run's audit trail.

- `verified`: every check passed and nothing rests on a placeholder.
- `assumptions`: every figure checked out, and the answer rests on labelled placeholder inputs only. Placeholders are
  never "verified", but they are not a failure either: the founder confirms them.
- `not_verified`: some check failed. `reasons` say which kind, in words that never name a removed figure or source.

The issues themselves are the audit trail (they may name a removed figure), so the founder sees only these reasons.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.verifier import extract_figures

ASSUMPTION_ISSUE = re.compile(r"^this rests on \d+ assumptions? to confirm$")
_REMOVED = re.compile(r"removed: (?:unsupported source|beyond the projection)(?: \((\d+)\))?")

_KINDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"number without lineage"), "A figure had no source in your data, so it was checked as unsupported."),
    (re.compile(r"wrong meaning"), "A figure was used with the wrong meaning; that sentence was rewritten by code."),
    (re.compile(r"was not returned by a search|cites no vault source"), "A cited note was not found in your vault."),
    (re.compile(r"retry failed|failed|cancelled"), "An agent did not finish."),
]


class Verification(BaseModel):
    state: Literal["verified", "assumptions", "not_verified"]
    reasons: list[str] = Field(default_factory=list, description="Why not verified, naming no removed figure")
    assumptions: list[str] = Field(default_factory=list, description="The placeholder inputs to confirm")
    removed_claims: int = Field(0, description="Sentences taken out because nothing backed them")
    sources: list[str] = Field(default_factory=list, description="Notes and data files the answer rests on")


def removed_count(issues: Iterable[str]) -> int:
    total = 0
    for issue in issues:
        for match in _REMOVED.finditer(issue):
            total += int(match.group(1) or 1)
    return total


def _reason(issue: str) -> str | None:
    if _REMOVED.search(issue):
        return None  # counted in removed_claims
    text = issue.split(": ", 1)[1] if re.match(r"^[\w &'-]{1,40}: ", issue) else issue
    for pattern, words in _KINDS:
        if pattern.search(text):
            return words
    if extract_figures(text) or "/" in text or "[" in text:
        return "Another check did not pass."
    return text[:1].upper() + text[1:].rstrip(".") + "."


def verification(
    issues: list[str],
    all_done: bool,
    assumptions: list[str],
    sources: list[str],
    resolved: list[str] | None = None,
) -> Verification:
    """`resolved`: audit lines about text the source check took out, so the founder never saw it. Those claims are
    counted (`removed_claims`, the chip by the badge) but do not make the shown figures "not verified"."""
    done = set(resolved or [])
    core = [i for i in issues if not ASSUMPTION_ISSUE.match(i)]
    removed = removed_count(core)
    failing = [i for i in core if i not in done and not _REMOVED.search(i)]
    reasons = list(dict.fromkeys(r for r in (_reason(i) for i in failing) if r))
    if not all_done and "An agent did not finish." not in reasons:
        reasons.append("An agent did not finish.")
    if removed and (failing or not all_done):
        reasons.append(f"{removed} unsupported claim{'s' if removed != 1 else ''} removed.")
    if failing or not all_done:
        state: Literal["verified", "assumptions", "not_verified"] = "not_verified"
    else:
        state = "assumptions" if assumptions else "verified"
    return Verification(state=state, reasons=reasons, assumptions=assumptions, removed_claims=removed, sources=sources)
