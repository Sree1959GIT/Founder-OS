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


# --- Y3: a Qdrant that already answers (another clone's container) ---------------------------------------------------
@pytest.mark.parametrize("name", ["setup.bat", "run.bat"])
def test_a_running_qdrant_skips_compose_with_no_warning(name: str) -> None:
    text = (SCRIPTS.parent / name).read_bytes().decode("ascii")
    probe = text.index("http://localhost:6333/readyz")
    assert probe < text.index("docker compose up -d qdrant")
    block = text[probe : text.index("where docker", probe)]
    assert "[OK] Qdrant already running" in block and "goto :" in block and "[WARN]" not in block
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")  # CRLF, or cmd loses its goto labels


# --- F1 (M7a gate): run.bat runs ensure_secret.py on every start ------------------------------------------------------
def _run_batch(text: str, failing: set[str]) -> list[str]:
    """A small cmd.exe control-flow model: `if [not] errorlevel|exist|defined ... (`, `) else (`, `)`, `goto :label`,
    `exit /b`. A command "fails" (errorlevel 1) when it contains one of `failing`; every other command succeeds.
    Returns the commands that ran, in order."""
    lines = [line.strip() for line in text.split("\r\n")]
    labels = {line[1:].lower(): i for i, line in enumerate(lines) if line.startswith(":") and not line.startswith("::")}
    ran: list[str] = []
    errorlevel = 0

    def condition(words: list[str]) -> tuple[bool, list[str]]:
        negate = words[0].lower() == "not"
        if negate:
            words = words[1:]
        kind = words[0].lower()
        if kind == "errorlevel":
            value, rest = errorlevel >= int(words[1]), words[2:]
        elif kind in ("exist", "defined"):
            value, rest = kind == "exist", words[2:]  # files exist (set up already); NEED_SETUP is not defined
        else:
            raise AssertionError(f"unsupported if: {words}")
        return (not value) if negate else value, rest

    def skip_block(i: int) -> tuple[int, bool]:
        """From the line after `(`, find the closing line. Returns (index of closer, closer is `) else (`)."""
        depth = 0
        while True:
            line = lines[i]
            if line.startswith(")"):
                if depth == 0:
                    return i, line.endswith("(")
                if not line.endswith("("):
                    depth -= 1
            elif line.endswith("(") and not line.lower().startswith("rem"):
                depth += 1
            i += 1

    def command(line: str) -> int | None:
        """Runs one command; returns the next index for goto, -1 for exit, None to go on."""
        nonlocal errorlevel
        low = line.lower()
        if low.startswith("goto "):
            return labels[low.split()[1].lstrip(":")]
        if low.startswith("exit"):
            return -1
        ran.append(line)
        if not low.startswith(("echo", "set ", "rem", "setlocal", "endlocal", "cd ")):
            errorlevel = 1 if any(f in line for f in failing) else 0
        return None

    i, stack = 0, []  # stack: True while inside a taken `if (` block
    while 0 <= i < len(lines):
        line, low = lines[i], lines[i].lower()
        if not line or low.startswith(("rem", "@echo", ":")):
            i += 1
            continue
        if line.startswith(")"):
            taken = stack.pop()
            if line.endswith("(") and taken:  # `) else (` after a taken branch: skip the else
                end, _ = skip_block(i + 1)
                i = end + 1
                continue
            if line.endswith("("):
                stack.append(True)
            i += 1
            continue
        if low.startswith("if "):
            value, rest = condition(line.split()[1:])
            if rest == ["("]:
                if value:
                    stack.append(True)
                    i += 1
                else:
                    end, has_else = skip_block(i + 1)
                    if has_else:
                        stack.append(False)
                    i = end + 1
                continue
            if value:
                jump = command(" ".join(rest))
                if jump is not None:
                    if jump == -1:
                        break
                    i = jump
                    continue
            i += 1
            continue
        jump = command(line)
        if jump == -1:
            break
        i = jump if jump is not None else i + 1
    return ran


@pytest.mark.parametrize(
    "failing",
    [
        set(),  # Qdrant already answers on 6333: `goto :preflight` straight away (the founder's F1 path)
        {"readyz"},  # Qdrant down, Docker running: compose starts it
        {"readyz", "where docker"},  # no Docker
        {"readyz", "docker info"},  # Docker Desktop not running
        {"readyz", "docker compose"},  # compose failed
    ],
    ids=["qdrant-running", "qdrant-started", "no-docker", "docker-stopped", "compose-failed"],
)
def test_run_bat_runs_ensure_secret_once_on_every_path(failing: set[str]) -> None:
    text = (SCRIPTS.parent / "run.bat").read_bytes().decode("ascii")
    ran = _run_batch(text, failing)
    secret = [i for i, line in enumerate(ran) if "ensure_secret.py" in line]
    preflight = [i for i, line in enumerate(ran) if "preflight.py" in line]
    assert len(secret) == 1, ran
    assert preflight and secret[0] < preflight[0]
    assert any("uvicorn" in line for line in ran)  # and the start goes on
    assert ("docker compose up -d qdrant" in " ".join(ran)) == (failing == {"readyz"} or "docker compose" in failing)


def test_batch_model_sees_the_old_unreachable_line() -> None:
    """The model really follows `goto`: the M7a run.bat (line after `goto :preflight` in the block) never ran it."""
    old = (
        "@echo off\r\ncurl.exe http://localhost:6333/readyz\r\nif not errorlevel 1 (\r\n  echo [OK] Qdrant\r\n"
        '  goto :preflight\r\n".venv\\Scripts\\python.exe" scripts\\ensure_secret.py\r\n)\r\nwhere docker\r\n'
        ':preflight\r\n".venv\\Scripts\\python.exe" scripts\\preflight.py\r\nexit /b 0\r\n'
    )
    assert not any("ensure_secret" in line for line in _run_batch(old, set()))
    assert not any("ensure_secret" in line for line in _run_batch(old, {"readyz"}))
