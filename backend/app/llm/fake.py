"""`FakeProvider`: scripted responses for tests (and `LLM_PROVIDER=fake` demos without Ollama).

Script entries are used in order. Each entry is a `Completion`, a plain string (the reply text), a `ToolCall` list
(the model asks for those tools), an exception instance (raised), or a callable `(messages, tools, json_schema) ->
any of the above`. When the script runs out, `default` answers: a callable, or by default an empty-but-valid reply
(a minimal object for `json_schema` calls).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.llm.base import Completion, LLMProvider, Message, ToolCall, ToolSpec, Usage

Reply = Completion | str | list[ToolCall] | BaseException
Responder = Callable[[list[Message], list[ToolSpec] | None, dict[str, Any] | None], "Reply"]


def schema_example(schema: dict[str, Any]) -> Any:
    """A minimal value that satisfies a simple JSON Schema (first enum value, empty strings, zero numbers)."""
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        props = schema.get("properties", {})
        return {k: schema_example(v) for k, v in props.items() if k in schema.get("required", props)}
    if kind == "array":
        return []
    if kind in ("number", "integer"):
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    return ""


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(
        self,
        script: list[Reply | Responder] | None = None,
        *,
        default: Responder | None = None,
        name: str = "fake",
        model: str = "fake-model",
        is_cloud: bool = False,
        supports_tools: bool = True,
    ) -> None:
        self.script: list[Reply | Responder] = list(script or [])
        self.default = default
        self.name = name
        self.model = model
        self.is_cloud = is_cloud
        self.supports_tools = supports_tools
        self.calls: list[dict[str, Any]] = []

    async def _complete(
        self, messages: list[Message], tools: list[ToolSpec] | None, json_schema: dict[str, Any] | None
    ) -> Completion:
        self.calls.append({"messages": messages, "tools": tools, "json_schema": json_schema})
        if self.script:
            entry: Any = self.script.pop(0)
        elif self.default is not None:
            entry = self.default
        else:
            entry = json.dumps(schema_example(json_schema)) if json_schema is not None else "OK."
        if callable(entry) and not isinstance(entry, BaseException | Completion):
            entry = entry(messages, tools, json_schema)
        if isinstance(entry, BaseException):
            raise entry
        if isinstance(entry, Completion):
            return entry
        if isinstance(entry, list):
            return Completion(tool_calls=entry, provider=self.name, model=self.model, usage=Usage(output_tokens=5))
        text = str(entry)
        return Completion(
            text=text, provider=self.name, model=self.model, usage=Usage(input_tokens=10, output_tokens=len(text) // 4)
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from app.engine.embeddings import FakeEmbedder

        return FakeEmbedder().embed_documents(texts)
