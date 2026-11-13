"""Application settings, loaded from environment variables and the project-root `.env` file."""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] is the repository root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

WORKSPACE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class DeepProvider(StrEnum):
    """Which provider "deep work" agents use. Falls back to Ollama when not usable."""

    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"
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

    # Financial data
    sample_data_dir: Path = Path("sample_data")
    # Load the Northwind demo data into an empty workspace at startup (turn off once you use your own files).
    auto_load_sample_data: bool = True
    max_upload_mb: int = Field(default=20, ge=1, le=500)

    # Local LLM (Ollama: an external service, native app or Docker container)
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:8b"
    ollama_embed_model: str = "nomic-embed-text"
    # Qwen3 "thinking": off for fast replies and clean JSON / tool calls.
    ollama_think: bool = False
    # How long Ollama keeps the chat model in VRAM after a call ("" = Ollama's default, 5 minutes).
    ollama_keep_alive: str = "30m"
    ollama_num_ctx: int | None = Field(default=8192, ge=2048, le=131072)
    # Load the chat model into VRAM in the background at startup (a cold load can take minutes on a slow disk).
    ollama_warmup: bool = True
    # ollama: the local provider is OLLAMA_CHAT_MODEL. fake: scripted offline replies (tests, demos without Ollama).
    llm_provider: Literal["ollama", "fake"] = "ollama"
    llm_timeout_s: float = Field(default=180.0, gt=0, le=1800)

    # Agents (M3a)
    # Who approves the Planner's team before it runs: always | cloud_only (any cloud agent) | never.
    team_approval: Literal["always", "cloud_only", "never"] = "cloud_only"
    team_approval_timeout_s: float = Field(default=300.0, gt=0, le=3600)
    max_local_agents: int = Field(default=2, ge=1, le=16)
    max_cloud_agents: int = Field(default=6, ge=1, le=32)
    agent_max_steps: int = Field(default=4, ge=1, le=12)
    # The Advisor warns when this share of Monte Carlo runs (or more) runs out of cash within 12 months. Above 1: off.
    cash_risk_warn_at: float = Field(default=0.5, ge=0, le=2)
    # Decision model (F7): llm (OLLAMA_CHAT_MODEL with JSON output) | fake. Below the confidence: escalate.
    decision_provider: Literal["llm", "fake", "laya", "jev"] = "llm"
    decision_min_confidence: float = Field(default=0.75, ge=0, le=1)
    laya_checkpoint: str = ""  # a fine-tuned folder; empty means stock Laya, which needs fine-tuning (PRD F7)
    laya_device: str = ""  # cuda or cpu; empty lets Laya choose
    jev_api_key: str = ""  # optional and paid; only non-sensitive routing state is sent
    jev_model: str = "jev-latest"

    # Conversation lane (M3b): stays responsive while agents run. No model set: it answers from templates.
    fast_lane_model: str = ""
    fast_lane_timeout_s: float = Field(default=4.0, gt=0, le=60)
    conversation_quiet: bool = False

    # Vector store (Qdrant, Docker)
    qdrant_host: str = "localhost"
    qdrant_port: int = Field(default=6333, ge=1, le=65535)

    # Vault and search (M2)
    # Copy the Northwind sample notes (sample_data/vault/) into an empty vault at startup.
    auto_load_sample_vault: bool = True
    # auto: Qdrant when reachable at startup, else in memory. qdrant: Qdrant only. memory: never use Qdrant.
    vector_store: Literal["auto", "qdrant", "memory"] = "auto"
    # ollama: OLLAMA_EMBED_MODEL. fake: deterministic offline hashing embedder (tests and demos without Ollama).
    embed_provider: Literal["ollama", "fake"] = "ollama"
    # tiktoken (cl100k_base, falls back to approx when it cannot load) or approx.
    tokenizer: Literal["tiktoken", "approx"] = "tiktoken"
    # Re-index when vault files change on disk. Polling helps on network drives.
    vault_watch: bool = True
    vault_watch_polling: bool = False

    # Cloud providers for deep-work agents
    deep_provider: DeepProvider = DeepProvider.OLLAMA
    cloud_allowed: bool = False
    # Per agent type, "provider" or "provider:model", as JSON: {"memo_writer": "anthropic:claude-opus-5-5"}.
    agent_models: dict[str, str] = Field(default_factory=dict)
    # At or over this month's estimated spend, cloud agents use Ollama. 0 means no cloud calls at all.
    cloud_monthly_cap_usd: float = Field(default=25.0, ge=0)
    # USD per million tokens, added to the built-in table, as JSON: {"my-model": [0.5, 1.5]}.
    llm_prices: dict[str, list[float]] = Field(default_factory=dict)
    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-sonnet-5-5"
    gemini_backend: Literal["ai_studio", "vertex"] = "ai_studio"
    gemini_api_key: SecretStr | None = None
    vertex_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-6.1-terra"
    # Any endpoint that speaks OpenAI's API: OpenRouter, DeepSeek and others.
    openai_compatible_api_key: SecretStr | None = None
    openai_compatible_base_url: str = ""
    openai_compatible_model: str = ""

    # Display
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")

    # Logging
    log_level: str = Field(default="INFO", pattern=r"^(?i:TRACE|DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL)$")

    # HTTP
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    health_probe_timeout_s: float = Field(default=2.0, gt=0, le=30)
    # Voice (M5, PRD F5). Models live in <data>/models; scripts/download_voice_models.py fetches them.
    voice_enabled: bool = True
    voice_mode: Literal["ptt", "duplex"] = "ptt"
    # faster_whisper: small.en on CUDA (int8_float16), base.en int8 on CPU as the fallback. fake: tests.
    voice_stt: Literal["faster_whisper", "fake"] = "faster_whisper"
    voice_stt_model: str = "small.en"
    voice_stt_cpu_model: str = "base.en"
    voice_stt_device: Literal["auto", "cuda", "cpu"] = "auto"
    voice_stt_compute_type: str = "auto"
    # kokoro: Kokoro-82M ONNX on CPU (leaves the shared GPU to qwen3:8b and Whisper). fake: tests.
    voice_tts: Literal["kokoro", "fake"] = "kokoro"
    voice_tts_model: str = "kokoro-v1.0.onnx"
    voice_tts_voice: str = "af_heart"
    voice_models_dir: Path | None = None  # empty: <data_dir>/models
    # silero: Silero VAD v6 (ONNX, bundled with faster-whisper). energy: an RMS threshold (fallback, tests).
    voice_vad: Literal["silero", "energy"] = "silero"
    voice_vad_threshold: float = Field(default=0.5, gt=0, lt=1)
    voice_end_silence_ms: int = Field(default=400, ge=100, le=3000)
    voice_barge_in_ms: int = Field(default=600, ge=100, le=5000)
    voice_partial_interval_ms: int = Field(default=0, ge=0, le=5000)
    # While FounderOS speaks, sound below this share of the founder's own speech level is its own echo (0: off).
    voice_echo_gate: float = Field(default=0.3, ge=0, le=1)

    @field_validator("deep_provider", mode="before")
    @classmethod
    def _removed_provider_is_local(cls, value: Any) -> Any:
        """`claude_sdk` was removed: a `.env` that still names it starts up local rather than failing."""
        return DeepProvider.OLLAMA if value == "claude_sdk" else value

    @field_validator(
        "anthropic_api_key",
        "gemini_api_key",
        "vertex_api_key",
        "openai_api_key",
        "openai_compatible_api_key",
        mode="before",
    )
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

    def voice_models_path(self) -> Path:
        return self._resolve(self.voice_models_dir or (self.data_dir / "models"))

    def workspace_data_dir(self, workspace_id: str | None = None) -> Path:
        """`<DATA_DIR>/<workspace_id>`: DuckDB file, mappings and logs for one workspace."""
        return self._resolve(self.data_dir) / self._workspace(workspace_id)

    def sample_data_path(self) -> Path:
        return self._resolve(self.sample_data_dir)

    def workspace_vault_dir(self, workspace_id: str | None = None) -> Path:
        """`<VAULT_PATH>/<workspace_id>`: the Markdown vault for one workspace."""
        return self._resolve(self.vault_path) / self._workspace(workspace_id)

    def provider_configured(self, provider: DeepProvider) -> bool:
        """Whether the credentials needed by `provider` are present (no network call)."""
        match provider:
            case DeepProvider.ANTHROPIC:
                return self.anthropic_api_key is not None
            case DeepProvider.GEMINI:
                key = self.vertex_api_key if self.gemini_backend == "vertex" else self.gemini_api_key
                return key is not None
            case DeepProvider.OPENAI:
                return self.openai_api_key is not None
            case DeepProvider.OPENAI_COMPATIBLE:
                return (
                    self.openai_compatible_api_key is not None
                    and bool(self.openai_compatible_base_url)
                    and bool(self.openai_compatible_model)
                )
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
