"""Embedding comparison (deferred from M3a): retrieval quality on labelled queries, latency and VRAM.

The labelled queries run over the sample vault, through the real `HybridIndex` with an in-memory store, in `dense` and
`hybrid` modes. Half of them share few words with the note on purpose: keyword search is the same for every model, so
those show what the embedding adds. It is a small vault, so read small differences as a tie.
"""

from __future__ import annotations

import json
import shutil
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.engine.chunking import ApproxTokenizer
from app.engine.embeddings import Embedder, EmbeddingError
from app.engine.hybrid_rag import HybridIndex
from app.engine.vector_store import InMemoryVectorStore
from app.evals.vault_eval import SAMPLE_VAULT
from app.vault.manager import VaultManager

QUERIES_PATH = Path(__file__).with_name("embedding_queries.json")
K = 3


@dataclass(frozen=True)
class LabelledQuery:
    query: str
    relevant: list[str]


def load_queries(path: Path = QUERIES_PATH) -> list[LabelledQuery]:
    return [LabelledQuery(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


@dataclass
class ModeScore:
    mode: str
    ranks: list[int | None] = field(default_factory=list)  # 1-based rank of the first relevant note, or None

    @property
    def recall_at_1(self) -> float:
        return sum(r == 1 for r in self.ranks) / len(self.ranks) if self.ranks else 0.0

    @property
    def recall_at_k(self) -> float:
        return sum(r is not None and r <= K for r in self.ranks) / len(self.ranks) if self.ranks else 0.0

    @property
    def mrr(self) -> float:
        return statistics.fmean(1 / r if r else 0.0 for r in self.ranks) if self.ranks else 0.0


@dataclass
class EmbedderScore:
    name: str
    dim: int = 0
    index_s: float = 0.0
    chunks: int = 0
    query_ms: list[float] = field(default_factory=list)
    vram_gb: float | None = None
    modes: dict[str, ModeScore] = field(default_factory=dict)
    error: str = ""

    def rows(self) -> list[list[str]]:
        if self.error:
            return [[self.name, "-", "-", "-", "-", "-", "-", "-", self.error]]
        ordered = sorted(self.query_ms)
        p50 = ordered[len(ordered) // 2] if ordered else 0.0
        vram = "unknown" if self.vram_gb is None else f"{self.vram_gb:.2f}"
        return [
            [
                self.name,
                mode.mode,
                f"{mode.recall_at_1:.0%}",
                f"{mode.recall_at_k:.0%}",
                f"{mode.mrr:.3f}",
                f"{p50:.0f}",
                f"{self.index_s:.1f}",
                vram,
                f"{self.dim}-d, {self.chunks} chunks",
            ]
            for mode in self.modes.values()
        ]


HEADERS = ["model", "mode", "recall@1", f"recall@{K}", "MRR", "query ms", "index s", "VRAM GB", "note"]


def _first_relevant_rank(hits: list[dict[str, Any]], relevant: list[str]) -> int | None:
    seen: list[str] = []
    for hit in hits:
        path = hit["citation"]["path"]
        if path not in seen:
            seen.append(path)
    return next((i + 1 for i, path in enumerate(seen) if path in relevant), None)


def score_embedder(embedder: Embedder, queries: list[LabelledQuery], vault_root: Path = SAMPLE_VAULT) -> EmbedderScore:
    result = EmbedderScore(embedder.name)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "vault"
        shutil.copytree(vault_root, root)
        index = HybridIndex(VaultManager(root), embedder, InMemoryVectorStore(), ApproxTokenizer())
        started = time.perf_counter()
        try:
            result.dim = len(embedder.embed_query("dimension check"))
            index.refresh()
        except EmbeddingError as exc:
            result.error = str(exc)[:120]
            return result
        result.index_s = time.perf_counter() - started
        result.chunks = index.status()["children"]
        for mode in ("dense", "hybrid"):
            score = ModeScore(mode)
            for query in queries:
                began = time.perf_counter()
                found = index.search(query.query, k=K * 3, mode=mode)  # type: ignore[arg-type]
                if mode == "dense":
                    result.query_ms.append((time.perf_counter() - began) * 1000)
                if found.get("mode") != mode:
                    result.error = f"fell back to {found.get('mode')}: {found.get('warnings')}"[:120]
                    return result
                score.ranks.append(_first_relevant_rank(found["results"], query.relevant))
            result.modes[mode] = score
    return result


def loaded_vram_gb(base_url: str, model: str) -> float | None:
    """What Ollama reports for the loaded model. None when it cannot say."""
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/ps", timeout=10.0)
        response.raise_for_status()
        for row in response.json().get("models", []):
            if row.get("name", "").split(":")[0] == model.split(":")[0]:
                return float(row.get("size_vram", 0)) / 1024**3
    except (httpx.HTTPError, ValueError, TypeError):
        return None
    return None


def recommend(scores: list[EmbedderScore], incumbent: str, tie: float = 0.05) -> str:
    """A proposal only. Judged on hybrid, the mode the app searches with; a new model must beat noise on this small set."""
    mine = next((s for s in scores if incumbent in s.name and not s.error), None)
    others = [s for s in scores if s is not mine and not s.error and "hybrid" in s.modes]
    if mine is None or "hybrid" not in mine.modes or not others:
        return "Not enough models answered to compare."
    best = max(others, key=lambda s: s.modes["hybrid"].mrr)
    gain = best.modes["hybrid"].mrr - mine.modes["hybrid"].mrr
    if gain > tie:
        return (
            f"{best.name} beats {mine.name} on hybrid MRR by {gain:.3f}. Check its licence before choosing it: "
            "see the licence note in PRD section 12."
        )
    return (
        f"No model beats {mine.name} by more than {tie} on hybrid MRR, the mode the app uses "
        f"(best other: {best.name}, {gain:+.3f}). Proposal: keep {mine.name}."
    )
