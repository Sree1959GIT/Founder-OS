"""The LLM provider interface (PRD §4): one shape for Ollama, Anthropic, Gemini, OpenAI-style APIs and the fake.

`complete(messages, tools=None, json_schema=None, stream=False)` returns a `Completion` (text, tool calls, usage).
With `stream=True` it returns an async iterator of `StreamChunk`s whose last chunk carries the full `Completion`.
`embed(texts)` returns one vector per text. Providers raise `LLMUnavailable` when the service cannot be reached (the
router then falls back to Ollama, PRD R3) and `LLMError` for anything else that went wrong.
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal, overload

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class LLMError(Exception):
    """The provider answered, but not usefully (bad request, malformed output, unsupported feature)."""


class LLMUnavailable(LLMError):
    """The provider cannot be reached or is not configured. Callers fall back (PRD R3)."""


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # role == "tool": which call this answers
    name: str | None = None  # role == "tool": the tool name

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str, tool_calls: list[ToolCall] | None = None) -> Message:
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool(cls, call: ToolCall, content: str) -> Message:
        return cls(role="tool", content=content, tool_call_id=call.id, name=call.name)


class ToolSpec(BaseModel):
    """A function the model may call. `parameters` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})

    def openai_style(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens, output_tokens=self.output_tokens + other.output_tokens
        )


class Completion(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    provider: str
    model: str
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0
    fallback_from: str | None = Field(default=None, description="Provider that failed before this one answered")
    est_cost_usd: float | None = Field(default=None, description="From the router's price table; 0 for local models")

    def json(self) -> Any:  # type: ignore[override]
        """The text parsed as JSON (for `json_schema` calls). Tolerates code fences around the object."""
        return parse_json_text(self.text)


class StreamChunk(BaseModel):
    delta: str = ""
    done: bool = False
    completion: Completion | None = None  # set on the final chunk


class WebSource(BaseModel):
    title: str = ""
    url: str


class WebAnswer(BaseModel):
    """A grounded search: the provider's text, the pages behind it, and the call for cost accounting."""

    text: str
    sources: list[WebSource] = Field(default_factory=list)
    completion: Completion


class LLMProvider(ABC):
    """Base class of every provider. `name` is e.g. "ollama"; `is_cloud` drives privacy routing (PRD R2).

    Subclasses implement `_complete` (and `_stream` when the service streams natively; the default streams the
    finished completion as one chunk) and, when they can, `embed`.
    """

    name: str = "provider"
    model: str = ""
    is_cloud: bool = False
    supports_tools: bool = True
    supports_web_search: bool = False

    @overload
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
        stream: Literal[False] = False,
    ) -> Completion: ...

    @overload
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
        *,
        stream: Literal[True],
    ) -> AsyncIterator[StreamChunk]: ...

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> Completion | AsyncIterator[StreamChunk]:
        if tools and not self.supports_tools:
            raise LLMError(f"{self.name} does not support tool calls")
        if stream:
            return self._stream(messages, tools, json_schema)
        return await self._complete(messages, tools, json_schema)

    @abstractmethod
    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion: ...

    async def _stream(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> AsyncIterator[StreamChunk]:
        completion = await self._complete(messages, tools, json_schema)
        async for chunk in single_chunk_stream(completion):
            yield chunk

    async def web_search(self, query: str) -> WebAnswer:
        raise LLMError(f"{self.name} does not provide web search")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise LLMError(f"{self.name} does not provide embeddings")


def parse_json_text(text: str) -> Any:
    """Parse model output as JSON, allowing ```json fences or prose around a single object."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[4:] if cleaned.lower().startswith("json") else cleaned
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError(f"model did not return valid JSON: {text[:200]!r}")


async def single_chunk_stream(completion: Completion) -> AsyncIterator[StreamChunk]:
    """Turn a finished completion into a stream (providers without native streaming)."""
    if completion.text:
        yield StreamChunk(delta=completion.text)
    yield StreamChunk(done=True, completion=completion)


class Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000, 1)
