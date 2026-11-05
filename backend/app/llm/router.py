"""Provider routing, privacy, cost and fallback (PRD §4, R2, R3).

Each agent type has a privacy class. `local` agents always use the local provider (Ollama). `cloud_allowed` and
`cloud` agents may use a cloud provider only when `CLOUD_ALLOWED=true`, its key exists, and the monthly cap allows it:
the type's own choice from `AGENT_MODELS`, else `DEEP_PROVIDER`. Every cloud payload goes through the privacy filter.
Any cloud failure falls back to the local provider, and the completion records `fallback_from`.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Literal

from loguru import logger

from app.config import DeepProvider, Settings
from app.llm.base import Completion, LLMError, LLMProvider, LLMUnavailable, Message, StreamChunk, ToolSpec, WebAnswer
from app.llm.cloud import AnthropicAPIProvider, GeminiProvider, OpenAICompatibleProvider
from app.llm.costs import CallRecord, CostLedger
from app.llm.fake import FakeProvider
from app.llm.ollama import OllamaProvider
from app.llm.privacy import FilterReport, filter_messages, filter_text

Privacy = Literal["local", "cloud_allowed", "cloud"]


class LLMRouter:
    def __init__(
        self,
        local: LLMProvider,
        cloud: LLMProvider | None = None,
        *,
        cloud_allowed: bool = False,
        routes: dict[str, LLMProvider | None] | None = None,
        ledger: CostLedger | None = None,
    ) -> None:
        self.local = local
        self.cloud = cloud
        self.cloud_allowed = cloud_allowed
        self.routes = routes or {}  # agent type -> its own provider; None means this type stays local
        self.ledger = ledger

    def _cloud_for(self, agent_type: str) -> LLMProvider | None:
        return self.routes.get(agent_type, self.cloud)

    def chain(self, privacy: Privacy, *, needs_tools: bool = False, agent_type: str = "") -> list[LLMProvider]:
        """Providers to try in order. Local agents never see a cloud provider (PRD R2)."""
        if privacy == "local" or not self.cloud_allowed:
            return [self.local]
        cloud = self._cloud_for(agent_type)
        if cloud is None or (needs_tools and not cloud.supports_tools):
            return [self.local]
        refusal = self.ledger.refusal(cloud.model) if self.ledger is not None else None
        if refusal:
            logger.warning("Using the local model for {}: {}", agent_type or "this call", refusal)
            return [self.local]
        return [cloud, self.local]

    def primary(self, privacy: Privacy, *, needs_tools: bool = False, agent_type: str = "") -> LLMProvider:
        return self.chain(privacy, needs_tools=needs_tools, agent_type=agent_type)[0]

    def _payload(self, provider: LLMProvider, messages: list[Message]) -> tuple[list[Message], FilterReport]:
        if not provider.is_cloud:
            return messages, FilterReport()
        filtered, report = filter_messages(messages)
        if report.total:
            logger.info("Privacy filter on the {} payload: {} items removed", provider.name, report.total)
        return filtered, report

    def _record(
        self,
        provider: LLMProvider,
        agent_type: str,
        started: float,
        report: FilterReport,
        completion: Completion | None = None,
        failed_from: str | None = None,
        error: str | None = None,
    ) -> None:
        usage = completion.usage if completion is not None else None
        cost = None
        if not provider.is_cloud:
            cost = 0.0
        elif usage is not None and self.ledger is not None:
            cost = self.ledger.estimate(provider.model, usage)
        if completion is not None:
            completion.fallback_from = failed_from or completion.fallback_from
            completion.est_cost_usd = cost
        if self.ledger is None:
            return
        self.ledger.record(
            CallRecord(
                agent_type=agent_type,
                provider=provider.name,
                model=provider.model,
                is_cloud=provider.is_cloud,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                est_cost_usd=cost,
                fallback_from=failed_from,
                filtered_items=report.total,
                error=error,
            )
        )

    async def complete(
        self,
        privacy: Privacy,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
        *,
        agent_type: str = "",
    ) -> Completion:
        chain = self.chain(privacy, needs_tools=bool(tools), agent_type=agent_type)
        failed: str | None = None
        for i, provider in enumerate(chain):
            payload, report = self._payload(provider, messages)
            started = time.perf_counter()
            try:
                completion = await provider.complete(payload, tools=tools, json_schema=json_schema)
            except LLMError as exc:
                self._record(provider, agent_type, started, report, failed_from=failed, error=type(exc).__name__)
                if i == len(chain) - 1:
                    raise
                logger.warning("LLM {} failed, falling back to {}: {}", provider.name, chain[i + 1].name, exc)
                failed = provider.name
                continue
            self._record(provider, agent_type, started, report, completion, failed)
            return completion
        raise LLMError("no provider available")  # unreachable: the chain is never empty

    async def stream(
        self,
        privacy: Privacy,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
        *,
        agent_type: str = "",
    ) -> AsyncIterator[StreamChunk]:
        """Stream from the first provider that answers. Fallback only happens before the first chunk."""
        chain = self.chain(privacy, needs_tools=bool(tools), agent_type=agent_type)
        failed: str | None = None
        for i, provider in enumerate(chain):
            payload, report = self._payload(provider, messages)
            started_at = time.perf_counter()
            started = False
            try:
                async for chunk in await provider.complete(payload, tools=tools, json_schema=json_schema, stream=True):
                    started = True
                    if chunk.done and chunk.completion is not None:
                        self._record(provider, agent_type, started_at, report, chunk.completion, failed)
                    yield chunk
                return
            except LLMError as exc:
                self._record(provider, agent_type, started_at, report, failed_from=failed, error=type(exc).__name__)
                if started or i == len(chain) - 1:
                    raise
                logger.warning("LLM {} failed, falling back to {}: {}", provider.name, chain[i + 1].name, exc)
                failed = provider.name

    def can_search_web(self, privacy: Privacy, agent_type: str) -> bool:
        return any(p.is_cloud and p.supports_web_search for p in self.chain(privacy, agent_type=agent_type))

    async def web_search(self, privacy: Privacy, query: str, *, agent_type: str = "") -> WebAnswer:
        """A grounded search through the agent's cloud provider. The query goes through the privacy filter too."""
        provider = next((p for p in self.chain(privacy, agent_type=agent_type) if p.is_cloud), None)
        if provider is None or not provider.supports_web_search:
            raise LLMUnavailable("web search needs a cloud provider that supports it")
        report = FilterReport()
        cleaned = filter_text(query, report)
        started = time.perf_counter()
        try:
            answer = await provider.web_search(cleaned)
        except LLMError as exc:
            self._record(provider, agent_type, started, report, error=type(exc).__name__)
            raise
        self._record(provider, agent_type, started, report, answer.completion)
        return answer


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


def build_fast_provider(settings: Settings) -> LLMProvider | None:
    """The conversation lane's small model, or None (then the lane answers from templates)."""
    if not settings.fast_lane_model or settings.llm_provider == "fake":
        return None
    return OllamaProvider(
        settings.ollama_base_url,
        settings.fast_lane_model,
        think=False,
        keep_alive=settings.ollama_keep_alive or None,
        num_ctx=settings.ollama_num_ctx,
        timeout_s=settings.fast_lane_timeout_s,
    )


def build_named_provider(settings: Settings, name: DeepProvider, model: str = "") -> LLMProvider | None:
    """A cloud provider by name, or None when it is not configured. Keys come from settings, never from code."""
    timeout = settings.llm_timeout_s
    match name:
        case DeepProvider.ANTHROPIC if settings.anthropic_api_key is not None:
            key = settings.anthropic_api_key.get_secret_value()
            return AnthropicAPIProvider(key, model or settings.claude_model, timeout_s=timeout)
        case DeepProvider.GEMINI if settings.provider_configured(DeepProvider.GEMINI):
            if settings.gemini_backend == "vertex":
                assert settings.vertex_api_key is not None
                key = settings.vertex_api_key.get_secret_value()
                return GeminiProvider(key, model or settings.gemini_model, timeout_s=timeout, backend="vertex")
            assert settings.gemini_api_key is not None
            key = settings.gemini_api_key.get_secret_value()
            return GeminiProvider(key, model or settings.gemini_model, timeout_s=timeout)
        case DeepProvider.OPENAI if settings.openai_api_key is not None:
            key = settings.openai_api_key.get_secret_value()
            return OpenAICompatibleProvider(
                key, model or settings.openai_model, name="openai", base_url=settings.openai_base_url, timeout_s=timeout
            )
        case DeepProvider.OPENAI_COMPATIBLE if settings.provider_configured(DeepProvider.OPENAI_COMPATIBLE):
            assert settings.openai_compatible_api_key is not None
            key = settings.openai_compatible_api_key.get_secret_value()
            return OpenAICompatibleProvider(
                key,
                model or settings.openai_compatible_model,
                name="openai_compatible",
                base_url=settings.openai_compatible_base_url,
                timeout_s=timeout,
            )
        case _:
            return None


def build_cloud_provider(settings: Settings) -> LLMProvider | None:
    """The default deep-work provider, or None when cloud is off or not configured (then everything runs locally)."""
    return build_named_provider(settings, settings.effective_deep_provider())


def build_routes(settings: Settings) -> dict[str, LLMProvider | None]:
    """`AGENT_MODELS`: per agent type, "provider" or "provider:model". A bad entry is reported and ignored."""
    routes: dict[str, LLMProvider | None] = {}
    if not settings.cloud_allowed:
        return routes
    for agent_type, choice in settings.agent_models.items():
        name, _, model = choice.partition(":")
        try:
            provider_name = DeepProvider(name.strip())
        except ValueError:
            logger.warning("AGENT_MODELS: unknown provider {!r} for {}; ignoring it", name, agent_type)
            continue
        if provider_name is DeepProvider.OLLAMA:
            routes[agent_type] = None
            continue
        provider = build_named_provider(settings, provider_name, model.strip())
        if provider is None:
            logger.warning("AGENT_MODELS: {} has no key for {}; ignoring it", name, agent_type)
            continue
        routes[agent_type] = provider
    return routes


def build_router(settings: Settings) -> LLMRouter:
    return LLMRouter(
        build_local_provider(settings),
        build_cloud_provider(settings),
        cloud_allowed=settings.cloud_allowed,
        routes=build_routes(settings),
        ledger=CostLedger(
            settings.workspace_data_dir() / "llm_calls.jsonl",
            monthly_cap_usd=settings.cloud_monthly_cap_usd,
            prices={model: (float(p[0]), float(p[1])) for model, p in settings.llm_prices.items()},
        ),
    )
