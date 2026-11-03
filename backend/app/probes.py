"""Dependency probes used by `/api/health`.

Each probe answers "is this dependency usable right now?" and never raises: failures become a status
(PRD R3, never crash on missing services). Probes are behind the `DependencyProbe` protocol so tests can
swap in fakes and never touch the network, a GPU or Docker.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from enum import StrEnum
from typing import Any, Protocol

import httpx
from loguru import logger
from pydantic import BaseModel

from app.config import DeepProvider, Settings


class DependencyState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class DependencyStatus(BaseModel):
    name: str
    state: DependencyState
    detail: str
    required: bool = True
    info: dict[str, Any] = {}


class DependencyProbe(Protocol):
    name: str
    required: bool

    async def check(self) -> DependencyStatus: ...


class OllamaProbe:
    """Checks the Ollama server is reachable and the configured chat/embedding models are pulled."""

    name = "ollama"
    required = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def check(self) -> DependencyStatus:
        url = f"{self._settings.ollama_base_url}/api/tags"
        try:
            response = await self._client.get(url, timeout=self._settings.health_probe_timeout_s)
            response.raise_for_status()
            payload = response.json()
            models = {str(m.get("name", "")) for m in payload.get("models", []) if isinstance(m, dict)}
        except (httpx.HTTPError, ValueError, AttributeError, TypeError) as exc:
            return DependencyStatus(
                name=self.name,
                required=self.required,
                state=DependencyState.UNAVAILABLE,
                detail=f"Ollama not reachable at {self._settings.ollama_base_url} ({type(exc).__name__})",
            )
        wanted = [self._settings.ollama_chat_model, self._settings.ollama_embed_model]
        missing = [m for m in wanted if not _model_present(m, models)]
        loaded = await self._loaded()
        in_vram = ", ".join("{} {} GB".format(m["name"], m["vram_gb"]) for m in loaded)
        vram = f"; in VRAM: {in_vram}" if loaded else ""
        if missing:
            return DependencyStatus(
                name=self.name,
                state=DependencyState.DEGRADED,
                detail=f"Ollama is running but these models are not pulled: {', '.join(missing)}",
                info={"missing_models": missing, "loaded": loaded},
            )
        return DependencyStatus(
            name=self.name,
            state=DependencyState.OK,
            detail=f"Ollama is running{vram}",
            info={"models": wanted, "loaded": loaded},
        )

    async def _loaded(self) -> list[dict[str, Any]]:
        """Models Ollama holds in memory (`/api/ps`) and their VRAM. The GPU may be shared with other apps."""
        try:
            response = await self._client.get(
                f"{self._settings.ollama_base_url}/api/ps", timeout=self._settings.health_probe_timeout_s
            )
            response.raise_for_status()
            raw = response.json().get("models", [])
        except (httpx.HTTPError, ValueError, AttributeError):
            return []
        gib = 1024**3
        return [
            {"name": str(m.get("name", "")), "vram_gb": round(float(m.get("size_vram") or 0) / gib, 1)}
            for m in raw
            if isinstance(m, dict)
        ]


def _model_present(model: str, available: set[str]) -> bool:
    # Ollama reports "nomic-embed-text:latest" for a model pulled as "nomic-embed-text".
    return model in available or (":" not in model and f"{model}:latest" in available)


class QdrantProbe:
    """Checks Qdrant answers on its REST port. Not required: retrieval falls back to BM25 only."""

    name = "qdrant"
    required = False

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def check(self) -> DependencyStatus:
        base = f"http://{self._settings.qdrant_host}:{self._settings.qdrant_port}"
        try:
            response = await self._client.get(f"{base}/", timeout=self._settings.health_probe_timeout_s)
            response.raise_for_status()
            version = str(response.json().get("version", "unknown"))
        except (httpx.HTTPError, ValueError) as exc:
            return DependencyStatus(
                name=self.name,
                state=DependencyState.UNAVAILABLE,
                detail=f"Qdrant not reachable at {base} ({type(exc).__name__}); search will use BM25 only",
                required=self.required,
            )
        return DependencyStatus(
            name=self.name,
            state=DependencyState.OK,
            detail=f"Qdrant {version} is running",
            required=self.required,
            info={"version": version},
        )


class CloudProvidersProbe:
    """Reports which cloud providers have credentials, from config only (no network calls, no secrets)."""

    name = "cloud"
    required = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self) -> DependencyStatus:
        s = self._settings
        configured = {
            DeepProvider.CLAUDE_SDK.value: s.provider_configured(DeepProvider.CLAUDE_SDK),
            DeepProvider.ANTHROPIC.value: s.provider_configured(DeepProvider.ANTHROPIC),
            DeepProvider.GEMINI.value: s.provider_configured(DeepProvider.GEMINI),
        }
        effective = s.effective_deep_provider()
        info = {
            "cloud_allowed": s.cloud_allowed,
            "deep_provider": s.deep_provider.value,
            "effective_deep_provider": effective.value,
            "configured": configured,
        }
        if not s.cloud_allowed:
            return DependencyStatus(
                name=self.name,
                state=DependencyState.NOT_CONFIGURED,
                detail="Cloud is disabled; all agents run locally",
                required=self.required,
                info=info,
            )
        if s.deep_provider is not DeepProvider.OLLAMA and effective is DeepProvider.OLLAMA:
            return DependencyStatus(
                name=self.name,
                state=DependencyState.DEGRADED,
                detail=f"{s.deep_provider.value} has no credentials; deep-work agents fall back to Ollama",
                required=self.required,
                info=info,
            )
        return DependencyStatus(
            name=self.name,
            state=DependencyState.OK,
            detail=f"Deep-work agents use {effective.value}",
            required=self.required,
            info=info,
        )


class GpuProbe:
    """Reports an NVIDIA GPU and its VRAM through NVML (optional `nvidia-ml-py`). Never required: CPU works."""

    name = "gpu"
    required = False

    def __init__(self, nvml: Any | None = None) -> None:
        self._nvml = nvml

    def _load_nvml(self) -> Any | None:
        if self._nvml is not None:
            return self._nvml
        try:
            return importlib.import_module("pynvml")
        except ImportError:
            return None

    async def check(self) -> DependencyStatus:
        nvml = self._load_nvml()
        if nvml is None:
            return DependencyStatus(
                name=self.name,
                state=DependencyState.NOT_CONFIGURED,
                detail="GPU check unavailable (install the 'gpu' extra); models run on CPU if needed",
                required=self.required,
            )
        try:
            return await asyncio.to_thread(self._query, nvml)
        except Exception as exc:  # NVML raises its own error types; any failure means "no usable GPU".
            return DependencyStatus(
                name=self.name,
                state=DependencyState.UNAVAILABLE,
                detail=f"No NVIDIA GPU detected ({type(exc).__name__}); models run on CPU",
                required=self.required,
            )

    def _query(self, nvml: Any) -> DependencyStatus:
        nvml.nvmlInit()
        try:
            handle = nvml.nvmlDeviceGetHandleByIndex(0)
            name = nvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            mem = nvml.nvmlDeviceGetMemoryInfo(handle)
        finally:
            nvml.nvmlShutdown()
        gib = 1024**3
        used_gb, total_gb = round(mem.used / gib, 1), round(mem.total / gib, 1)
        return DependencyStatus(
            name=self.name,
            state=DependencyState.OK,
            detail=f"{name}: {used_gb}/{total_gb} GB VRAM in use",
            required=self.required,
            info={"device": name, "vram_used_gb": used_gb, "vram_total_gb": total_gb},
        )


class StorageProbe:
    """Checks the workspace data and vault folders exist and are writable."""

    name = "storage"
    required = True

    def __init__(self, settings: Settings) -> None:
        self._dirs = {"data": settings.workspace_data_dir(), "vault": settings.workspace_vault_dir()}

    async def check(self) -> DependencyStatus:
        problems = [
            f"{label} folder {path} is missing or not writable"
            for label, path in self._dirs.items()
            if not (path.is_dir() and os.access(path, os.W_OK))
        ]
        info = {label: str(path) for label, path in self._dirs.items()}
        if problems:
            return DependencyStatus(
                name=self.name, state=DependencyState.UNAVAILABLE, detail="; ".join(problems), info=info
            )
        return DependencyStatus(name=self.name, state=DependencyState.OK, detail="Workspace folders OK", info=info)


async def run_probes(probes: list[DependencyProbe], timeout_s: float) -> list[DependencyStatus]:
    """Run all probes concurrently. A probe that hangs or raises is reported as unavailable."""

    async def guarded(probe: DependencyProbe) -> DependencyStatus:
        try:
            return await asyncio.wait_for(probe.check(), timeout=timeout_s)
        except TimeoutError:
            detail = f"health check timed out after {timeout_s:g}s"
        except Exception as exc:
            logger.exception("Health probe {} failed", probe.name)
            detail = f"health check failed ({type(exc).__name__})"
        return DependencyStatus(
            name=probe.name, state=DependencyState.UNAVAILABLE, detail=detail, required=probe.required
        )

    return list(await asyncio.gather(*(guarded(p) for p in probes)))
