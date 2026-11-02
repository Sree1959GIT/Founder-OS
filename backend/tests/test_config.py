from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, DeepProvider, Settings


def make(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_defaults_are_local_only() -> None:
    s = make()
    assert s.workspace_id == "default"
    assert s.cloud_allowed is False
    assert s.effective_deep_provider() is DeepProvider.OLLAMA


def test_relative_paths_resolve_against_project_root() -> None:
    s = make()
    assert s.workspace_data_dir() == (PROJECT_ROOT / "data" / "default").resolve()
    assert s.workspace_vault_dir("acme") == (PROJECT_ROOT / "vault" / "acme").resolve()


def test_absolute_paths_are_kept(tmp_path: Path) -> None:
    s = make(data_dir=tmp_path)
    assert s.workspace_data_dir() == tmp_path / "default"


@pytest.mark.parametrize("bad", ["../etc", "a/b", "a\\b", "", "x" * 65, "has space"])
def test_workspace_id_rejects_path_tricks(bad: str) -> None:
    with pytest.raises(ValidationError):
        make(workspace_id=bad)


def test_env_vars_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ID", "northwind")
    monkeypatch.setenv("CLOUD_ALLOWED", "true")
    monkeypatch.setenv("DEEP_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value")
    s = make()
    assert s.workspace_id == "northwind"
    assert s.effective_deep_provider() is DeepProvider.GEMINI
    assert "secret-value" not in repr(s)


def test_blank_secret_means_not_configured() -> None:
    s = make(cloud_allowed=True, deep_provider="anthropic", anthropic_api_key="  ")
    assert s.anthropic_api_key is None
    assert s.effective_deep_provider() is DeepProvider.OLLAMA


@pytest.mark.parametrize(
    ("provider", "field"),
    [
        (DeepProvider.CLAUDE_SDK, "claude_code_oauth_token"),
        (DeepProvider.ANTHROPIC, "anthropic_api_key"),
        (DeepProvider.GEMINI, "gemini_api_key"),
    ],
)
def test_deep_provider_needs_cloud_and_credentials(provider: DeepProvider, field: str) -> None:
    assert make(cloud_allowed=True, deep_provider=provider).effective_deep_provider() is DeepProvider.OLLAMA
    assert make(cloud_allowed=False, deep_provider=provider, **{field: "k"}).effective_deep_provider() is (
        DeepProvider.OLLAMA
    )
    assert make(cloud_allowed=True, deep_provider=provider, **{field: "k"}).effective_deep_provider() is provider


def test_ollama_url_trailing_slash_is_stripped() -> None:
    assert make(ollama_base_url="http://host:11434/").ollama_base_url == "http://host:11434"


def test_currency_must_be_iso_code() -> None:
    with pytest.raises(ValidationError):
        make(currency="rupees")
