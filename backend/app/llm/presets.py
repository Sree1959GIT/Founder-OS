"""The AI model card's presets (M7a): which providers a member may bring a key for, and how each is called.

API keys only. Subscription sign-ins (Claude Pro/Max OAuth, Google AI Pro/Ultra, "Sign in with ChatGPT") are not
offered: their terms do not allow them in a hosted app like this one, and `CLAUDE_CODE_OAUTH_TOKEN` is never read.
Base URLs are the providers' documented API roots; model defaults come from config (`Settings`), never from here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.config import Settings

Kind = Literal["local", "anthropic", "gemini", "openai_compatible"]

LOCAL_PRESET = "qwen_local"


class Preset(BaseModel):
    id: str
    label: str  # the provider's name, as on the green chip: "Claude · claude-sonnet-5-5 · key verified"
    title: str  # the line in the picker
    kind: Kind
    base_url: str = ""
    needs_key: bool = True
    custom_base_url: bool = False
    json_mode: Literal["schema", "prompt"] = "schema"
    key_hint: str = ""  # where a member gets a key


PRESETS: dict[str, Preset] = {
    p.id: p
    for p in [
        Preset(
            id=LOCAL_PRESET,
            label="Qwen",
            title="Qwen on our server (free, private, slower)",
            kind="local",
            needs_key=False,
        ),
        Preset(
            id="claude",
            label="Claude",
            title="Claude (Anthropic API key)",
            kind="anthropic",
            base_url="https://api.anthropic.com",
            key_hint="console.anthropic.com → API keys",
        ),
        Preset(
            id="gemini",
            label="Gemini",
            title="Gemini (Google AI Studio key)",
            kind="gemini",
            base_url="https://generativelanguage.googleapis.com",
            key_hint="aistudio.google.com → Get API key",
        ),
        Preset(
            id="openai",
            label="OpenAI",
            title="OpenAI (API key)",
            kind="openai_compatible",
            base_url="https://api.openai.com/v1",
            key_hint="platform.openai.com → API keys",
        ),
        Preset(
            id="openrouter",
            label="OpenRouter",
            title="OpenRouter (API key)",
            kind="openai_compatible",
            base_url="https://openrouter.ai/api/v1",
            key_hint="openrouter.ai → Keys",
        ),
        Preset(
            id="groq",
            label="Groq",
            title="Groq (API key)",
            kind="openai_compatible",
            base_url="https://api.groq.com/openai/v1",
            json_mode="prompt",  # structured output only on some Groq models
            key_hint="console.groq.com → API keys",
        ),
        Preset(
            id="ollama_cloud",
            label="Ollama Cloud",
            title="Ollama Cloud (API key)",
            kind="openai_compatible",
            base_url="https://ollama.com/v1",  # docs.ollama.com/api/openai-compatibility, read 2026-11-22
            json_mode="prompt",  # "Cloud models currently do not support structured outputs" (docs, 2026-11-22)
            key_hint="ollama.com → Settings → API keys",
        ),
        Preset(
            id="custom",
            label="Custom",
            title="Custom (any OpenAI-compatible server)",
            kind="openai_compatible",
            custom_base_url=True,
            json_mode="prompt",  # unknown server: the schema goes in the instructions, which every server accepts
            key_hint="your provider's dashboard",
        ),
    ]
}


# Founder F3: the provider from the key's shape, so a member only pastes a key. Most specific prefix first
# ("sk-ant-" and "sk-or-" before OpenAI's plain "sk-"). The provider list on the card stays as a manual override.
KEY_SHAPES: tuple[tuple[str, str], ...] = (
    ("sk-ant-", "claude"),
    ("sk-or-", "openrouter"),
    ("gsk_", "groq"),
    ("AIza", "gemini"),
    ("sk-proj-", "openai"),
    ("sk-", "openai"),
)


def detect_preset(key: str) -> str | None:
    """The preset id a key's prefix belongs to, or None (Ollama Cloud and Custom keys have no fixed shape)."""
    key = key.strip()
    return next((preset for prefix, preset in KEY_SHAPES if key.startswith(prefix)), None)


def default_model(preset: Preset, settings: Settings) -> str:
    """The configured model, used only when the provider cannot list its models (see `ai_model.pick_models`)."""
    return {
        LOCAL_PRESET: settings.ollama_chat_model,
        "claude": settings.claude_model,
        "gemini": settings.gemini_model,
        "openai": settings.openai_model,
        "openrouter": settings.openrouter_model,
        "groq": settings.groq_model,
        "ollama_cloud": settings.ollama_cloud_model,
        "custom": settings.openai_compatible_model,
    }.get(preset.id, "")
