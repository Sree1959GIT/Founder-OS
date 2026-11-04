"""Cloud providers for "deep work" agents (PRD §4): Anthropic API, Gemini and the Claude Agent SDK.

Anthropic and Gemini are called over their REST APIs with httpx (no SDK dependency; tests use `httpx.MockTransport`).
The Claude Agent SDK (`claude-agent-sdk`, needs the Claude Code CLI) is imported lazily, so it stays optional.
Every failure raises `LLMUnavailable` or `LLMError`; the router then falls back to Ollama (PRD R3).
Model IDs come from config (`CLAUDE_MODEL`, `GEMINI_MODEL`), never from agent code.
"""

from __future__ import annotations

import importlib
import json
import os
from typing import Any

import httpx

from app.llm.base import Completion, LLMError, LLMProvider, LLMUnavailable, Message, Timer, ToolCall, ToolSpec, Usage

JSON_TOOL = "respond"


def _http_error(provider: str, exc: Exception) -> LLMError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = exc.response.text[:300]
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
    def _messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
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
            "messages": self._messages(messages),
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
            raise _http_error("Anthropic API", exc) from exc
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


class GeminiProvider(LLMProvider):
    """Google Gemini `generateContent` over REST (`GEMINI_API_KEY`)."""

    name = "gemini"
    is_cloud = True

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 120.0,
        base_url: str = "https://generativelanguage.googleapis.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._key = api_key
        self._timeout = httpx.Timeout(timeout_s, connect=10.0)
        self._base_url = base_url
        self._transport = transport

    @staticmethod
    def _contents(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                part = {"functionResponse": {"name": m.name or "tool", "response": {"content": m.content}}}
                out.append({"role": "user", "parts": [part]})
            elif m.role == "assistant":
                parts: list[dict[str, Any]] = [{"text": m.content}] if m.content else []
                parts += [{"functionCall": {"name": c.name, "args": c.arguments}} for c in m.tool_calls]
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
                    f"/v1beta/models/{self.model}:generateContent", json=body, headers={"x-goog-api-key": self._key}
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
                    calls.append(ToolCall(name=str(call["name"]), arguments=dict(call.get("args") or {})))
            meta = data.get("usageMetadata", {})
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _http_error("Gemini", exc) from exc
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


class ClaudeAgentSDKProvider(LLMProvider):
    """Claude on the founder's subscription through the Claude Agent SDK (`CLAUDE_CODE_OAUTH_TOKEN`). Personal use.

    The SDK runs Claude Code as a subprocess: calls take several seconds and never sit in the voice path. Custom tool
    calls are not supported here (the router falls back to Ollama for tool-using agents); JSON output is requested in
    the prompt and parsed.
    """

    name = "claude_sdk"
    is_cloud = True
    supports_tools = False

    def __init__(self, oauth_token: str, model: str, *, sdk: Any | None = None) -> None:
        self.model = model
        self._token = oauth_token
        self._sdk = sdk

    def _load(self) -> Any:
        if self._sdk is not None:
            return self._sdk
        try:
            self._sdk = importlib.import_module("claude_agent_sdk")
        except ImportError as exc:
            raise LLMUnavailable("claude-agent-sdk is not installed (pip install claude-agent-sdk)") from exc
        return self._sdk

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        sdk = self._load()
        timer = Timer()
        system = _system_text(messages)
        if json_schema is not None:
            system += "\n\nReply with only a JSON object matching this JSON Schema:\n" + json.dumps(json_schema)
        transcript = "\n\n".join(f"{m.role.upper()}: {m.content}" for m in messages if m.role != "system" and m.content)
        env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": self._token}
        try:
            options = sdk.ClaudeAgentOptions(
                model=self.model, system_prompt=system or None, max_turns=1, allowed_tools=[], env=env
            )
            texts: list[str] = []
            usage = Usage()
            async for message in sdk.query(prompt=transcript, options=options):
                for block in getattr(message, "content", None) or []:
                    text = getattr(block, "text", None)
                    if isinstance(text, str):
                        texts.append(text)
                raw_usage = getattr(message, "usage", None)
                if isinstance(raw_usage, dict):
                    usage = Usage(
                        input_tokens=int(raw_usage.get("input_tokens", 0)),
                        output_tokens=int(raw_usage.get("output_tokens", 0)),
                    )
        except LLMError:
            raise
        except Exception as exc:  # the SDK raises CLINotFoundError, ProcessError, ... (all mean "not usable now")
            raise LLMUnavailable(f"Claude Agent SDK failed ({type(exc).__name__}: {exc})") from exc
        if not texts:
            raise LLMError("Claude Agent SDK returned no text")
        return Completion(text="".join(texts), provider=self.name, model=self.model, usage=usage, latency_ms=timer.ms)
