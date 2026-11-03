"""One workspace's vault: manager + hybrid index + watcher, built from settings with fakes for tests."""

from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path

from loguru import logger

from app.config import Settings
from app.engine.chunking import get_tokenizer
from app.engine.embeddings import Embedder, FakeEmbedder, OllamaEmbedder
from app.engine.hybrid_rag import HybridIndex
from app.engine.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorStore, VectorStoreError
from app.vault.manager import VaultManager
from app.vault.watcher import watch_vault

SAMPLE_VAULT_DIR_NAME = "vault"


def build_embedder(settings: Settings) -> Embedder:
    if settings.embed_provider == "fake":
        return FakeEmbedder()
    return OllamaEmbedder(settings.ollama_base_url, settings.ollama_embed_model)


def build_store(settings: Settings, workspace_id: str) -> tuple[VectorStore | None, str | None]:
    """(store, warning). `auto` uses Qdrant when it answers, else the in-memory store (PRD R3)."""
    if settings.vector_store == "memory":
        return InMemoryVectorStore(), None
    base = f"http://{settings.qdrant_host}:{settings.qdrant_port}"
    qdrant = QdrantVectorStore(base, f"founderos_{workspace_id}", timeout_s=max(settings.health_probe_timeout_s, 5.0))
    try:
        qdrant.ping()
        return qdrant, None
    except VectorStoreError as exc:
        if settings.vector_store == "qdrant":
            logger.warning("Qdrant unavailable at {} ({}); search uses BM25 only", base, exc)
            return qdrant, None  # keep trying Qdrant; the index retries and reports the error meanwhile
        logger.warning("Qdrant unavailable at {}; using the in-memory vector store", base)
        return InMemoryVectorStore(), f"Qdrant not reachable at {base}; vectors are kept in memory"


class VaultService:
    def __init__(
        self,
        settings: Settings,
        workspace_id: str | None = None,
        *,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
    ) -> None:
        self.settings = settings
        self.workspace_id = workspace_id or settings.workspace_id
        self.vault = VaultManager(settings.workspace_vault_dir(self.workspace_id))
        store_note: str | None = None
        if store is None:
            store, store_note = build_store(settings, self.workspace_id)
        self.store_note = store_note
        self.index = HybridIndex(
            self.vault, embedder or build_embedder(settings), store, get_tokenizer(settings.tokenizer)
        )
        self.ready = threading.Event()
        self._start_lock = threading.Lock()
        self._started = False
        self.watching = False
        self._stop: asyncio.Event | None = None
        self._watch_task: asyncio.Task[None] | None = None

    def seed_sample_vault(self) -> int:
        """Copy `sample_data/vault/` into an empty vault (demo). Returns the number of files copied."""
        source = self.settings.sample_data_path() / SAMPLE_VAULT_DIR_NAME
        if not source.is_dir() or self.vault.iter_files():
            return 0
        copied = 0
        for path in sorted(source.rglob("*")):
            if path.is_file():
                target = self.vault.root / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                copied += 1
        logger.info("Copied {} sample notes into {}", copied, self.vault.root)
        return copied

    def start(self) -> None:
        """Build the index (keyword search is ready first), then embed. Runs in a worker thread at startup."""
        try:
            self.vault.ensure_layout()
            if self.settings.auto_load_sample_vault:
                self.seed_sample_vault()
            self.index.refresh(dense=False)
            logger.info(
                "Vault indexed: {}", {k: v for k, v in self.index.status().items() if k in ("files", "children")}
            )
        except Exception as exc:  # PRD R3: the API still answers (empty results + status shows the error)
            logger.exception("Vault indexing failed: {}", exc)
        finally:
            self.ready.set()
        self.index.sync_vectors()

    def ensure_started(self) -> None:
        """Run `start()` once (the app lifespan calls this in a thread; a lazily created service on first use)."""
        with self._start_lock:
            if self._started:
                return
            self._started = True
        self.start()

    def wait_ready(self, timeout_s: float = 60.0) -> bool:
        return self.ready.wait(timeout_s)

    def apply_changes(self, paths: set[str]) -> None:
        self.index.refresh(paths)

    async def start_watcher(self) -> None:
        self._stop = asyncio.Event()
        root: Path = self.vault.root
        root.mkdir(parents=True, exist_ok=True)
        self._watch_task = asyncio.create_task(
            watch_vault(root, self.apply_changes, self._stop, force_polling=self.settings.vault_watch_polling)
        )
        self.watching = True

    async def stop_watcher(self) -> None:
        if self._stop is not None and self._watch_task is not None:
            self._stop.set()
            try:
                await asyncio.wait_for(self._watch_task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                self._watch_task.cancel()
        self.watching = False
