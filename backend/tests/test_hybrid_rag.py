from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import PROJECT_ROOT
from app.engine.chunking import ApproxTokenizer
from app.engine.embeddings import EmbeddingError, FakeEmbedder, OllamaEmbedder
from app.engine.hybrid_rag import RRF_K, HybridIndex
from app.engine.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorPoint, VectorStoreError
from app.vault.manager import VaultManager

SAMPLE_VAULT = PROJECT_ROOT / "sample_data" / "vault"


def make_index(tmp_path: Path, store: Any = None, embedder: FakeEmbedder | None = None) -> HybridIndex:
    root = tmp_path / "vault"
    shutil.copytree(SAMPLE_VAULT, root)
    vault = VaultManager(root)
    index = HybridIndex(
        vault, embedder or FakeEmbedder(), store if store is not None else InMemoryVectorStore(), ApproxTokenizer()
    )
    index.refresh()
    return index


def test_sample_vault_indexes_and_hybrid_search_cites_sources(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    status = index.status()
    assert status["files"] == 7 and status["errors"] == {}
    assert status["embedded"] == status["children"] > 0 and status["dense_available"]
    result = index.search("annual prepayment discount effective price per seat", k=3)
    assert result["mode"] == "hybrid" and result["warnings"] == []
    top = next(r for r in result["results"] if r["path"] == "notes/pricing-strategy.md")
    assert top["rank"] <= 2
    assert top["citation"] == {"path": top["path"], "heading": top["heading"], "chunk_id": top["chunk_id"]}
    assert top["chunk_id"].startswith("notes/pricing-strategy.md#p") and top["child_id"].startswith(top["chunk_id"])
    assert "Annual plans" in top["heading"] and top["bm25_rank"] == 1 and top["dense_rank"] is not None
    assert "15 %" in top["text"]
    # Results are distinct parents, best first.
    assert len({r["chunk_id"] for r in result["results"]}) == len(result["results"])
    assert [r["rank"] for r in result["results"]] == list(range(1, len(result["results"]) + 1))


def test_csv_source_is_searchable(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    top = index.search("Fabrikam Enterprise dedicated support", k=1, mode="bm25")["results"][0]
    assert top["path"] == "sources/competitor-pricing.csv" and top["heading"] == "Sheet competitor-pricing"


def test_rrf_scores_follow_the_formula(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    result = index.search("logistics churn budget", k=5)
    for item in result["results"]:
        expected = sum(1 / (RRF_K + r) for r in (item["bm25_rank"], item["dense_rank"]) if r is not None)
        assert item["score"] == pytest.approx(expected, abs=1e-6)
    scores = [r["score"] for r in result["results"]]
    assert scores == sorted(scores, reverse=True)


def test_folder_filter_and_modes(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    in_decisions = index.search("runway", folder="decisions")
    assert in_decisions["results"] and {r["path"].split("/")[0] for r in in_decisions["results"]} == {"decisions"}
    assert index.search("runway", mode="bm25")["mode"] == "bm25"
    dense = index.search("runway", mode="dense")
    assert dense["mode"] == "dense" and all(r["bm25_rank"] is None for r in dense["results"])
    assert index.search("the and of", mode="bm25")["results"] == []  # only stopwords


def test_embedder_down_falls_back_to_bm25_then_recovers(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    embedder.fail = True
    index = make_index(tmp_path, embedder=embedder)
    index.retry_s = 0.0
    status = index.status()
    assert status["embedded"] == 0 and not status["dense_available"] and "fail" in status["dense_error"]
    result = index.search("annual prepayment discount")
    assert result["mode"] == "bm25" and result["results"][0]["path"] == "notes/pricing-strategy.md"
    assert "keyword search (BM25) only" in result["warnings"][0]
    embedder.fail = False  # "Ollama started"
    index.sync_vectors()
    assert index.status()["embedded"] == index.status()["children"]
    assert index.search("annual prepayment discount")["mode"] == "hybrid"


def test_embedder_down_after_indexing_keeps_the_reason(tmp_path: Path) -> None:
    """Founder feedback [M2]: during the retry window the warning said "(None)" instead of the reason."""
    embedder = FakeEmbedder()
    index = make_index(tmp_path, embedder=embedder)  # everything embedded, then "Ollama stops"
    embedder.fail = True
    index.retry_s = 0.0
    first = index.search("churn")
    assert first["mode"] == "bm25" and "fake embedder is set to fail" in first["warnings"][0]
    for _ in range(5):
        index.sync_vectors()  # nothing is missing, but the embedder must still be checked
        result = index.search("churn")
        assert result["mode"] == "bm25"
        assert "(None)" not in result["warnings"][0] and "fake embedder is set to fail" in result["warnings"][0]
    assert "fail" in index.status()["dense_error"]
    embedder.fail = False
    index.sync_vectors()
    assert index.status()["dense_error"] is None and index.search("churn")["mode"] == "hybrid"


def test_no_store_means_bm25_with_warning(tmp_path: Path) -> None:
    root = tmp_path / "v"
    shutil.copytree(SAMPLE_VAULT, root)
    index = HybridIndex(VaultManager(root), FakeEmbedder(), None, ApproxTokenizer(), store_warning="no qdrant")
    index.refresh()
    result = index.search("churn")
    assert result["mode"] == "bm25" and result["warnings"] == ["no qdrant"] and result["results"]


def test_incremental_updates_reembed_only_changes(tmp_path: Path) -> None:
    store = InMemoryVectorStore()
    embedder = FakeEmbedder()
    index = make_index(tmp_path, store=store, embedder=embedder)
    before_ids = store.ids()
    calls = embedder.calls
    assert index.refresh() is False and embedder.calls == calls  # nothing changed: no work
    note = index.vault.root / "journal" / "2026-11-02.md"
    note.write_text("# Journal\nThe zeppelin partnership idea came up.", encoding="utf-8")
    assert index.refresh({"journal/2026-11-02.md"}) is True
    assert index.search("zeppelin", mode="bm25")["results"][0]["path"] == "journal/2026-11-02.md"
    assert len(store.ids() - before_ids) == 1 and before_ids <= store.ids()
    note.unlink()
    index.refresh({"journal/2026-11-02.md"})
    assert index.search("zeppelin", mode="bm25")["results"] == []
    assert all(r["path"] != "journal/2026-11-02.md" for r in index.search("zeppelin")["results"])
    assert store.ids() == before_ids  # stale vectors deleted


def test_folder_delete_and_rescan(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    shutil.rmtree(index.vault.root / "journal")
    index.refresh({"journal"})  # a folder path triggers a full rescan
    assert not any(r["path"].startswith("journal/") for r in index.search("journal board prep runway", k=10)["results"])
    assert index.refresh(full=True) is True
    assert index.status()["files"] == 6


def test_unparseable_file_is_reported_not_fatal(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    (index.vault.root / "sources" / "broken.pdf").write_bytes(b"garbage")
    index.refresh({"sources/broken.pdf"})
    assert "cannot read PDF" in index.status()["errors"]["sources/broken.pdf"]
    assert index.search("churn")["results"]


class FakeQdrant:
    """Just enough of the Qdrant REST API for QdrantVectorStore, served through httpx.MockTransport."""

    def __init__(self) -> None:
        self.collections: dict[str, dict[str, Any]] = {}
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        parts = request.url.path.strip("/").split("/")
        body = json.loads(request.content) if request.content else {}
        if parts == ["collections"]:
            return httpx.Response(200, json={"result": {"collections": []}})
        name = parts[1]
        coll = self.collections.get(name)
        if len(parts) == 2:
            if request.method == "GET":
                if coll is None:
                    return httpx.Response(404, json={"status": {"error": "not found"}})
                return httpx.Response(200, json={"result": {"config": {"params": {"vectors": {"size": coll["dim"]}}}}})
            if request.method == "PUT":
                self.collections[name] = {"dim": body["vectors"]["size"], "points": {}}
                return httpx.Response(200, json={"result": True})
            if request.method == "DELETE":
                self.collections.pop(name, None)
                return httpx.Response(200, json={"result": True})
        if coll is None:
            return httpx.Response(404, json={"status": {"error": "not found"}})
        action = parts[-1]
        points = coll["points"]
        if action == "points" and request.method == "PUT":
            for p in body["points"]:
                assert len(p["vector"]) == coll["dim"]
                points[p["id"]] = p
            return httpx.Response(200, json={"result": {"status": "completed"}})
        if action == "scroll":
            ids = sorted(points)
            start = int(body.get("offset") or 0)
            page = ids[start : start + body["limit"]]
            nxt = start + body["limit"] if start + body["limit"] < len(ids) else None
            return httpx.Response(200, json={"result": {"points": [{"id": i} for i in page], "next_page_offset": nxt}})
        if action == "delete":
            for i in body["points"]:
                points.pop(i, None)
            return httpx.Response(200, json={"result": {"status": "completed"}})
        if action == "search":
            memory = InMemoryVectorStore()
            memory.upsert([VectorPoint(i, p["vector"], p["payload"]) for i, p in points.items()])
            hits = memory.search(body["vector"], body["limit"])
            return httpx.Response(
                200, json={"result": [{"id": h.id, "score": h.score, "payload": h.payload} for h in hits]}
            )
        return httpx.Response(400, json={"status": {"error": f"unexpected {request.method} {request.url.path}"}})


def test_qdrant_store_end_to_end_with_fake_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeQdrant()
    monkeypatch.setattr("app.engine.vector_store.SCROLL_PAGE", 5)  # exercise pagination
    client = httpx.Client(transport=httpx.MockTransport(server.handler))
    store = QdrantVectorStore("http://qdrant:6333", "founderos_default", client=client)
    store.ping()
    index = make_index(tmp_path, store=store)
    assert server.collections["founderos_default"]["dim"] == 64
    assert len(store.ids()) == index.status()["children"] > 5
    result = index.search("hire two SDRs outbound", k=2)
    assert result["mode"] == "hybrid" and result["results"][0]["path"] == "decisions/2026-09-hire-two-sdrs.md"
    # A restart with the same content embeds nothing new.
    embedder = FakeEmbedder()
    again = HybridIndex(index.vault, embedder, store, ApproxTokenizer())
    again.refresh()
    assert embedder.calls == 0 and again.status()["embedded"] == again.status()["children"]
    # Qdrant goes down: search keeps working on BM25 with a warning.
    server.down = True
    down = again.search("hire two SDRs outbound")
    assert down["mode"] == "bm25" and "Qdrant not reachable" in down["warnings"][0]
    with pytest.raises(VectorStoreError):
        store.ping()
    # A different embedding size recreates the collection.
    server.down = False
    store._dim = None
    with pytest.raises(VectorStoreError, match="recreated"):
        store.upsert([VectorPoint("00000000-0000-0000-0000-000000000001", [1.0, 0.0], {"chunk_id": "x"})])
    assert server.collections["founderos_default"] == {"dim": 2, "points": {}}  # caller re-embeds everything


def test_ollama_embedder_request_shape_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if body["model"] == "broken":
            return httpx.Response(200, json={"embeddings": []})
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2] for _ in body["input"]]})

    real_client = httpx.Client
    monkeypatch.setattr(
        "app.engine.embeddings.httpx.Client",
        lambda timeout: real_client(transport=httpx.MockTransport(handler), timeout=timeout),
    )
    embedder = OllamaEmbedder("http://localhost:11434/", "nomic-embed-text")
    assert embedder.embed_documents(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert embedder.embed_query("q") == [0.1, 0.2]
    assert seen[0]["input"] == ["search_document: a", "search_document: b"]
    assert seen[1]["input"] == ["search_query: q"]
    with pytest.raises(EmbeddingError):
        OllamaEmbedder("http://localhost:11434", "broken").embed_documents(["a"])


def test_ollama_embedder_connection_refused() -> None:
    embedder = OllamaEmbedder("http://127.0.0.1:9", "nomic-embed-text", timeout_s=0.5)
    started = time.monotonic()
    with pytest.raises(EmbeddingError):
        embedder.embed_query("x")
    assert time.monotonic() - started < 10


def test_bm25_finds_words_shared_by_every_note(tmp_path: Path) -> None:
    """Regression: rank-bm25's classic IDF is <= 0 for words in most notes, so they vanished from keyword results."""
    vault = VaultManager(tmp_path / "v")
    vault.ensure_layout()
    vault.write_note("notes/only.md", "Runway is ten months.")
    index = HybridIndex(vault, FakeEmbedder(), None, ApproxTokenizer())
    index.refresh()
    assert [r["path"] for r in index.search("runway", mode="bm25")["results"]] == ["notes/only.md"]
    vault.write_note("notes/second.md", "Runway again, and runway.")
    index.refresh()
    assert {r["path"] for r in index.search("runway", mode="bm25")["results"]} == {"notes/only.md", "notes/second.md"}


def test_folder_search_filters_inside_the_vector_store(tmp_path: Path) -> None:
    store = InMemoryVectorStore()
    index = make_index(tmp_path, store=store)
    hits = store.search(FakeEmbedder().embed_query("runway"), 100, folder="decisions")
    assert hits and {h.payload["path"].split("/")[0] for h in hits} == {"decisions"}
    result = index.search("runway hiring", folder="decisions", mode="dense")
    assert result["mode"] == "dense" and result["results"][0]["path"] == "decisions/2026-09-hire-two-sdrs.md"


def test_unexpected_parser_errors_are_per_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.engine.hybrid_rag as rag

    real = rag.parse_file

    def flaky(path: Path):  # type: ignore[no-untyped-def]
        if path.suffix == ".csv":
            raise RuntimeError("field larger than field limit")  # e.g. csv.Error / pypdf DependencyError
        return real(path)

    monkeypatch.setattr(rag, "parse_file", flaky)
    index = make_index(tmp_path)
    status = index.status()
    assert status["files"] == 7 and "RuntimeError" in status["errors"]["sources/competitor-pricing.csv"]
    assert index.search("churn")["results"]


def test_sync_failure_never_raises(tmp_path: Path) -> None:
    class BadEmbedder(FakeEmbedder):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0]]  # wrong count: zip(strict=True) fails

    index = make_index(tmp_path, embedder=BadEmbedder())
    assert "vector sync failed" in index.status()["dense_error"]
    assert index.search("churn")["mode"] == "bm25"
