"""`scripts/voice_scenarios.py` (the scripted RZ re-test) runs only on a PC with Ollama and the voice models.

Anywhere else, CI included, it must say why and exit 0 without starting a backend.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "voice_scenarios.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("voice_scenarios", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["voice_scenarios"] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def test_without_ollama_it_skips_cleanly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    module = load()
    monkeypatch.setattr(module, "ollama_up", lambda *a: False)
    monkeypatch.setattr(module.Backend, "start", lambda self: pytest.fail("no backend may start"))
    monkeypatch.setattr(sys, "argv", ["voice_scenarios.py"])
    assert module.main() == 0
    assert capsys.readouterr().out.startswith("SKIP: Ollama is not running")


def test_every_founder_scenario_is_scripted() -> None:
    assert list(load().SCENARIOS) == ["S1+S2", "S3", "S4", "S5", "S6", "S7", "RL2a", "RL2b", "RL2c", "RL2d"]
