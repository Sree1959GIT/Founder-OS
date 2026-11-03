from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings
from app.deps import get_probes
from app.engine.duckdb_engine import FinanceDB
from app.engine.ingest import ingest_directory
from app.main import create_app
from app.probes import DependencyProbe, DependencyState, DependencyStatus


class FakeProbe:
    """Scripted probe for API tests."""

    def __init__(self, name: str, state: DependencyState, required: bool = True) -> None:
        self.name = name
        self.required = required
        self._state = state

    async def check(self) -> DependencyStatus:
        return DependencyStatus(name=self.name, state=self._state, detail="fake", required=self.required)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not see the developer's or CI runner's real config or secrets (e.g. GEMINI_API_KEY)."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None: never read a developer's real .env during tests.
    return Settings(
        _env_file=None, data_dir=tmp_path / "data", vault_path=tmp_path / "vault", auto_load_sample_data=False
    )


@pytest.fixture
def make_client(settings: Settings) -> Iterator[object]:
    clients: list[TestClient] = []

    def _make(probes: list[DependencyProbe]) -> TestClient:
        app = create_app(settings)
        app.dependency_overrides[get_probes] = lambda: probes
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture(scope="session")
def loaded_db(tmp_path_factory: pytest.TempPathFactory) -> FinanceDB:
    """The Northwind sample data loaded once per test session. Tests must not write to it."""
    db = FinanceDB(tmp_path_factory.mktemp("finance") / "default")
    ingest_directory(db, PROJECT_ROOT / "sample_data")
    return db


@pytest.fixture
def empty_db(tmp_path: Path) -> FinanceDB:
    return FinanceDB(tmp_path / "ws")
