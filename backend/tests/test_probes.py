from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.probes import (
    CloudProvidersProbe,
    DependencyState,
    GpuProbe,
    OllamaProbe,
    QdrantProbe,
    StorageProbe,
    run_probes,
)


def client_for(handler: httpx.MockTransport | None = None, **routes: object) -> httpx.AsyncClient:
    def respond(request: httpx.Request) -> httpx.Response:
        body = routes.get(request.url.path)
        if body is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=body)

    return httpx.AsyncClient(transport=handler or httpx.MockTransport(respond))


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


async def test_ollama_ok_when_models_pulled(settings: Settings) -> None:
    tags = {"models": [{"name": "qwen2.5:7b-instruct-q4_K_M"}, {"name": "nomic-embed-text:latest"}]}
    async with client_for(**{"/api/tags": tags}) as client:
        status = await OllamaProbe(settings, client).check()
    assert status.state is DependencyState.OK
    assert status.required is True


async def test_ollama_degraded_when_model_missing(settings: Settings) -> None:
    async with client_for(**{"/api/tags": {"models": [{"name": "nomic-embed-text:latest"}]}}) as client:
        status = await OllamaProbe(settings, client).check()
    assert status.state is DependencyState.DEGRADED
    assert status.info["missing_models"] == ["qwen2.5:7b-instruct-q4_K_M"]


async def test_ollama_unavailable_when_down(settings: Settings) -> None:
    async with client_for() as client:
        status = await OllamaProbe(settings, client).check()
    assert status.state is DependencyState.UNAVAILABLE
    assert "localhost:11434" in status.detail


async def test_ollama_unavailable_on_bad_json(settings: Settings) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"not json"))
    async with client_for(transport) as client:
        status = await OllamaProbe(settings, client).check()
    assert status.state is DependencyState.UNAVAILABLE


async def test_qdrant_ok_and_down(settings: Settings) -> None:
    async with client_for(**{"/": {"title": "qdrant", "version": "1.12.0"}}) as client:
        ok = await QdrantProbe(settings, client).check()
    async with client_for() as client:
        down = await QdrantProbe(settings, client).check()
    assert ok.state is DependencyState.OK and ok.info["version"] == "1.12.0"
    assert down.state is DependencyState.UNAVAILABLE and down.required is False
    assert "BM25" in down.detail


async def test_cloud_probe_states() -> None:
    off = await CloudProvidersProbe(Settings(_env_file=None)).check()
    missing = await CloudProvidersProbe(
        Settings(_env_file=None, cloud_allowed=True, deep_provider="claude_sdk")
    ).check()
    on = await CloudProvidersProbe(
        Settings(_env_file=None, cloud_allowed=True, deep_provider="gemini", gemini_api_key="sk-test-SECRET")
    ).check()
    assert off.state is DependencyState.NOT_CONFIGURED
    assert missing.state is DependencyState.DEGRADED
    assert missing.info["effective_deep_provider"] == "ollama"
    assert on.state is DependencyState.OK
    assert on.info["configured"]["gemini"] is True
    assert "sk-test-SECRET" not in on.model_dump_json()  # secret value never reported


class FakeNvml:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.shutdown_called = False

    def nvmlInit(self) -> None:
        if self.fail:
            raise RuntimeError("NVML Shared Library Not Found")

    def nvmlDeviceGetHandleByIndex(self, index: int) -> int:
        return index

    def nvmlDeviceGetName(self, handle: int) -> bytes:
        return b"NVIDIA GeForce RTX 4070"

    def nvmlDeviceGetMemoryInfo(self, handle: int) -> SimpleNamespace:
        return SimpleNamespace(used=int(7.9 * 1024**3), total=12 * 1024**3)

    def nvmlShutdown(self) -> None:
        self.shutdown_called = True


async def test_gpu_probe_reports_vram() -> None:
    nvml = FakeNvml()
    status = await GpuProbe(nvml).check()
    assert status.state is DependencyState.OK
    assert status.info == {"device": "NVIDIA GeForce RTX 4070", "vram_used_gb": 7.9, "vram_total_gb": 12.0}
    assert nvml.shutdown_called


async def test_gpu_probe_without_gpu() -> None:
    status = await GpuProbe(FakeNvml(fail=True)).check()
    assert status.state is DependencyState.UNAVAILABLE
    assert status.required is False


class HangingProbe:
    name = "hang"
    required = False

    async def check(self):  # type: ignore[no-untyped-def]
        await asyncio.sleep(10)


class BrokenProbe:
    name = "broken"
    required = True

    async def check(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


async def test_run_probes_never_raises() -> None:
    results = await run_probes([HangingProbe(), BrokenProbe()], timeout_s=0.05)
    assert [r.state for r in results] == [DependencyState.UNAVAILABLE, DependencyState.UNAVAILABLE]
    assert "timed out" in results[0].detail and results[0].required is False
    assert "RuntimeError" in results[1].detail and results[1].required is True


@pytest.mark.parametrize("body", [["not", "an", "object"], {"models": ["x", 3]}, {"models": None}])
async def test_ollama_tolerates_unexpected_json(settings: Settings, body: object) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    async with client_for(transport) as client:
        status = await OllamaProbe(settings, client).check()
    assert status.state in (DependencyState.UNAVAILABLE, DependencyState.DEGRADED)


async def test_storage_probe(tmp_path) -> None:  # type: ignore[no-untyped-def]
    s = Settings(_env_file=None, data_dir=tmp_path / "data", vault_path=tmp_path / "vault")
    missing = await StorageProbe(s).check()
    s.workspace_data_dir().mkdir(parents=True)
    s.workspace_vault_dir().mkdir(parents=True)
    ok = await StorageProbe(s).check()
    assert missing.state is DependencyState.UNAVAILABLE and missing.required is True
    assert ok.state is DependencyState.OK
