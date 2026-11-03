from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.vault.manager import NoteExistsError, NoteNotFoundError, VaultError, VaultManager, VaultPathError


@pytest.fixture
def vault(tmp_path: Path) -> VaultManager:
    manager = VaultManager(tmp_path / "vault" / "default")
    manager.ensure_layout()
    return manager


@pytest.mark.parametrize(
    "bad",
    [
        "../secret.md",
        "notes/../../x.md",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "c:notes.md",
        ".index/links.json",
        "notes/.hidden.md",
        ".obsidian/app.json",
        "CON.md",
        "notes/aux",
        "notes/a?.md",
        'notes/"q".md',
        "notes/trailing. ",
        "",
        "notes//x.md",
    ],
)
def test_unsafe_paths_are_rejected(vault: VaultManager, bad: str) -> None:
    with pytest.raises(VaultPathError):
        vault.resolve(bad)


def test_backslash_paths_are_normalised(vault: VaultManager) -> None:
    assert vault.resolve("notes\\a.md") == vault.root / "notes" / "a.md"


def test_layout_listing_and_hidden_files(vault: VaultManager) -> None:
    assert all((vault.root / f).is_dir() for f in ("profile", "notes", "decisions", "journal", "sources"))
    vault.write_note("notes/a.md", "# A")
    (vault.root / ".obsidian").mkdir()
    (vault.root / ".obsidian" / "x.md").write_text("ignored", encoding="utf-8")
    (vault.root / "notes" / "~$lock.md").write_text("ignored", encoding="utf-8")
    (vault.root / "notes" / "image.png").write_bytes(b"\x89PNG")
    assert vault.iter_files() == ["notes/a.md"]


def test_write_read_frontmatter_and_errors(vault: VaultManager) -> None:
    rel = vault.write_note("notes/plan.md", frontmatter={"title": "Plan", "tags": ["x"]}, body="Body [[Missing]]\n")
    vault.refresh_links()
    note = vault.read_note(rel)
    assert note["title"] == "Plan" and note["frontmatter"]["tags"] == ["x"] and note["body"] == "Body [[Missing]]\n"
    assert note["links"] == [{"target": "Missing", "heading": None, "alias": None, "embed": False, "resolved": None}]
    with pytest.raises(NoteExistsError):
        vault.write_note(rel, "x", create_only=True)
    with pytest.raises(VaultError):
        vault.write_note("notes/x.pdf", "x")
    with pytest.raises(NoteNotFoundError):
        vault.read_note("notes/none.md")
    with pytest.raises(NoteNotFoundError):
        vault.delete("notes/none.md")
    assert vault.delete(rel) == rel and not (vault.root / rel).exists()


def test_backlinks_aliases_and_links_json(vault: VaultManager) -> None:
    vault.write_note("profile/company.md", "---\naliases: [Northwind]\n---\n# Company\n")
    vault.write_note("notes/a.md", "Links: [[Northwind]] and [[company#Goals|goals]] and [[ghost]].")
    vault.write_note("journal/day.md", "Today [[a]]. Self [[#Top]].")
    graph = vault.refresh_links()
    assert graph.backlinks["profile/company.md"] == ["notes/a.md"]
    assert graph.backlinks["notes/a.md"] == ["journal/day.md"]
    assert graph.unresolved == {"ghost": ["notes/a.md"]}
    stored = json.loads((vault.index_dir / "links.json").read_text(encoding="utf-8"))
    assert stored["backlinks"]["profile/company.md"] == ["notes/a.md"]
    assert stored["notes"]["profile/company.md"]["aliases"] == ["Northwind"]
    assert vault.read_note("profile/company.md")["backlinks"] == ["notes/a.md"]
    # An edit outside the app (e.g. Notepad) is picked up on the next refresh.
    (vault.root / "notes" / "a.md").write_text("No links any more", encoding="utf-8")
    assert "profile/company.md" not in vault.refresh_links().backlinks


def test_rename_rewrites_links_and_keeps_heading_alias(vault: VaultManager) -> None:
    vault.write_note("notes/pricing.md", "---\naliases: [Price notes]\n---\n# Pricing\n## Annual\nx")
    vault.write_note("journal/day.md", "See [[pricing]], [[pricing#Annual|annual]], ![[pricing]], [[Price notes]].")
    vault.write_note("notes/other.md", "Path link [[notes/pricing]] and `[[pricing]]` in code.")
    result = vault.rename("notes/pricing.md", "decisions/price-plan.md")
    assert result.to_path == "decisions/price-plan.md"
    assert sorted(result.updated_files) == ["journal/day.md", "notes/other.md"]
    day = (vault.root / "journal" / "day.md").read_text(encoding="utf-8")
    # The alias link still resolves (aliases move with the note), so it is left alone.
    assert day == "See [[price-plan]], [[price-plan#Annual|annual]], ![[price-plan]], [[Price notes]]."
    other = (vault.root / "notes" / "other.md").read_text(encoding="utf-8")
    assert other == "Path link [[price-plan]] and `[[pricing]]` in code."
    assert vault.graph.backlinks["decisions/price-plan.md"] == ["journal/day.md", "notes/other.md"]
    assert vault.graph.unresolved == {}


def test_rename_errors(vault: VaultManager) -> None:
    vault.write_note("notes/a.md", "a")
    vault.write_note("notes/b.md", "b")
    with pytest.raises(NoteExistsError):
        vault.rename("notes/a.md", "notes/b.md")
    with pytest.raises(NoteNotFoundError):
        vault.rename("notes/zzz.md", "notes/c.md")
    with pytest.raises(VaultError):
        vault.rename("notes/a.md", "notes/a.txt")
    with pytest.raises(VaultPathError):
        vault.rename("notes/a.md", "../a.md")
