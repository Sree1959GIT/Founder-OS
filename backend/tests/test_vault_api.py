from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.vault.service import VaultService
from app.vault.watcher import changed_paths, make_filter
from tests.test_vault_parsers import make_pdf


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings.model_copy(update={"auto_load_sample_vault": True}))
    with TestClient(app) as test_client:
        yield test_client


def test_sample_vault_is_seeded_and_listed(client: TestClient) -> None:
    status = client.get("/api/vault/status").json()
    assert status["files"] == 7 and status["errors"] == {} and status["embedder"] == "fake:64"
    assert status["vector_store"] == "memory" and status["tokenizer"] == "approx"
    notes = client.get("/api/vault/notes").json()
    assert notes["count"] == 7
    company = next(n for n in notes["notes"] if n["path"] == "profile/company.md")
    assert company["title"] == "Northwind Analytics" and company["folder"] == "profile" and company["backlinks"] >= 2
    decisions = client.get("/api/vault/notes", params={"folder": "decisions"}).json()
    assert [n["path"] for n in decisions["notes"]] == ["decisions/2026-09-hire-two-sdrs.md"]


def test_read_note_with_links_and_backlinks(client: TestClient) -> None:
    note = client.get("/api/vault/notes/notes/pricing-strategy.md").json()
    assert note["title"] == "Pricing strategy" and note["frontmatter"]["aliases"] == ["Pricing"]
    resolved = {link["target"]: link["resolved"] for link in note["links"]}
    assert resolved["Northwind"] == "profile/company.md"
    assert resolved["2026-09-hire-two-sdrs"] == "decisions/2026-09-hire-two-sdrs.md"
    assert "journal/2026-10-28.md" in note["backlinks"]
    graph = client.get("/api/vault/links").json()
    assert graph["unresolved"] == {} and "notes/pricing-strategy.md" in graph["backlinks"]
    csv_note = client.get("/api/vault/notes/sources/competitor-pricing.csv").json()
    assert csv_note["content"] is None and csv_note["kind"] == "csv"


def test_search_get_and_post(client: TestClient) -> None:
    result = client.get("/api/search", params={"q": "why are logistics customers churning", "k": 3}).json()
    assert result["mode"] == "hybrid" and len(result["results"]) == 3
    assert result["results"][0]["citation"]["path"] in {"notes/customer-churn.md", "journal/2026-10-28.md"}
    assert {"path", "heading", "chunk_id"} == set(result["results"][0]["citation"])
    posted = client.post("/api/search", json={"q": "SDR kill criterion", "k": 1, "mode": "bm25"}).json()
    assert posted["mode"] == "bm25" and posted["results"][0]["path"] == "decisions/2026-09-hire-two-sdrs.md"
    assert client.get("/api/search", params={"q": ""}).status_code == 422
    assert client.get("/api/search", params={"q": "x", "mode": "magic"}).status_code == 422


def test_write_rename_delete_cycle(client: TestClient) -> None:
    body = {"frontmatter": {"title": "Dubai office", "tags": ["expansion"]}, "body": "# Dubai\nOpen a Dubai office?"}
    written = client.put("/api/vault/notes/notes/dubai.md", json=body)
    assert written.status_code == 200 and written.json()["title"] == "Dubai office"
    assert client.put("/api/vault/notes/notes/dubai.md", json={"content": "x", "create_only": True}).status_code == 409
    client.put("/api/vault/notes/journal/link.md", json={"content": "Thinking about [[dubai|the office]]."})
    found = client.get("/api/search", params={"q": "Dubai office", "mode": "bm25"}).json()["results"]
    assert found[0]["path"] == "notes/dubai.md"
    renamed = client.post("/api/vault/rename", json={"from_path": "notes/dubai.md", "to_path": "decisions/dubai.md"})
    assert renamed.status_code == 200 and renamed.json()["updated_files"] == []  # [[dubai]] still resolves
    renamed = client.post(
        "/api/vault/rename", json={"from_path": "decisions/dubai.md", "to_path": "decisions/uae-office.md"}
    ).json()
    assert renamed["updated_files"] == ["journal/link.md"] and renamed["links_rewritten"] == 1
    link_note = client.get("/api/vault/notes/journal/link.md").json()
    assert link_note["content"] == "Thinking about [[uae-office|the office]]."
    found = client.get("/api/search", params={"q": "Dubai office", "mode": "bm25"}).json()["results"]
    assert found[0]["path"] == "decisions/uae-office.md"
    assert client.delete("/api/vault/notes/decisions/uae-office.md").json() == {"deleted": "decisions/uae-office.md"}
    after = client.get("/api/search", params={"q": "Dubai office", "mode": "bm25"}).json()["results"]
    assert all(r["path"] != "decisions/uae-office.md" for r in after)


def test_errors_and_path_safety(client: TestClient) -> None:
    assert client.get("/api/vault/notes/notes/missing.md").status_code == 404
    assert client.get("/api/vault/notes/..%2F..%2Fsecret.md").status_code in (400, 404)
    assert client.put("/api/vault/notes/CON.md", json={"content": "x"}).status_code == 400
    assert client.put("/api/vault/notes/.index/links.json", json={"content": "x"}).status_code == 400
    assert client.put("/api/vault/notes/notes/x.pdf", json={"content": "x"}).status_code == 422
    assert client.put("/api/vault/notes/notes/x.md", json={}).status_code == 422
    bad = client.post("/api/vault/rename", json={"from_path": "notes/customer-churn.md", "to_path": "../x.md"})
    assert bad.status_code == 400


def test_upload_pdf_csv_and_limits(client: TestClient, settings: Settings) -> None:
    pdf = make_pdf(["Zanzibar distribution partnership terms"])
    uploaded = client.post("/api/vault/upload", files={"file": ("Partner Deck.pdf", pdf, "application/pdf")})
    assert uploaded.status_code == 200 and uploaded.json() == {
        "path": "sources/Partner Deck.pdf",
        "size": len(pdf),
        "error": None,
    }
    hit = client.get("/api/search", params={"q": "Zanzibar partnership"}).json()["results"][0]
    assert hit["path"] == "sources/Partner Deck.pdf" and hit["heading"] == "Page 1"
    csv_up = client.post(
        "/api/vault/upload",
        files={"file": ("kpis.csv", b"metric,value\nNPS,41\n", "text/csv")},
        data={"folder": "notes"},
    )
    assert csv_up.json()["path"] == "notes/kpis.csv"
    broken = client.post("/api/vault/upload", files={"file": ("broken.pdf", b"garbage", "application/pdf")})
    assert broken.status_code == 200 and "cannot read PDF" in broken.json()["error"]
    assert (
        client.post("/api/vault/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code
        == 415
    )
    bad_folder = client.post(
        "/api/vault/upload", files={"file": ("a.md", b"x", "text/markdown")}, data={"folder": ".."}
    )
    assert bad_folder.status_code == 400
    big = b"x" * (settings.max_upload_mb * 1024 * 1024 + 1)
    assert client.post("/api/vault/upload", files={"file": ("big.txt", big, "text/plain")}).status_code == 413


def test_external_edit_is_picked_up_by_reindex(client: TestClient, settings: Settings) -> None:
    assert client.get("/api/vault/status").json()["files"] == 7  # waits for the startup index
    note = settings.workspace_vault_dir() / "notes" / "pricing-strategy.md"
    note.write_text(note.read_text(encoding="utf-8") + "\nQuokka pricing experiment.\n", encoding="utf-8")
    assert client.get("/api/search", params={"q": "quokka", "mode": "bm25"}).json()["results"] == []  # no watcher
    status = client.post("/api/vault/reindex").json()
    assert status["files"] == 7
    assert client.get("/api/search", params={"q": "quokka", "mode": "bm25"}).json()["results"][0]["path"] == (
        "notes/pricing-strategy.md"
    )
    assert client.post("/api/vault/reindex", params={"full": True}).json()["files"] == 7


def test_watcher_filter() -> None:
    root = Path("/vault") if not Path("C:/").exists() else Path("C:/vault")
    keep = make_filter(root)
    assert keep(None, str(root / "notes" / "a.md"))  # type: ignore[arg-type]
    assert not keep(None, str(root / ".index" / "links.json"))  # type: ignore[arg-type]
    assert not keep(None, str(root / "notes" / ".a.md.123.tmp"))  # type: ignore[arg-type]
    assert not keep(None, str(root / "notes" / "~$draft.md"))  # type: ignore[arg-type]
    assert not keep(None, str(root.parent / "elsewhere.md"))  # type: ignore[arg-type]
    assert changed_paths(root, {(None, str(root / "notes" / "a.md"))}) == {"notes/a.md"}  # type: ignore[arg-type]


async def test_watcher_reindexes_external_edits(settings: Settings) -> None:
    service = VaultService(settings)
    await asyncio.to_thread(service.ensure_started)
    await service.start_watcher()
    try:
        note = service.vault.root / "notes" / "from-notepad.md"
        start = time.monotonic()
        deadline = start + 20
        saves = 0
        while time.monotonic() < deadline:
            # Re-save every ~2 s: the OS-level watch can start a moment after start_watcher() returns.
            if saves * 2 <= time.monotonic() - start:
                note.write_text(f"# Notepad\nThe walrus budget line was cut ({saves}).", encoding="utf-8")
                saves += 1
            results = service.index.search("walrus budget", mode="bm25")["results"]
            if results and results[0]["path"] == "notes/from-notepad.md":
                break
            await asyncio.sleep(0.2)
        else:
            pytest.fail("the watcher did not index the new note")
        assert service.watching
        note.unlink()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and service.index.search("walrus", mode="bm25")["results"]:
            await asyncio.sleep(0.2)
        assert service.index.search("walrus", mode="bm25")["results"] == []
    finally:
        await service.stop_watcher()
    assert not service.watching
