"""Ollama provider (`/api/chat`, `/api/embed`). Ollama is an external service at `OLLAMA_BASE_URL`: the native app
or a Docker container (the founder's runs in Docker, shared with n8n).

Qwen3 is a "thinking" model. Thinking is off by default (`think: false`): replies are faster and JSON and tool calls
come back without a reasoning preamble. Set `OLLAMA_THINK=true` to turn it on.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from loguru import logger

from app.llm.base import (
    Completion,
    LLMError,
    LLMProvider,
    LLMUnavailable,
    Message,
    StreamChunk,
    Timer,
    ToolCall,
    ToolSpec,
    Usage,
)


def to_ollama_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        item: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            item["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls]
        if m.role == "tool" and m.name:
            item["tool_name"] = m.name
        out.append(item)
    return out


def _tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function", {}) if isinstance(raw, dict) else {}
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):  # some models return a JSON string
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                arguments = {"_raw": arguments}
        name = str(function.get("name", ""))
        if name:
            kwargs: dict[str, Any] = {"name": name, "arguments": arguments if isinstance(arguments, dict) else {}}
            if raw.get("id"):
                kwargs["id"] = str(raw["id"])
            calls.append(ToolCall(**kwargs))
    return calls


class OllamaProvider(LLMProvider):
    name = "ollama"
    is_cloud = False

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        embed_model: str = "nomic-embed-text",
        think: bool = False,
        keep_alive: str | None = "30m",
        num_ctx: int | None = 8192,
        temperature: float | None = 0.2,
        timeout_s: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.think = think
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.temperature = temperature
        self._timeout = httpx.Timeout(timeout_s, connect=5.0)
        self._transport = transport
        self.ensure_loaded_before_calls = True
        self.load_timeout_s = 1200.0
        self._load_lock = asyncio.Lock()
        self._loaded_at = -1e9  # monotonic time the model was last seen in memory

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout, transport=self._transport)

    def _body(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None, stream: bool
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": to_ollama_messages(messages),
            "stream": stream,
            "think": self.think,
        }
        if tools:
            body["tools"] = [t.openai_style() for t in tools]
        if json_schema is not None:
            body["format"] = json_schema
        if self.keep_alive:
            body["keep_alive"] = self.keep_alive
        options: dict[str, Any] = {}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        if self.temperature is not None:
            options["temperature"] = 0.0 if json_schema is not None else self.temperature
        if options:
            body["options"] = options
        return body

    def _error(self, exc: Exception) -> LLMError:
        if isinstance(exc, httpx.HTTPStatusError):
            detail = exc.response.text[:300]
            if exc.response.status_code == 404:
                return LLMUnavailable(f"Ollama model {self.model} is not pulled ({detail})")
            return LLMError(f"Ollama returned HTTP {exc.response.status_code}: {detail}")
        if isinstance(exc, httpx.TimeoutException):
            return LLMUnavailable(f"Ollama timed out at {self.base_url} ({type(exc).__name__})")
        if isinstance(exc, httpx.HTTPError):
            return LLMUnavailable(f"Ollama not reachable at {self.base_url} ({type(exc).__name__}: {exc})")
        return LLMError(f"Ollama returned an unreadable response ({type(exc).__name__}: {exc})")

    def _is_this_model(self, entry: dict[str, Any]) -> bool:
        names = {str(entry.get("name", "")), str(entry.get("model", ""))}
        return self.model in names or (":" not in self.model and f"{self.model}:latest" in names)

    async def ensure_loaded(self) -> None:
        """Load the chat model first when Ollama has unloaded it (idle `keep_alive`, restart, another app's model).

        Without this, a cold load slower than the chat timeout is aborted by every call and never completes. The
        `/api/ps` check is cached for 60 s; concurrent callers share one load. Errors are left to the chat call.
        """
        if not self.ensure_loaded_before_calls or time.monotonic() - self._loaded_at < 60:
            return
        async with self._load_lock:
            if time.monotonic() - self._loaded_at < 60:
                return
            try:
                if not any(self._is_this_model(m) for m in await self.loaded_models()):
                    logger.info("Ollama has not loaded {}; loading it first (can take minutes)", self.model)
                    seconds = await self.warm_up(self.load_timeout_s)
                    logger.info("Ollama model {} loaded in {} s", self.model, seconds)
                self._loaded_at = time.monotonic()
            except LLMError as exc:
                logger.debug("Could not check or load {}: {}", self.model, exc)

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        await self.ensure_loaded()
        timer = Timer()
        try:
            async with self._client() as client:
                response = await client.post("/api/chat", json=self._body(messages, tools, json_schema, False))
                response.raise_for_status()
                data = response.json()
            message = data["message"]
            return Completion(
                text=str(message.get("content") or ""),
                tool_calls=_tool_calls(message),
                provider=self.name,
                model=self.model,
                usage=Usage(
                    input_tokens=int(data.get("prompt_eval_count") or 0),
                    output_tokens=int(data.get("eval_count") or 0),
                ),
                latency_ms=timer.ms,
            )
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise self._error(exc) from exc

    async def _stream(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> AsyncIterator[StreamChunk]:
        await self.ensure_loaded()
        timer = Timer()
        parts: list[str] = []
        calls: list[ToolCall] = []
        usage = Usage()
        try:
            async with (
                self._client() as client,
                client.stream("POST", "/api/chat", json=self._body(messages, tools, json_schema, True)) as response,
            ):
                if response.status_code >= 400:
                    await response.aread()
                    response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise LLMError(f"Ollama error: {data['error']}")
                    message = data.get("message") or {}
                    delta = str(message.get("content") or "")
                    calls.extend(_tool_calls(message))
                    if delta:
                        parts.append(delta)
                        yield StreamChunk(delta=delta)
                    if data.get("done"):
                        usage = Usage(
                            input_tokens=int(data.get("prompt_eval_count") or 0),
                            output_tokens=int(data.get("eval_count") or 0),
                        )
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise self._error(exc) from exc
        completion = Completion(
            text="".join(parts),
            tool_calls=calls,
            provider=self.name,
            model=self.model,
            usage=usage,
            latency_ms=timer.ms,
        )
        yield StreamChunk(done=True, completion=completion)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with self._client() as client:
                response = await client.post("/api/embed", json={"model": self.embed_model, "input": texts})
                response.raise_for_status()
                vectors = response.json()["embeddings"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise self._error(exc) from exc
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise LLMError("Ollama returned the wrong number of embeddings")
        return [[float(x) for x in v] for v in vectors]

    async def warm_up(self, timeout_s: float = 1200.0) -> float:
        """Load the chat model into VRAM (`/api/generate` without a prompt) and return the seconds it took.

        A cold load can take minutes when the model files sit on a slow disk (e.g. a Windows bind mount into Docker).
        Ollama aborts a load when the client disconnects, so a short chat timeout would never let it finish. This call
        waits up to `timeout_s` and uses the same `num_ctx` as chat calls, so they reuse the loaded runner.
        """
        timer = Timer()
        body: dict[str, Any] = {"model": self.model}
        if self.keep_alive:
            body["keep_alive"] = self.keep_alive
        if self.num_ctx:
            body["options"] = {"num_ctx": self.num_ctx}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=httpx.Timeout(timeout_s, connect=5.0), transport=self._transport
            ) as client:
                response = await client.post("/api/generate", json=body)
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            raise self._error(exc) from exc
        self._loaded_at = time.monotonic()
        return round(timer.ms / 1000, 1)

    async def loaded_models(self) -> list[dict[str, Any]]:
        """`/api/ps`: models in memory and the VRAM each one uses (the GPU is shared with other apps)."""
        try:
            async with self._client() as client:
                response = await client.get("/api/ps")
                response.raise_for_status()
                return list(response.json().get("models") or [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise self._error(exc) from exc
