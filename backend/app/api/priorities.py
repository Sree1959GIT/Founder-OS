"""`/api/priorities`: the Prioritisation Matrix. Scores are the founder's; the arithmetic is `weighted_scoring`.

The initiatives and weights live in the vault (`notes/priorities.md`), so they can be read and edited in Obsidian too.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import ValidationError

from app.deps import VaultDep
from app.engine.decision_science import Criterion, ScoredOption, ScoringRequest, weighted_scoring
from app.vault.manager import NoteNotFoundError

router = APIRouter(prefix="/priorities", tags=["priorities"])

PRIORITIES_NOTE = "notes/priorities.md"
DEFAULT_CRITERIA = [
    Criterion(name="Cash impact", weight=0.35, axis="value"),
    Criterion(name="Strategic fit", weight=0.25, axis="value"),
    Criterion(name="Team capacity", weight=0.25, axis="feasibility"),
    Criterion(name="Reversibility", weight=0.15, axis="feasibility"),
]


# The engine's names, in the words of the design's four corners.
QUADRANT_WORDS = {"Quick win": "Do now", "Big bet": "Plan carefully", "Fill-in": "Quick wins", "Deprioritise": "Drop"}
# A new initiative starts in the middle, scored nowhere yet: it is not "Do now" (founder review 31).
UNSCORED = "Not scored yet"


def _quadrant(option: Any) -> str | None:
    if option.value == 0.5 and option.feasibility == 0.5:
        return UNSCORED
    return QUADRANT_WORDS.get(option.quadrant or "", option.quadrant)


def _body(request: ScoringRequest) -> str:
    result = weighted_scoring(request)
    rows = "\n".join(
        f"| {o.rank} | {o.name} | {o.total:.2f} | {_quadrant(o) or ''} |"
        for o in sorted(result.options, key=lambda x: x.rank)
    )
    return (
        "# Priorities\n\nWritten by the Prioritisation Matrix. Scores are yours; the ranking is computed in code.\n\n"
        f"| Rank | Initiative | Score | Quadrant |\n|---|---|---|---|\n{rows}\n"
    )


def _view(criteria: list[Criterion], options: list[ScoredOption]) -> dict[str, Any]:
    scoring = weighted_scoring(ScoringRequest(criteria=criteria, options=options)) if options else None
    if scoring is not None:
        for option in scoring.options:
            option.quadrant = _quadrant(option)
    return {
        "criteria": [c.model_dump() for c in criteria],
        "options": [o.model_dump() for o in options],
        "scoring": scoring.model_dump() if scoring is not None else None,
        "path": PRIORITIES_NOTE,
    }


@router.get("")
def get_priorities(vault: VaultDep) -> dict[str, Any]:
    try:
        front = vault.vault.read_note(PRIORITIES_NOTE).get("frontmatter") or {}
    except NoteNotFoundError:
        return _view(DEFAULT_CRITERIA, [])
    try:
        criteria = [Criterion(**c) for c in front.get("criteria", [])] or DEFAULT_CRITERIA
        options = [ScoredOption(**o) for o in front.get("options", [])]
        return _view(criteria, options)
    except (TypeError, ValidationError):  # hand-edited into something unreadable: show the defaults, keep the file
        return {**_view(DEFAULT_CRITERIA, []), "warning": f"{PRIORITIES_NOTE} could not be read"}


@router.put("")
def put_priorities(request: ScoringRequest, vault: VaultDep) -> dict[str, Any]:
    """Save the initiatives and weights to the vault, and return the ranking."""
    frontmatter = {
        "title": "Priorities",
        "tags": ["priorities"],
        "criteria": [c.model_dump() for c in request.criteria],
        "options": [o.model_dump() for o in request.options],
    }
    rel = vault.vault.write_note(PRIORITIES_NOTE, None, frontmatter=frontmatter, body=_body(request))
    vault.apply_changes({rel})
    return _view(request.criteria, request.options)
