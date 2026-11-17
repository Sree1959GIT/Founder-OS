"""M6a packaging scripts: `scripts/reset_demo.py` and `scripts/download_models.py` (no network, no Ollama)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import Settings

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --- reset_demo -----------------------------------------------------------------------------------------------------
def make_settings(tmp_path: Path) -> Settings:
    sample = tmp_path / "sample"
    (sample / "vault" / "decisions").mkdir(parents=True)
    (sample / "vault" / "decisions" / "2026-09-hire-two-sdrs.md").write_text("# SDRs\n", encoding="utf-8")
    (sample / "vault" / "profile").mkdir()
    (sample / "vault" / "profile" / "company.md").write_text("# Northwind\n", encoding="utf-8")
    return Settings(_env_file=None, data_dir=tmp_path / "data", vault_path=tmp_path / "vault", sample_data_dir=sample)


def test_reset_backs_up_then_restores_the_sample_vault_and_keeps_settings(tmp_path: Path) -> None:
    reset_demo = load("reset_demo")
    settings = make_settings(tmp_path)
    vault, data = settings.workspace_vault_dir("default"), settings.workspace_data_dir("default")
    (vault / "decisions").mkdir(parents=True)
    (vault / "decisions" / "2026-11-06-open-dubai-office.md").write_text("# test memo\n", encoding="utf-8")
    (data / "uploads").mkdir(parents=True)
    (data / "founder.duckdb").write_bytes(b"db")
    (data / "uploads" / "rw8_test.csv").write_text("a\n", encoding="utf-8")
    (data / "ui_settings.json").write_text('{"team_approval": "never"}', encoding="utf-8")

    backup = reset_demo.reset(settings, "default", now=datetime(2026, 11, 17, 3, 0, tzinfo=UTC))

    assert backup.name == "reset-20261117-030000-default"
    assert (backup / "vault" / "decisions" / "2026-11-06-open-dubai-office.md").is_file()  # moved, not deleted
    assert (backup / "data" / "founder.duckdb").read_bytes() == b"db"
    files = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file())
    assert files == ["decisions/2026-09-hire-two-sdrs.md", "profile/company.md"]
    assert sorted(p.name for p in data.iterdir()) == ["ui_settings.json"]  # the DuckDB file reloads on start
    assert json.loads((data / "ui_settings.json").read_text(encoding="utf-8")) == {"team_approval": "never"}


def test_reset_can_reset_settings_too_and_works_on_an_empty_workspace(tmp_path: Path) -> None:
    reset_demo = load("reset_demo")
    settings = make_settings(tmp_path)
    data = settings.workspace_data_dir("default")
    data.mkdir(parents=True)
    (data / "ui_settings.json").write_text("{}", encoding="utf-8")
    reset_demo.reset(settings, "default", keep_settings=False)
    assert list(data.iterdir()) == []
    reset_demo.reset(settings, "other")  # nothing there yet: still a clean demo vault
    assert (settings.workspace_vault_dir("other") / "profile" / "company.md").is_file()


def test_reset_refuses_while_the_backend_is_running(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    reset_demo = load("reset_demo")
    monkeypatch.setattr(reset_demo, "port_in_use", lambda port: True)
    monkeypatch.setattr(reset_demo, "reset", lambda *a, **k: pytest.fail("nothing may move"))
    monkeypatch.setattr(sys, "argv", ["reset_demo.py", "--yes"])
    assert reset_demo.main() == 1
    assert "port 8000" in capsys.readouterr().out


def test_reset_rejects_a_bad_workspace_id(tmp_path: Path) -> None:
    settings, reset_demo = make_settings(tmp_path), load("reset_demo")
    for bad in ("../outside", "backups"):
        with pytest.raises(ValueError):
            reset_demo.reset(settings, bad)


# --- download_models ------------------------------------------------------------------------------------------------
def test_models_to_pull_come_from_config() -> None:
    dm = load("download_models")
    settings = Settings(_env_file=None, ollama_chat_model="qwen3:8b", ollama_embed_model="nomic-embed-text")
    assert dm.ollama_models(settings) == ["qwen3:8b", "nomic-embed-text"]
    both = Settings(_env_file=None, fast_lane_model="qwen3:8b")
    assert dm.ollama_models(both) == ["qwen3:8b", "nomic-embed-text"]  # the same model is pulled once


def _transport(pulled: list[str], pulls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n} for n in pulled]})
        if request.url.path == "/api/pull":
            pulls.append(json.loads(request.content)["model"])
            lines = [{"status": "pulling manifest"}, {"status": "downloading", "total": 10, "completed": 5}]
            lines.append({"status": "success"})
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_pulls_only_the_missing_model_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    dm = load("download_models")
    pulls: list[str] = []
    client = httpx.Client(transport=_transport(["qwen3:8b"], pulls), base_url="http://ollama:11434")
    monkeypatch.setattr(dm.httpx, "get", lambda url, **k: client.get(url.replace("http://ollama:11434", "")))
    monkeypatch.setattr(
        dm.httpx, "stream", lambda method, url, **k: client.stream(method, url.replace("http://ollama:11434", ""), **k)
    )
    settings = Settings(_env_file=None, ollama_base_url="http://ollama:11434")
    assert dm.do_ollama(settings, check=False) is True
    assert pulls == ["nomic-embed-text"]
    assert dm.do_ollama(settings, check=True) is False  # check mode only reports the missing one
    assert pulls == ["nomic-embed-text"]


def test_ollama_down_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    dm = load("download_models")

    def down(*a: Any, **k: Any) -> Any:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(dm.httpx, "get", down)
    assert dm.do_ollama(Settings(_env_file=None), check=False) is False
    assert "not answering" in capsys.readouterr().out
