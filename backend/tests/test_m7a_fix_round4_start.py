"""Founder F8c: start the backend the way run.bat does (a new process running
`python -m uvicorn --factory app.main:create_app` in backend/, inheriting the environment that PowerShell's `$env:`
set before `.\\run.bat`), and check that the backend says which slow-agent limit it really uses.

No network, Ollama, Docker or GPU: every service is pointed at a dead local port or a fake, and the data lives in a
temporary folder."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from app.main import slow_offer_line

BACKEND = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_f8c_the_backend_started_like_run_bat_logs_the_slow_limit_from_the_environment(tmp_path: Path) -> None:
    port, dead = _free_port(), _free_port()
    env = {
        **os.environ,
        # What the founder typed in PowerShell before .\run.bat:
        "CLOUD_SLOW_AFTER_S": "3",
        "CLOUD_SLOW_MIN_S": "0",
        # Offline and isolated (the founder's .env is not read for these: an environment variable beats it):
        "DATA_DIR": str(tmp_path / "data"),
        "VAULT_PATH": str(tmp_path / "vault"),
        "OLLAMA_BASE_URL": f"http://127.0.0.1:{dead}",
        "VECTOR_STORE": "memory",
        "EMBED_PROVIDER": "fake",
        "VOICE_ENABLED": "false",
        "VAULT_WATCH": "false",
        "AUTO_LOAD_SAMPLE_DATA": "false",
        "FX_RATES_URL": f"http://127.0.0.1:{dead}/latest/USD",
        "PYTHONUTF8": "1",
    }
    log = tmp_path / "backend.log"
    with log.open("w", encoding="utf-8") as out:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "--factory",
                "app.main:create_app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=BACKEND,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            healthy = False
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    healthy = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2).status_code == 200
                except httpx.HTTPError:
                    healthy = False
                if healthy and "Slow-agent offer" in log.read_text(encoding="utf-8", errors="replace"):
                    break
                time.sleep(0.3)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
    text = log.read_text(encoding="utf-8", errors="replace")
    assert healthy, text[-3000:]
    assert "Slow-agent offer after 3 s (min 0 s; from the environment: CLOUD_SLOW_AFTER_S, CLOUD_SLOW_MIN_S)" in text


def test_f8c_the_startup_line_names_the_limit_and_its_source(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("CLOUD_SLOW_AFTER_S", raising=False)
    monkeypatch.delenv("CLOUD_SLOW_MIN_S", raising=False)
    assert slow_offer_line(45, 15) == "Slow-agent offer after 45 s (min 15 s; from .env or the default)"
    assert slow_offer_line(0, 15) == "Slow-agent offer off (CLOUD_SLOW_AFTER_S is 0)"
    monkeypatch.setenv("CLOUD_SLOW_AFTER_S", "3")
    assert slow_offer_line(3, 0) == "Slow-agent offer after 3 s (min 0 s; from the environment: CLOUD_SLOW_AFTER_S)"
