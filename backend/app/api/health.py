"""`GET /api/health`: backend liveness plus the status of every external dependency."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.deps import ProbesDep, SettingsDep
from app.probes import DependencyState, DependencyStatus, run_probes

router = APIRouter(tags=["health"])


class OverallStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class HealthResponse(BaseModel):
    status: OverallStatus
    version: str
    workspace_id: str
    currency: str
    checked_at: datetime
    dependencies: list[DependencyStatus]


def overall_status(dependencies: list[DependencyStatus]) -> OverallStatus:
    """Degraded when any required dependency is not OK, or any optional one is degraded or down.

    `not_configured` on an optional dependency (e.g. cloud switched off) is a normal state, not a problem.
    """
    for dep in dependencies:
        if dep.required and dep.state is not DependencyState.OK:
            return OverallStatus.DEGRADED
        if not dep.required and dep.state in (DependencyState.DEGRADED, DependencyState.UNAVAILABLE):
            return OverallStatus.DEGRADED
    return OverallStatus.OK


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep, probes: ProbesDep) -> HealthResponse:
    """Always answers 200 while the backend is up; problems are reported per dependency (PRD R3)."""
    dependencies = await run_probes(probes, timeout_s=settings.health_probe_timeout_s + 1.0)
    return HealthResponse(
        status=overall_status(dependencies),
        version=__version__,
        workspace_id=settings.workspace_id,
        currency=settings.currency,
        checked_at=datetime.now(UTC),
        dependencies=dependencies,
    )
