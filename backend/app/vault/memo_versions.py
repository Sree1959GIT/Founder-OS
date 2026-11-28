"""Founder F18: one memo per open decision. A new memo for the same decision replaces that decision's memo file, and
the text it replaces is kept here, outside the vault (so search and the Librarian never read an old proposal as
current). Paths: `<workspace data>/memo_versions/<memo file stem>/<YYYYMMDDTHHMMSS>.md`."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from loguru import logger

from app.vault.parsers import split_frontmatter

_ID = re.compile(r"^\d{8}T\d{6}(-\d+)?$")


def _folder(root: Path, memo_path: str) -> Path:
    stem = Path(memo_path).stem
    if not stem or stem.startswith(".") or "/" in stem or "\\" in stem:
        raise ValueError(f"not a memo path: {memo_path}")
    return root / stem


def find_memo_for(vault: Any, decision: str) -> str | None:
    """The proposed memo already written for this open decision (its `decision` key), newest first."""
    if not decision:
        return None
    found: list[tuple[str, str]] = []
    for rel in vault.iter_files():
        if not rel.startswith("decisions/") or not rel.endswith(".md"):
            continue
        try:
            note = vault.read_note(rel)
        except Exception:  # an unreadable note is simply not this decision's memo
            continue
        fm = note.get("frontmatter") or {}
        if fm.get("decision") == decision and fm.get("status", "proposed") == "proposed":
            found.append((str(fm.get("written_at") or fm.get("written") or ""), rel))
    return max(found)[1] if found else None


def keep_version(root: Path, memo_path: str, content: str, at: dt.datetime | None = None) -> str:
    """Saves the memo text about to be replaced; returns its version id."""
    folder = _folder(root, memo_path)
    folder.mkdir(parents=True, exist_ok=True)
    fm, _body, _err = split_frontmatter(content)
    stamp = str(fm.get("written_at") or "")
    try:
        when = dt.datetime.fromisoformat(stamp) if stamp else (at or dt.datetime.now())
    except ValueError:
        when = at or dt.datetime.now()
    base = when.strftime("%Y%m%dT%H%M%S")
    version, n = base, 1
    while (folder / f"{version}.md").exists():
        n += 1
        version = f"{base}-{n}"
    (folder / f"{version}.md").write_text(content, encoding="utf-8")
    logger.info("Memo {}: earlier version kept as {}", memo_path, version)
    return version


def list_versions(root: Path, memo_path: str) -> list[dict[str, Any]]:
    """Earlier versions of one memo, newest first: id, when it was written, its title and proposed option."""
    folder = _folder(root, memo_path)
    if not folder.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for file in folder.glob("*.md"):
        if not _ID.match(file.stem):
            continue
        fm, _body, _err = split_frontmatter(file.read_text(encoding="utf-8"))
        items.append(
            {
                "id": file.stem,
                "written_at": str(fm.get("written_at") or fm.get("written") or ""),
                "title": str(fm.get("title") or ""),
                "proposed_option": str(fm.get("proposed_option") or ""),
            }
        )
    return sorted(items, key=lambda v: v["id"], reverse=True)


def read_version(root: Path, memo_path: str, version: str) -> dict[str, Any]:
    if not _ID.match(version):
        raise ValueError(f"not a version id: {version}")
    file = _folder(root, memo_path) / f"{version}.md"
    if not file.is_file():
        raise FileNotFoundError(version)
    content = file.read_text(encoding="utf-8")
    fm, body, _err = split_frontmatter(content)
    return {"id": version, "frontmatter": fm, "body": body}
