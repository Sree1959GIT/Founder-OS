"""Cloud providers for "deep work" agents (PRD §4): Anthropic, Gemini (AI Studio or Vertex), OpenAI, OpenAI-compatible.

All are called over their REST APIs with httpx (no SDK dependency; tests use `httpx.MockTransport`), with an API key
from `.env`. A Claude Free, Pro or Max subscription is not an option: Anthropic does not permit those credentials in
apps like this one, so Claude is reached with an API key only (see PRD §12).
Every failure raises `LLMUnavailable` or `LLMError`; the router then falls back to Ollama (PRD R3). Keys travel in
headers and are removed from error text, so they cannot reach a log.
Model IDs come from config (`CLAUDE_MODEL`, `GEMINI_MODEL`, `OPENAI_MODEL`...), never from agent code.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx

from app.llm.base import (
    Completion,
    LLMError,
    LLMProvider,
    LLMUnavailable,
    Message,
    Timer,
    ToolCall,
    ToolSpec,
    Usage,
    WebAnswer,
    WebSource,
)

JSON_TOOL = "respond"


ANTHROPIC_WEB_SEARCH_TOOL = "web_search_20260209"


def _http_error(provider: str, exc: Exception, secret: str = "") -> LLMError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = exc.response.text[:300]
        if secret:
            detail = detail.replace(secret, "***")
        if status in (401, 403, 408, 429) or status >= 500:
            return LLMUnavailable(f"{provider} unavailable (HTTP {status}): {detail}")
        return LLMError(f"{provider} rejected the request (HTTP {status}): {detail}")
    if isinstance(exc, httpx.HTTPError):
        return LLMUnavailable(f"{provider} not reachable ({type(exc).__name__}: {exc})")
    return LLMError(f"{provider} returned an unreadable response ({type(exc).__name__}: {exc})")


def _system_text(messages: list[Message]) -> str:
    return "\n\n".join(m.content for m in messages if m.role == "system")


class AnthropicAPIProvider(LLMProvider):
    """Claude through the Anthropic Messages API (`ANTHROPIC_API_KEY`). JSON output uses a forced `respond` tool."""

    name = "anthropic"
    is_cloud = True
    supports_web_search = True

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        max_tokens: int = 2048,
        timeout_s: float = 120.0,
        base_url: str = "https://api.anthropic.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._key = api_key
        self._max_tokens = max_tokens
        self._timeout = httpx.Timeout(timeout_s, connect=10.0)
        self._base_url = base_url
        self._transport = transport

    @staticmethod
    def _messages(messages: list[Message], *, has_tools: bool = True) -> list[dict[str, Any]]:
        """`has_tools=False`: the API refuses tool blocks in a request that defines no tools, so they become text."""
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            if not has_tools and m.role == "tool":
                out.append({"role": "user", "content": f"Result of {m.name or 'the tool'}: {m.content}"})
                continue
            if not has_tools and m.role == "assistant" and m.tool_calls:
                called = ", ".join(c.name for c in m.tool_calls)
                out.append({"role": "assistant", "content": f"{m.content} (I called: {called})".strip()})
                continue
            if m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id or "", "content": m.content}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)  # parallel tool results share one user turn
                else:
                    out.append({"role": "user", "content": [block]})
                continue
            if m.role == "assistant" and m.tool_calls:
                content: list[dict[str, Any]] = [{"type": "text", "text": m.content}] if m.content else []
                content += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls
                ]
                out.append({"role": "assistant", "content": content})
                continue
            out.append({"role": m.role, "content": m.content})
        return out

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        timer = Timer()
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
        }
        system = _system_text(messages)
        if system:
            body["system"] = system
        specs = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools or []]
        if json_schema is not None:
            specs.append({"name": JSON_TOOL, "description": "Return the answer as JSON.", "input_schema": json_schema})
            body["tool_choice"] = {"type": "tool", "name": JSON_TOOL}
        if specs:
            body["tools"] = specs
        body["messages"] = self._messages(messages, has_tools=bool(specs))
        headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post("/v1/messages", json=body, headers=headers)
                response.raise_for_status()
                data = response.json()
            texts: list[str] = []
            calls: list[ToolCall] = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    texts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_use":
                    if block.get("name") == JSON_TOOL and json_schema is not None:
                        texts.append(json.dumps(block.get("input", {})))
                    else:
                        calls.append(ToolCall(id=str(block["id"]), name=str(block["name"]), arguments=block["input"]))
            usage = data.get("usage", {})
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _http_error("Anthropic API", exc, self._key) from exc
        return Completion(
            text="".join(texts),
            tool_calls=calls,
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0)), output_tokens=int(usage.get("output_tokens", 0))
            ),
            latency_ms=timer.ms,
        )

    async def web_search(self, query: str) -> WebAnswer:
        timer = Timer()
        body = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": query}],
            "tools": [{"type": ANTHROPIC_WEB_SEARCH_TOOL, "name": "web_search", "max_uses": 3}],
        }
        headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post("/v1/messages", json=body, headers=headers)
                response.raise_for_status()
                data = response.json()
            texts: list[str] = []
            sources: dict[str, WebSource] = {}
            for block in data.get("content", []):
                if block.get("type") != "text":
                    continue
                texts.append(str(block.get("text", "")))
                for cite in block.get("citations") or []:
                    if cite.get("url"):
                        sources[cite["url"]] = WebSource(title=str(cite.get("title", "")), url=str(cite["url"]))
            usage = data.get("usage", {})
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _http_error("Anthropic API", exc, self._key) from exc
        completion = Completion(
            text="".join(texts),
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0)), output_tokens=int(usage.get("output_tokens", 0))
            ),
            latency_ms=timer.ms,
        )
        return WebAnswer(text=completion.text, sources=list(sources.values()), completion=completion)


class GeminiProvider(LLMProvider):
    """Google Gemini `generateContent` over REST: an AI Studio key, or a Vertex AI key (express mode)."""

    name = "gemini"
    is_cloud = True
    supports_web_search = True

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 120.0,
        backend: Literal["ai_studio", "vertex"] = "ai_studio",
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._key = api_key
        self._timeout = httpx.Timeout(timeout_s, connect=10.0)
        vertex = backend == "vertex"
        self._base_url = base_url or (
            "https://aiplatform.googleapis.com" if vertex else "https://generativelanguage.googleapis.com"
        )
        self._path = f"/v1/publishers/google/models/{model}" if vertex else f"/v1beta/models/{model}"
        self._transport = transport

    @staticmethod
    def _contents(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                part = {"functionResponse": {"name": m.name or "tool", "response": {"content": m.content}}}
                if out and out[-1]["role"] == "user" and "functionResponse" in out[-1]["parts"][0]:
                    out[-1]["parts"].append(part)  # parallel results share one turn, as many as there were calls
                else:
                    out.append({"role": "user", "parts": [part]})
            elif m.role == "assistant":
                parts: list[dict[str, Any]] = [{"text": m.content}] if m.content else []
                for c in m.tool_calls:
                    call: dict[str, Any] = {"functionCall": {"name": c.name, "args": c.arguments}}
                    if c.signature:
                        call["thoughtSignature"] = c.signature  # Gemini 3 refuses a replayed call without it
                    parts.append(call)
                out.append({"role": "model", "parts": parts or [{"text": ""}]})
            else:
                out.append({"role": "user", "parts": [{"text": m.content}]})
        return out

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        timer = Timer()
        body: dict[str, Any] = {"contents": self._contents(messages)}
        system = _system_text(messages)
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parametersJsonSchema": t.parameters}
                        for t in tools
                    ]
                }
            ]
        if json_schema is not None:
            body["generationConfig"] = {"responseMimeType": "application/json", "responseJsonSchema": json_schema}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._path}:generateContent", json=body, headers={"x-goog-api-key": self._key}
                )
                response.raise_for_status()
                data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise LLMError(f"Gemini returned no candidates ({data.get('promptFeedback', {})})")
            texts: list[str] = []
            calls: list[ToolCall] = []
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part and not part.get("thought"):
                    texts.append(str(part["text"]))
                elif "functionCall" in part:
                    call = part["functionCall"]
                    calls.append(
                        ToolCall(
                            name=str(call["name"]),
                            arguments=dict(call.get("args") or {}),
                            signature=part.get("thoughtSignature"),
                        )
                    )
            meta = data.get("usageMetadata", {})
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _http_error("Gemini", exc, self._key) from exc
        return Completion(
            text="".join(texts),
            tool_calls=calls,
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=int(meta.get("promptTokenCount", 0)),
                output_tokens=int(meta.get("candidatesTokenCount", 0)),
            ),
            latency_ms=timer.ms,
        )

    async def web_search(self, query: str) -> WebAnswer:
        timer = Timer()
        body = {"contents": [{"role": "user", "parts": [{"text": query}]}], "tools": [{"google_search": {}}]}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._path}:generateContent", json=body, headers={"x-goog-api-key": self._key}
                )
                response.raise_for_status()
                data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise LLMError("Gemini returned no candidates for the web search")
            candidate = candidates[0]
            text = "".join(str(p.get("text", "")) for p in candidate.get("content", {}).get("parts", []))
            chunks = candidate.get("groundingMetadata", {}).get("groundingChunks") or []
            sources = [
                WebSource(title=str(c["web"].get("title", "")), url=str(c["web"]["uri"]))
                for c in chunks
                if c.get("web", {}).get("uri")
            ]
            meta = data.get("usageMetadata", {})
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _http_error("Gemini", exc, self._key) from exc
        completion = Completion(
            text=text,
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=int(meta.get("promptTokenCount", 0)),
                output_tokens=int(meta.get("candidatesTokenCount", 0)),
            ),
            latency_ms=timer.ms,
        )
        return WebAnswer(text=text, sources=sources, completion=completion)


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI's Chat Completions API, and any endpoint that speaks it (OpenRouter, DeepSeek and others)."""

    is_cloud = True

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        name: str = "openai",
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._key = api_key
        self._base_url = base_url.rstrip("/") + "/"
        self._timeout = httpx.Timeout(timeout_s, connect=10.0)
        self._transport = transport

    @staticmethod
    def _messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                out.append({"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content})
            elif m.role == "assistant" and m.tool_calls:
                out.append(
                    {
                        "role": "assistant",
                        "content": m.content or None,
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                            }
                            for c in m.tool_calls
                        ],
                    }
                )
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        timer = Timer()
        body: dict[str, Any] = {"model": self.model, "messages": self._messages(messages)}
        if tools:
            body["tools"] = [t.openai_style() for t in tools]
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "respond", "schema": json_schema}}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    "chat/completions", json=body, headers={"Authorization": f"Bearer {self._key}"}
                )
                response.raise_for_status()
                data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise LLMError(f"{self.name} returned no choices")
            message = choices[0].get("message", {})
            calls = [
                ToolCall(
                    id=str(c.get("id") or ""),
                    name=str(c["function"]["name"]),
                    arguments=json.loads(c["function"].get("arguments") or "{}"),
                )
                for c in message.get("tool_calls") or []
            ]
            usage = data.get("usage") or {}
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _http_error(self.name, exc, self._key) from exc
        return Completion(
            text=str(message.get("content") or ""),
            tool_calls=calls,
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=int(usage.get("prompt_tokens", 0)), output_tokens=int(usage.get("completion_tokens", 0))
            ),
            latency_ms=timer.ms,
        )
