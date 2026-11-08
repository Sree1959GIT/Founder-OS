"""`GET /api/health`: backend liveness plus the status of every external dependency."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, Request
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
async def health(request: Request, settings: SettingsDep, probes: ProbesDep) -> HealthResponse:
    """Always answers 200 while the backend is up; problems are reported per dependency (PRD R3)."""
    dependencies = await run_probes(probes, timeout_s=settings.health_probe_timeout_s + 1.0)
    orchestrator = getattr(request.app.state, "orchestrator", None)
    for dependency in dependencies:  # Settings can change this while the app runs: the badge must show what is true
        if dependency.name == "cloud" and orchestrator is not None:
            allowed = bool(orchestrator.router.cloud_allowed)
            dependency.info["cloud_allowed"] = allowed
            keys = any(bool(v) for v in dict(dependency.info.get("configured") or {}).values())
            dependency.info["cloud_usable"] = allowed and keys
            # The strip and the privacy badge read the same facts (founder review 35).
            if not allowed:
                dependency.state = DependencyState.NOT_CONFIGURED
                dependency.detail = "Cloud is off; all agents run locally"
            elif not keys:
                dependency.state = DependencyState.DEGRADED
                dependency.detail = "Cloud is allowed, but no provider has a key: every agent runs locally"

    return HealthResponse(
        status=overall_status(dependencies),
        version=__version__,
        workspace_id=settings.workspace_id,
        currency=settings.currency,
        checked_at=datetime.now(UTC),
        dependencies=dependencies,
    )
