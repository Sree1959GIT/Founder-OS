"""Provider routing and fallback (PRD §4, R2, R3).

Each agent type has a privacy class. `local` agents always use the local provider (Ollama). `cloud_allowed` and
`cloud` agents use the deep-work provider (`DEEP_PROVIDER`) only when `CLOUD_ALLOWED=true` and its credentials exist;
any cloud failure falls back to the local provider, and the completion records `fallback_from`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from loguru import logger

from app.config import DeepProvider, Settings
from app.llm.base import Completion, LLMError, LLMProvider, Message, StreamChunk, ToolSpec
from app.llm.cloud import AnthropicAPIProvider, ClaudeAgentSDKProvider, GeminiProvider
from app.llm.fake import FakeProvider
from app.llm.ollama import OllamaProvider

Privacy = Literal["local", "cloud_allowed", "cloud"]


class LLMRouter:
    def __init__(self, local: LLMProvider, cloud: LLMProvider | None = None, *, cloud_allowed: bool = False) -> None:
        self.local = local
        self.cloud = cloud
        self.cloud_allowed = cloud_allowed

    def chain(self, privacy: Privacy, *, needs_tools: bool = False) -> list[LLMProvider]:
        """Providers to try in order. Local agents never see a cloud provider (PRD R2)."""
        if privacy == "local" or self.cloud is None or not self.cloud_allowed:
            return [self.local]
        if needs_tools and not self.cloud.supports_tools:
            return [self.local]
        return [self.cloud, self.local]

    def primary(self, privacy: Privacy, *, needs_tools: bool = False) -> LLMProvider:
        return self.chain(privacy, needs_tools=needs_tools)[0]

    async def complete(
        self,
        privacy: Privacy,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> Completion:
        chain = self.chain(privacy, needs_tools=bool(tools))
        failed: str | None = None
        for i, provider in enumerate(chain):
            try:
                completion = await provider.complete(messages, tools=tools, json_schema=json_schema)
            except LLMError as exc:
                if i == len(chain) - 1:
                    raise
                logger.warning("LLM {} failed, falling back to {}: {}", provider.name, chain[i + 1].name, exc)
                failed = provider.name
                continue
            if failed:
                completion.fallback_from = failed
            return completion
        raise LLMError("no provider available")  # unreachable: the chain is never empty

    async def stream(
        self,
        privacy: Privacy,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream from the first provider that answers. Fallback only happens before the first chunk."""
        chain = self.chain(privacy, needs_tools=bool(tools))
        failed: str | None = None
        for i, provider in enumerate(chain):
            started = False
            try:
                async for chunk in await provider.complete(messages, tools=tools, json_schema=json_schema, stream=True):
                    started = True
                    if chunk.done and chunk.completion is not None and failed:
                        chunk.completion.fallback_from = failed
                    yield chunk
                return
            except LLMError as exc:
                if started or i == len(chain) - 1:
                    raise
                logger.warning("LLM {} failed, falling back to {}: {}", provider.name, chain[i + 1].name, exc)
                failed = provider.name


def build_local_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeProvider(name="fake", model="fake-model")
    return OllamaProvider(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        embed_model=settings.ollama_embed_model,
        think=settings.ollama_think,
        keep_alive=settings.ollama_keep_alive or None,
        num_ctx=settings.ollama_num_ctx,
        timeout_s=settings.llm_timeout_s,
    )


def build_cloud_provider(settings: Settings) -> LLMProvider | None:
    """The deep-work provider, or None when cloud is off or not configured (then everything runs locally)."""
    effective = settings.effective_deep_provider()
    match effective:
        case DeepProvider.ANTHROPIC if settings.anthropic_api_key is not None:
            return AnthropicAPIProvider(
                settings.anthropic_api_key.get_secret_value(), settings.claude_model, timeout_s=settings.llm_timeout_s
            )
        case DeepProvider.GEMINI if settings.gemini_api_key is not None:
            return GeminiProvider(
                settings.gemini_api_key.get_secret_value(), settings.gemini_model, timeout_s=settings.llm_timeout_s
            )
        case DeepProvider.CLAUDE_SDK if settings.claude_code_oauth_token is not None:
            return ClaudeAgentSDKProvider(settings.claude_code_oauth_token.get_secret_value(), settings.claude_model)
        case _:
            return None


def build_router(settings: Settings) -> LLMRouter:
    return LLMRouter(
        build_local_provider(settings), build_cloud_provider(settings), cloud_allowed=settings.cloud_allowed
    )
