"""FastAPI dependencies. Override these in tests (`app.dependency_overrides`) to inject fakes."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
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


class FinanceServices:
    """Per-workspace financial engine objects, shared across requests (the scenario engine caches drivers)."""

    def __init__(self, settings: Settings) -> None:
        self.db = FinanceDB(settings.workspace_data_dir())
        self.metrics = MetricsEngine(self.db, settings.currency)
        self.scenario = ScenarioEngine(self.db, settings.currency)
        self.calibration = CalibrationStore(settings.workspace_data_dir())


def get_finance(request: Request, settings: SettingsDep) -> FinanceServices:
    registry: dict[str, FinanceServices] = request.app.state.finance
    key = str(settings.workspace_data_dir())
    services = registry.get(key)
    if services is None:
        services = registry.setdefault(key, FinanceServices(settings))
    return services


FinanceDep = Annotated[FinanceServices, Depends(get_finance)]
