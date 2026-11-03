"""FastAPI dependencies. Override these in tests (`app.dependency_overrides`) to inject fakes."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.probes import CloudProvidersProbe, DependencyProbe, GpuProbe, OllamaProbe, QdrantProbe, StorageProbe

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The shared outbound HTTP client created in the app lifespan."""
    client: httpx.AsyncClient = request.app.state.http_client
    return client


def get_probes(
    settings: SettingsDep, client: Annotated[httpx.AsyncClient, Depends(get_http_client)]
) -> list[DependencyProbe]:
    return [
        OllamaProbe(settings, client),
        QdrantProbe(settings, client),
        CloudProvidersProbe(settings),
        GpuProbe(),
        StorageProbe(settings),
    ]


ProbesDep = Annotated[list[DependencyProbe], Depends(get_probes)]
