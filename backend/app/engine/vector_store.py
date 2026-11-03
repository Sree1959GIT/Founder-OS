"""Dense vector stores for child chunks: Qdrant (REST, one collection per workspace) and an in-memory fallback.

Point ids are UUIDv5 of `chunk_id + content_hash`, so an unchanged chunk keeps its id across restarts and the index
only embeds what is new (`ids()` is compared with the wanted set). Payload: `chunk_id`, `path`, `hash`.
Failures raise `VectorStoreError`; the search then runs BM25 only (PRD R3).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import numpy as np

_NAMESPACE = uuid.UUID("6f1c3f0e-5b8a-4c55-9a3e-2d5c1a7e9b10")
SCROLL_PAGE = 1000


class VectorStoreError(Exception):
    """The vector store is unavailable or rejected a request."""


def point_id(chunk_id: str, content_hash: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{chunk_id}\x00{content_hash}"))


@dataclass
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict[str, Any]


class VectorStore(Protocol):
    name: str

    def ids(self) -> set[str]: ...

    def upsert(self, points: list[VectorPoint]) -> None: ...

    def delete(self, ids: list[str]) -> None: ...

    def search(self, vector: list[float], limit: int, folder: str | None = None) -> list[VectorHit]: ...


class InMemoryVectorStore:
    """Cosine similarity with NumPy. Lost on restart (the index re-embeds at startup)."""

    name = "memory"

    def __init__(self) -> None:
        self._points: dict[str, tuple[np.ndarray, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def ids(self) -> set[str]:
        with self._lock:
            return set(self._points)

    def upsert(self, points: list[VectorPoint]) -> None:
        with self._lock:
            for point in points:
                vector = np.asarray(point.vector, dtype=np.float32)
                norm = float(np.linalg.norm(vector)) or 1.0
                self._points[point.id] = (vector / norm, dict(point.payload))

    def delete(self, ids: list[str]) -> None:
        with self._lock:
            for item in ids:
                self._points.pop(item, None)

    def search(self, vector: list[float], limit: int, folder: str | None = None) -> list[VectorHit]:
        with self._lock:
            items = [i for i in self._points.items() if folder is None or folder in i[1][1].get("folders", [])]
        if not items:
            return []
        query = np.asarray(vector, dtype=np.float32)
        query = query / (float(np.linalg.norm(query)) or 1.0)
        dims = {v.shape[0] for _, (v, _) in items}
        if dims != {query.shape[0]}:
            raise VectorStoreError(f"vector size mismatch (query {query.shape[0]}, stored {sorted(dims)})")
        matrix = np.stack([v for _, (v, _) in items])
        scores = matrix @ query
        order = np.argsort(-scores)[:limit]
        return [VectorHit(items[i][0], float(scores[i]), dict(items[i][1][1])) for i in order]


class QdrantVectorStore:
    """Qdrant over its REST API (httpx). The collection is created on first upsert with the embedding size."""

    name = "qdrant"

    def __init__(self, base_url: str, collection: str, timeout_s: float = 10.0, client: httpx.Client | None = None):
        self._base = base_url.rstrip("/")
        self.collection = collection
        self._client = client or httpx.Client(timeout=timeout_s)
        self._dim: int | None = None

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, f"{self._base}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"Qdrant not reachable ({type(exc).__name__})") from exc
        if response.status_code == 404:
            return {"status": 404}
        if response.status_code >= 400:
            raise VectorStoreError(f"Qdrant {method} {path} -> HTTP {response.status_code}: {response.text[:200]}")
        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise VectorStoreError("Qdrant returned invalid JSON") from exc
        return body

    def ping(self) -> None:
        self._request("GET", "/collections")

    def _collection_dim(self) -> int | None:
        body = self._request("GET", f"/collections/{self.collection}")
        if body.get("status") == 404:
            return None
        vectors = body.get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
        size = vectors.get("size") if isinstance(vectors, dict) else None
        return int(size) if size else None

    def _ensure(self, dim: int) -> None:
        if self._dim == dim:
            return
        existing = self._collection_dim()
        if existing is not None and existing != dim:
            # Same collection, new vector size: rebuild it and make the caller re-read ids and re-embed everything.
            self._request("DELETE", f"/collections/{self.collection}")
            self._create(dim)
            raise VectorStoreError(f"collection {self.collection} had a different vector size; it was recreated")
        if existing is None:
            self._request(
                "PUT", f"/collections/{self.collection}", json={"vectors": {"size": dim, "distance": "Cosine"}}
            )
        self._dim = dim

    def _create(self, dim: int) -> None:
        self._request("PUT", f"/collections/{self.collection}", json={"vectors": {"size": dim, "distance": "Cosine"}})
        self._dim = dim

    def ids(self) -> set[str]:
        found: set[str] = set()
        offset: Any = None
        while True:
            body: dict[str, Any] = {"limit": SCROLL_PAGE, "with_payload": False, "with_vector": False}
            if offset is not None:
                body["offset"] = offset
            result = self._request("POST", f"/collections/{self.collection}/points/scroll", json=body)
            if result.get("status") == 404:
                return set()
            page = result.get("result", {})
            found.update(str(p["id"]) for p in page.get("points", []))
            offset = page.get("next_page_offset")
            if offset is None:
                return found

    def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        self._ensure(len(points[0].vector))
        for start in range(0, len(points), 256):
            batch = points[start : start + 256]
            self._request(
                "PUT",
                f"/collections/{self.collection}/points?wait=true",
                json={"points": [{"id": p.id, "vector": p.vector, "payload": p.payload} for p in batch]},
            )

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._request("POST", f"/collections/{self.collection}/points/delete?wait=true", json={"points": ids})

    def search(self, vector: list[float], limit: int, folder: str | None = None) -> list[VectorHit]:
        query: dict[str, Any] = {"vector": vector, "limit": limit, "with_payload": True}
        if folder:
            query["filter"] = {"must": [{"key": "folders", "match": {"value": folder}}]}
        body = self._request("POST", f"/collections/{self.collection}/points/search", json=query)
        if body.get("status") == 404:
            return []
        return [VectorHit(str(h["id"]), float(h["score"]), h.get("payload") or {}) for h in body.get("result", [])]
