"""Text embeddings behind one interface: Ollama (`nomic-embed-text`, default) and a deterministic fake for tests.

Calls are synchronous; the vault index runs them in worker threads. Failures raise `EmbeddingError` and the search
falls back to BM25 only (PRD R3).
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from typing import Protocol

import httpx

EMBED_BATCH = 32
_WORD_RE = re.compile(r"\w+")


class EmbeddingError(Exception):
    """The embedding backend is unavailable or returned something unusable."""


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def task_prefixes(model: str) -> tuple[str, str]:
    """(document prefix, query prefix). These models were trained with them, and retrieve worse without them.

    nomic-embed-text: its model card. EmbeddingGemma: "title: none | text: " and "task: search result | query: ", from
    its model card, read 2026-11-05. mxbai-embed-large has a query instruction only.
    """
    name = model.lower()
    if "nomic-embed" in name:
        return "search_document: ", "search_query: "
    if "embeddinggemma" in name:
        return "title: none | text: ", "task: search result | query: "
    if "mxbai-embed" in name:
        return "", "Represent this sentence for searching relevant passages: "
    return "", ""


class OllamaEmbedder:
    """`POST /api/embed` on Ollama, with the task prefixes each model expects."""

    def __init__(self, base_url: str, model: str, timeout_s: float = 60.0) -> None:
        self.name = f"ollama:{model}"
        self._url = f"{base_url.rstrip('/')}/api/embed"
        self._model = model
        self._timeout = timeout_s
        self._doc_prefix, self._query_prefix = task_prefixes(model)

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=self._timeout) as client:
            for start in range(0, len(inputs), EMBED_BATCH):
                batch = inputs[start : start + EMBED_BATCH]
                try:
                    response = client.post(self._url, json={"model": self._model, "input": batch})
                    response.raise_for_status()
                    embeddings = response.json()["embeddings"]
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    raise EmbeddingError(f"Ollama embeddings failed ({type(exc).__name__}: {exc})") from exc
                if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                    raise EmbeddingError("Ollama returned the wrong number of embeddings")
                vectors.extend([float(x) for x in vector] for vector in embeddings)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self._doc_prefix + t for t in texts]) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._query_prefix + text])[0]


class FakeEmbedder:
    """Hashed bag of words (+ bigrams), L2-normalised. Deterministic, offline, and similar texts score higher."""

    def __init__(self, dim: int = 64) -> None:
        self.name = f"fake:{dim}"
        self.dim = dim
        self.fail = False  # tests flip this to simulate Ollama being down
        self.calls = 0

    def _vector(self, text: str) -> list[float]:
        words = [w.lower() for w in _WORD_RE.findall(text)]
        features = words + [f"{a} {b}" for a, b in itertools.pairwise(words)]
        vector = [0.0] * self.dim
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise EmbeddingError("fake embedder is set to fail")
        self.calls += 1
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        if self.fail:
            raise EmbeddingError("fake embedder is set to fail")
        return self._vector(text)
