"""Hybrid retrieval over the vault (PRD F2): BM25 (rank-bm25) + dense vectors, fused with Reciprocal Rank Fusion.

Flow: every supported vault file is parsed (`app.vault.parsers`) and cut into parent/child chunks
(`app.engine.chunking`). Children are scored by BM25 and, when the embedder and vector store work, by cosine
similarity. RRF combines the two rankings: `score(child) = sum(1 / (k + rank))` over the lists it appears in, with
k = 60 and ranks starting at 1. A parent scores as its best child, and results are parent chunks with a citation
`{path, heading, chunk_id}`.

Degradation (PRD R3): without embeddings (Ollama down) or a vector store (Qdrant down), search is BM25 only and the
response says so in `warnings`. Chunks that could not be embedded are retried at most every `retry_s` seconds.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import re
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from loguru import logger
from rank_bm25 import BM25Okapi

from app.engine.chunking import ChildChunk, ParentChunk, Tokenizer, chunk_document
from app.engine.embeddings import Embedder, EmbeddingError
from app.engine.vector_store import VectorPoint, VectorStore, VectorStoreError, point_id
from app.vault.decisions import DecisionRecord, build_record, frontmatter_section
from app.vault.manager import VaultManager
from app.vault.parsers import ParseError, Section, parse_file

RRF_K = 60
MAX_INDEX_BYTES = 25 * 1024 * 1024
SearchMode = Literal["hybrid", "bm25", "dense"]
_TOKEN_RE = re.compile(r"\w+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "which",
        "who",
        "will",
        "with",
        "our",
        "you",
        "your",
    ]
)

# Words that say how a question is asked, not what it is about. They never make a past decision "on topic".
_NOT_TOPICAL = (
    "about after again all already am any before can could decide decided decision decisions did do does doing done "
    "far five four get had how i if last list make may me might month months more most my need next not note notes "
    "now one past previous prior quarter quarters say says second should show so still tell than their them then there "
    "these they think third three two us vault want why work working would year years"
)
_DECISION_WORDS = ("decide", "decided", "decision", "decisions")
MAX_PAST_DECISIONS = 3


def stem(token: str) -> str:
    """A light English stemmer, so "SDR" finds "SDRs" and "hiring" finds "hire". Numbers stay as they are."""
    if not token.isalpha() or len(token) < 4:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        token = token[:-1]
    for suffix in ("ing", "ed"):
        base = token[: -len(suffix)]
        if token.endswith(suffix) and len(base) >= 3 and re.search(r"[aeiouy]", base):
            token = base
            if len(token) > 3 and token[-1] == token[-2] and token[-1] not in "aeiouylsz":
                token = token[:-1]  # running -> run
            break
    if token.endswith("e") and len(token) >= 4:
        token = token[:-1]  # hire, hires, hiring and hired all become "hir"
    return token


class LuceneBM25(BM25Okapi):
    """BM25Okapi with the Lucene IDF `log(1 + (N - n + 0.5) / (n + 0.5))`, which is always positive.

    rank-bm25's classic IDF goes negative for terms found in more than half the documents, so in a small vault (or a
    one-note vault) a note that plainly contains the query word could score <= 0 and vanish from keyword results.
    """

    def _calc_idf(self, nd: dict[str, int]) -> None:
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))


def folder_prefixes(path: str) -> list[str]:
    """`notes/a/b.md` -> ["notes", "notes/a"]: stored with each vector so folder searches filter in the store."""
    parts = path.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def bm25_tokens(text: str) -> list[str]:
    return [stem(t) for t in (m.lower() for m in _TOKEN_RE.findall(text)) if t not in _STOPWORDS]


_NOT_TOPICAL_STEMS = frozenset(bm25_tokens(_NOT_TOPICAL))


def topic_terms(text: str) -> list[str]:
    return list(dict.fromkeys(t for t in bm25_tokens(text) if t not in _NOT_TOPICAL_STEMS))


def decision_matches(terms: list[str], name_words: set[str], body_words: set[str]) -> tuple[int, int] | None:
    """(matches in the note's name and tags, matches anywhere), or None when the note is not on this topic.

    Dense search always returns something, so "on topic" is decided here by words: two matches in the note's name,
    or most of the question's words including one in its name (or three anywhere). "Should we hire a designer?"
    does not match a note on hiring SDRs, and a passing link to a pricing note does not make it a pricing decision.
    """
    named = sum(t in name_words for t in terms)
    matched = sum(t in name_words or t in body_words for t in terms)
    if named >= 2 or (matched * 2 > len(terms) and (named >= 1 or matched >= 3)):
        return named, matched
    return None


@dataclass
class IndexedDoc:
    path: str
    title: str
    kind: str
    stamp: tuple[int, int]  # (mtime_ns, size): skip re-reading unchanged files
    file_hash: str
    parents: list[ParentChunk] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    frontmatter: dict[str, Any] = field(default_factory=dict)
    decision: DecisionRecord | None = None
    body: str = ""


@dataclass
class _Snapshot:
    """Immutable view used by searches, swapped atomically after each index change."""

    children: list[ChildChunk]
    parents: dict[str, ParentChunk]
    titles: dict[str, str]
    bm25: LuceneBM25 | None
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    decisions: dict[str, DecisionRecord] = field(default_factory=dict)
    decision_words: dict[str, tuple[set[str], set[str]]] = field(default_factory=dict)


class HybridIndex:
    def __init__(
        self,
        vault: VaultManager,
        embedder: Embedder,
        store: VectorStore | None,
        tokenizer: Tokenizer,
        *,
        retry_s: float = 30.0,
        store_warning: str | None = None,
    ) -> None:
        self.vault = vault
        self.embedder = embedder
        self.store = store
        self.tokenizer = tokenizer
        self.retry_s = retry_s
        self._store_warning = store_warning
        self._docs: dict[str, IndexedDoc] = {}
        self._lock = threading.RLock()
        self._vector_lock = threading.Lock()
        self._snapshot = _Snapshot([], {}, {}, None)
        self._stored_ids: set[str] | None = None
        self._embedded_ids: set[str] = set()
        self._dense_error: str | None = None
        self._last_dense_attempt = 0.0
        self.last_indexed_at: float | None = None

    # ---------------------------------------------------------------- indexing
    def _index_file(self, rel: str, path: Path) -> bool:
        """(Re)index one file if it changed. Returns True when the index changed."""
        try:
            stat = path.stat()
        except OSError:
            return self._remove(rel)
        stamp = (stat.st_mtime_ns, stat.st_size)
        current = self._docs.get(rel)
        if current and current.stamp == stamp:
            return False
        if stat.st_size > MAX_INDEX_BYTES:
            self._docs[rel] = IndexedDoc(rel, path.stem, path.suffix.lstrip("."), stamp, "", error="file too large")
            return True
        try:
            data = path.read_bytes()
        except OSError as exc:
            logger.warning("Cannot read {}: {}", rel, exc)
            return False
        file_hash = hashlib.sha256(data).hexdigest()
        if current and current.file_hash == file_hash:
            current.stamp = stamp
            return False
        kind = path.suffix.lower().lstrip(".")
        try:
            parsed = parse_file(path)
            record = frontmatter_section(parsed)
            sections: list[Section] = [record, *parsed.sections] if record else parsed.sections
            parents = chunk_document(rel, parsed.title, sections, self.tokenizer)
            doc = IndexedDoc(
                rel,
                parsed.title,
                kind,
                stamp,
                file_hash,
                parents,
                parsed.warnings,
                frontmatter=parsed.frontmatter,
                decision=build_record(rel, parsed),
                body=parsed.body,
            )
        except Exception as exc:  # one odd file (bad CSV, AES-encrypted PDF...) must never stop the index
            message = str(exc) if isinstance(exc, ParseError) else f"cannot parse ({type(exc).__name__}: {exc})"
            doc = IndexedDoc(rel, path.stem, kind, stamp, file_hash, error=message)
            logger.warning("Vault: cannot index {}: {}", rel, message)
        self._docs[rel] = doc
        return True

    def _remove(self, rel: str) -> bool:
        return self._docs.pop(rel, None) is not None

    def _scan(self, only: Iterable[str] | None) -> bool:
        changed = False
        if only is None:
            wanted = set(self.vault.iter_files())
            for rel in list(self._docs):
                if rel not in wanted:
                    changed |= self._remove(rel)
            targets: Iterable[str] = sorted(wanted)
        else:
            targets = only
        for rel in targets:
            path = self.vault.root / rel
            if self.vault.is_indexable(rel) and path.is_file():
                changed |= self._index_file(rel, path)
            else:
                changed |= self._remove(rel)
        return changed

    def _rebuild_snapshot(self) -> None:
        children = [c for doc in self._docs.values() for p in doc.parents for c in p.children]
        children.sort(key=lambda c: c.id)
        parents = {p.id: p for doc in self._docs.values() for p in doc.parents}
        titles = {doc.path: doc.title for doc in self._docs.values()}
        corpus = [bm25_tokens(c.embed_text) for c in children]
        bm25 = LuceneBM25(corpus) if corpus and any(corpus) else None
        decisions = {doc.path: doc.decision for doc in self._docs.values() if doc.decision}
        self._snapshot = _Snapshot(
            children,
            parents,
            titles,
            bm25,
            metadata={doc.path: doc.frontmatter for doc in self._docs.values() if doc.frontmatter},
            decisions=decisions,
            decision_words={
                path: (
                    set(bm25_tokens(" ".join([record.title, path.rsplit("/", 1)[-1], *record.tags]))),
                    set(bm25_tokens(self._docs[path].body)),
                )
                for path, record in decisions.items()
            },
        )
        self.last_indexed_at = time.time()

    def refresh(self, paths: Iterable[str] | None = None, *, dense: bool = True, full: bool = False) -> bool:
        """Re-index `paths` (vault-relative), or rescan everything when None. Missing files are dropped.

        `full=True` re-parses every file. The search snapshot is swapped only once the new one is complete, so a
        concurrent search or vector sync never sees a half-built (or empty) index.
        """
        with self._lock:
            if full:
                self._docs.clear()
                paths = None
            path_list = None if paths is None else list(paths)
            if path_list is not None and any(not self.vault.is_indexable(p) for p in path_list):
                path_list = None  # a folder or unknown path changed (e.g. a folder rename): rescan
            changed = self._scan(path_list)
            if path_list is not None:  # also drop files deleted with their folder
                for rel in list(self._docs):
                    if not (self.vault.root / rel).is_file():
                        changed |= self._remove(rel)
            if changed or full or self._snapshot.bm25 is None:
                self._rebuild_snapshot()
            self.vault.refresh_links()
        if dense:
            self.sync_vectors()
        return changed

    def sync_vectors(self) -> None:
        """Embed children that are not in the vector store yet and delete stale points. Never raises."""
        if self.store is None:
            return
        if not self._vector_lock.acquire(blocking=False):
            return  # another thread is already syncing
        try:
            self._last_dense_attempt = time.monotonic()
            wanted = {point_id(c.id, c.content_hash): c for c in self._snapshot.children}
            stored = set(self._stored_ids) if self._stored_ids is not None else self.store.ids()
            missing = [pid for pid in wanted if pid not in stored]
            stale = [pid for pid in stored if pid not in wanted]
            for start in range(0, len(missing), 64):
                batch = missing[start : start + 64]
                vectors = self.embedder.embed_documents([wanted[pid].embed_text for pid in batch])
                points = [
                    VectorPoint(
                        pid,
                        vec,
                        {
                            "chunk_id": wanted[pid].id,
                            "path": wanted[pid].path,
                            "hash": wanted[pid].content_hash,
                            "folders": folder_prefixes(wanted[pid].path),
                        },
                    )
                    for pid, vec in zip(batch, vectors, strict=True)
                ]
                self.store.upsert(points)
                stored.update(batch)
                self._stored_ids = set(stored)
                self._embedded_ids = set(stored)
            if stale:
                self.store.delete(stale)
                stored.difference_update(stale)
            if not missing and self._dense_error:
                # Nothing to embed proves nothing: check the embedder itself before clearing a query-time error.
                self.embedder.embed_query("ping")
            self._stored_ids = stored
            self._embedded_ids = set(stored)
            if self._dense_error:
                logger.info("Vault: dense search available again ({} chunks embedded)", len(missing))
            self._dense_error = None
        except (EmbeddingError, VectorStoreError) as exc:
            if self._dense_error != str(exc):
                logger.warning("Vault: dense index unavailable, search uses BM25 only: {}", exc)
            self._dense_error = str(exc)
            self._stored_ids = None
        except Exception as exc:  # e.g. a misbehaving embedder (zip length mismatch); never kill the caller
            logger.exception("Vault: vector sync failed: {}", exc)
            self._dense_error = f"vector sync failed ({type(exc).__name__}: {exc})"
            self._stored_ids = None
        finally:
            self._vector_lock.release()

    def _maybe_retry_dense(self) -> None:
        if time.monotonic() - self._last_dense_attempt >= self.retry_s:
            threading.Thread(target=self.sync_vectors, name="vault-embed", daemon=True).start()

    # ------------------------------------------------------------------ search
    def search(self, query: str, k: int = 5, mode: SearchMode = "hybrid", folder: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        snap = self._snapshot
        warnings: list[str] = []
        prefix = f"{folder.strip('/')}/" if folder else None
        allowed = {c.id: c for c in snap.children if prefix is None or c.path.startswith(prefix)}
        candidates = max(50, k * 10)
        rankings: dict[str, list[str]] = {}

        dense_ranking: list[str] | None = None
        if mode in ("hybrid", "dense"):
            dense_ranking, dense_warning = self._dense_ranking(query, allowed, candidates, prefix)
            if dense_warning:
                warnings.append(dense_warning)
            if dense_ranking is not None:
                rankings["dense"] = dense_ranking
        if mode in ("hybrid", "bm25") or dense_ranking is None:  # dense-only falls back to BM25
            rankings["bm25"] = self._bm25_ranking(query, snap, allowed, candidates)
        effective = "bm25" if dense_ranking is None else "hybrid" if mode == "hybrid" else "dense"
        results = self._fuse(rankings, allowed, snap, k)
        return {
            "query": query,
            "requested_mode": mode,
            "mode": effective,
            "results": results,
            "warnings": warnings,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def past_decisions(
        self, query: str, limit: int = MAX_PAST_DECISIONS, today: dt.date | None = None
    ) -> list[DecisionRecord]:
        """Decision notes on the topic of `query`, best first (or the latest, for "what have we decided?")."""
        snap = self._snapshot
        today = today or dt.date.today()
        terms = topic_terms(query)
        scored: list[tuple[tuple[int, int], DecisionRecord]] = []
        if terms:
            for path, record in snap.decisions.items():
                match = decision_matches(terms, *snap.decision_words[path])
                if match is not None:
                    scored.append((match, record))
        elif any(word in _TOKEN_RE.findall(query.lower()) for word in _DECISION_WORDS):
            scored = [((0, 0), record) for record in snap.decisions.values()]
        scored.sort(key=lambda item: (item[0], item[1].decided or "", item[1].path), reverse=True)
        return [record.with_review_state(today) for _, record in scored[:limit]]

    @staticmethod
    def _bm25_ranking(query: str, snap: _Snapshot, allowed: dict[str, ChildChunk], candidates: int) -> list[str]:
        # "What do my notes say about X?" is about X: question words only count when nothing else is left.
        tokens = topic_terms(query) or bm25_tokens(query)
        if snap.bm25 is None or not tokens:
            return []
        scores = snap.bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], snap.children[i].id))
        return [snap.children[i].id for i in order if scores[i] > 0 and snap.children[i].id in allowed][:candidates]

    def _dense_ranking(
        self, query: str, allowed: dict[str, ChildChunk], candidates: int, prefix: str | None
    ) -> tuple[list[str] | None, str | None]:
        if self.store is None:
            return None, self._store_warning or "no vector store configured; using keyword search (BM25) only"
        error = self._dense_error  # read once: the retry thread may clear it concurrently
        if error:
            self._maybe_retry_dense()
            return None, f"semantic search unavailable ({error}); using keyword search (BM25) only"
        wanted = {point_id(c.id, c.content_hash) for c in allowed.values()}
        pending = len(wanted - self._embedded_ids)
        warning = None
        if pending:
            self._maybe_retry_dense()
            warning = f"{pending} of {len(wanted)} chunks are not embedded yet; their semantic matches are missing"
        try:
            vector = self.embedder.embed_query(query)
            hits = self.store.search(vector, candidates * 2, folder=prefix.rstrip("/") if prefix else None)
        except (EmbeddingError, VectorStoreError) as exc:
            self._dense_error = str(exc)  # the next sync re-reads the store's ids
            return None, f"semantic search unavailable ({exc}); using keyword search (BM25) only"
        ranking: list[str] = []
        for hit in hits:
            child = allowed.get(str(hit.payload.get("chunk_id", "")))
            if child is not None and point_id(child.id, child.content_hash) == hit.id and child.id not in ranking:
                ranking.append(child.id)
        return ranking[:candidates], warning

    @staticmethod
    def _fuse(
        rankings: dict[str, list[str]], allowed: dict[str, ChildChunk], snap: _Snapshot, k: int
    ) -> list[dict[str, Any]]:
        fused: dict[str, float] = {}
        ranks: dict[str, dict[str, int]] = {}
        for source, ids in rankings.items():
            for rank, child_id in enumerate(ids, start=1):
                fused[child_id] = fused.get(child_id, 0.0) + 1.0 / (RRF_K + rank)
                ranks.setdefault(child_id, {})[source] = rank
        best: dict[str, tuple[float, str]] = {}
        for child_id, score in fused.items():
            parent_id = allowed[child_id].parent_id
            if parent_id not in best or score > best[parent_id][0]:
                best[parent_id] = (score, child_id)
        ordered = sorted(best.items(), key=lambda item: (-item[1][0], item[0]))[:k]
        results = []
        for position, (parent_id, (score, child_id)) in enumerate(ordered, start=1):
            parent, child = snap.parents[parent_id], allowed[child_id]
            results.append(
                {
                    "rank": position,
                    "score": round(score, 6),
                    "path": parent.path,
                    "title": snap.titles.get(parent.path, PurePosixPath(parent.path).stem),
                    "heading": child.heading,
                    "chunk_id": parent.id,
                    "child_id": child.id,
                    "text": parent.text,
                    "snippet": child.text,
                    "metadata": snap.metadata.get(parent.path, {}),
                    "decision": snap.decisions.get(parent.path),
                    "bm25_rank": ranks[child_id].get("bm25"),
                    "dense_rank": ranks[child_id].get("dense"),
                    "citation": {"path": parent.path, "heading": child.heading, "chunk_id": parent.id},
                }
            )
        return results

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        with self._lock:
            docs = list(self._docs.values())
        snap = self._snapshot
        wanted = {point_id(c.id, c.content_hash) for c in snap.children}
        return {
            "files": len(docs),
            "parents": len(snap.parents),
            "children": len(snap.children),
            "embedded": len(wanted & self._embedded_ids),
            "errors": {d.path: d.error for d in docs if d.error},
            "file_warnings": {d.path: d.warnings for d in docs if d.warnings},
            "embedder": self.embedder.name,
            "vector_store": self.store.name if self.store else None,
            "tokenizer": self.tokenizer.name,
            "dense_available": self.store is not None and self._dense_error is None,
            "dense_error": self._dense_error or (self._store_warning if self.store is None else None),
            "last_indexed_at": self.last_indexed_at,
        }
