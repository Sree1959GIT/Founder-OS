"""Application settings, loaded from environment variables and the project-root `.env` file."""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] is the repository root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

WORKSPACE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class DeepProvider(StrEnum):
    """Which provider "deep work" agents use. Falls back to Ollama when not usable."""

    CLAUDE_SDK = "claude_sdk"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    """All runtime configuration. Secrets are `SecretStr` so they never appear in logs or reprs."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Workspace and storage
    workspace_id: str = Field(default="default", pattern=WORKSPACE_ID_PATTERN)
    data_dir: Path = Path("data")
    vault_path: Path = Path("vault")

    # Local LLM (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_embed_model: str = "nomic-embed-text"

    # Vector store (Qdrant, Docker)
    qdrant_host: str = "localhost"
    qdrant_port: int = Field(default=6333, ge=1, le=65535)

    # Cloud providers for deep-work agents
    deep_provider: DeepProvider = DeepProvider.OLLAMA
    cloud_allowed: bool = False
    claude_code_oauth_token: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-sonnet-5-5"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Display
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")

    # Logging
    log_level: str = Field(default="INFO", pattern=r"^(?i:TRACE|DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL)$")

    # HTTP
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    health_probe_timeout_s: float = Field(default=2.0, gt=0, le=30)

    @field_validator("claude_code_oauth_token", "anthropic_api_key", "gemini_api_key", mode="before")
    @classmethod
    def _blank_secret_is_none(cls, value: object) -> object:
        """Treat an empty value in `.env` (e.g. `GEMINI_API_KEY=`) as not configured."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    def _workspace(self, workspace_id: str | None) -> str:
        if workspace_id is None:
            return self.workspace_id
        if not re.fullmatch(WORKSPACE_ID_PATTERN, workspace_id):
            raise ValueError(f"invalid workspace id: {workspace_id!r}")
        return workspace_id

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    def workspace_data_dir(self, workspace_id: str | None = None) -> Path:
        """`<DATA_DIR>/<workspace_id>`: DuckDB file, mappings and logs for one workspace."""
        return self._resolve(self.data_dir) / self._workspace(workspace_id)

    def workspace_vault_dir(self, workspace_id: str | None = None) -> Path:
        """`<VAULT_PATH>/<workspace_id>`: the Markdown vault for one workspace."""
        return self._resolve(self.vault_path) / self._workspace(workspace_id)

    def provider_configured(self, provider: DeepProvider) -> bool:
        """Whether the credentials needed by `provider` are present (no network call)."""
        match provider:
            case DeepProvider.CLAUDE_SDK:
                return self.claude_code_oauth_token is not None
            case DeepProvider.ANTHROPIC:
                return self.anthropic_api_key is not None
            case DeepProvider.GEMINI:
                return self.gemini_api_key is not None
            case DeepProvider.OLLAMA:
                return True

    def effective_deep_provider(self) -> DeepProvider:
        """The provider deep-work agents will actually use, after privacy and credential fallback (PRD R2/R3)."""
        if self.deep_provider is DeepProvider.OLLAMA or not self.cloud_allowed:
            return DeepProvider.OLLAMA
        if self.provider_configured(self.deep_provider):
            return self.deep_provider
        return DeepProvider.OLLAMA


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton. Tests override it through FastAPI dependency overrides."""
    return Settings()
