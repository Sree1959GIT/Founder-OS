from __future__ import annotations

from app.probes import DependencyState
from tests.conftest import FakeProbe


def test_health_ok(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client(
        [
            FakeProbe("ollama", DependencyState.OK),
            FakeProbe("cloud", DependencyState.NOT_CONFIGURED, required=False),
        ]
    )
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["workspace_id"] == "default"
    assert [d["name"] for d in body["dependencies"]] == ["ollama", "cloud"]


def test_health_degraded_when_required_dependency_down(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client([FakeProbe("ollama", DependencyState.UNAVAILABLE)])
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_health_degraded_when_optional_dependency_down(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client(
        [FakeProbe("ollama", DependencyState.OK), FakeProbe("qdrant", DependencyState.UNAVAILABLE, False)]
    )
    assert client.get("/api/health").json()["status"] == "degraded"


def test_startup_creates_workspace_dirs(make_client, settings) -> None:  # type: ignore[no-untyped-def]
    make_client([])
    assert settings.workspace_data_dir().is_dir()
    assert settings.workspace_vault_dir().is_dir()


def test_cors_allows_frontend_origin_only(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client([])
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    blocked = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in blocked.headers


def test_real_probes_do_not_crash_without_services(settings) -> None:  # type: ignore[no-untyped-def]
    """End-to-end with the real probes, pointed at closed ports: must still answer 200 (PRD R3)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings.ollama_base_url = "http://127.0.0.1:1"
    settings.qdrant_port = 1
    settings.health_probe_timeout_s = 0.5
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()
    states = {d["name"]: d["state"] for d in body["dependencies"]}
    assert body["status"] == "degraded"
    assert states["ollama"] == "unavailable"
    assert states["qdrant"] == "unavailable"
    assert states["cloud"] == "not_configured"
