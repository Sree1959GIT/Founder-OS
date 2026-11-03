from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.config import DeepProvider, Settings
from app.llm.base import Completion, LLMError, LLMUnavailable, Message, ToolCall, ToolSpec, parse_json_text
from app.llm.cloud import AnthropicAPIProvider, ClaudeAgentSDKProvider, GeminiProvider
from app.llm.fake import FakeProvider, schema_example
from app.llm.ollama import OllamaProvider
from app.llm.router import LLMRouter, build_cloud_provider, build_local_provider, build_router

TOOL = ToolSpec(
    name="get_metric",
    description="Get a metric",
    parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)


def recorder(handler: Any) -> tuple[httpx.MockTransport, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        seen.append({"path": request.url.path, "body": body, "headers": dict(request.headers)})
        return handler(request, body)

    return httpx.MockTransport(respond), seen


def ollama(*args: Any, **kwargs: Any) -> OllamaProvider:
    """An Ollama provider that skips the load check, so tests see only the call under test."""
    provider = OllamaProvider(*args, **kwargs)
    provider.ensure_loaded_before_calls = False
    return provider


# --- Ollama ---------------------------------------------------------------------------------------------------
async def test_ollama_tool_call_with_thinking_off() -> None:
    def handler(request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "get_metric", "arguments": {"name": "runway"}}}],
        }
        return httpx.Response(200, json={"message": message, "prompt_eval_count": 155, "eval_count": 21})

    transport, seen = recorder(handler)
    provider = ollama("http://ollama:11434/", "qwen3:8b", transport=transport)
    completion = await provider.complete([Message.user("What's our runway?")], tools=[TOOL])
    assert completion.tool_calls[0].name == "get_metric" and completion.tool_calls[0].arguments == {"name": "runway"}
    assert completion.usage.input_tokens == 155 and completion.provider == "ollama" and completion.model == "qwen3:8b"
    body = seen[0]["body"]
    assert seen[0]["path"] == "/api/chat" and body["think"] is False and body["stream"] is False
    assert body["model"] == "qwen3:8b" and body["keep_alive"] == "30m" and body["options"]["num_ctx"] == 8192
    assert body["tools"][0]["function"]["name"] == "get_metric"


async def test_ollama_json_schema_uses_format_and_zero_temperature() -> None:
    def handler(request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"choice": "finance"}'}})

    transport, seen = recorder(handler)
    schema = {"type": "object", "properties": {"choice": {"type": "string"}}}
    completion = await ollama("http://o", "qwen3:8b", transport=transport).complete(
        [Message.user("x")], json_schema=schema
    )
    assert completion.json() == {"choice": "finance"}
    assert seen[0]["body"]["format"] == schema and seen[0]["body"]["options"]["temperature"] == 0.0


async def test_ollama_tool_messages_round_trip() -> None:
    transport, seen = recorder(lambda r, b: httpx.Response(200, json={"message": {"content": "ok"}}))
    call = ToolCall(name="get_metric", arguments={"name": "runway"})
    messages = [Message.user("q"), Message.assistant("", [call]), Message.tool(call, '{"value": 10.65}')]
    await ollama("http://o", "m", transport=transport).complete(messages)
    sent = seen[0]["body"]["messages"]
    assert sent[1]["tool_calls"] == [{"function": {"name": "get_metric", "arguments": {"name": "runway"}}}]
    assert sent[2] == {"role": "tool", "content": '{"value": 10.65}', "tool_name": "get_metric"}


async def test_ollama_streams_ndjson() -> None:
    lines = [
        {"message": {"content": "Runway "}, "done": False},
        {"message": {"content": "is 10.65 months."}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 50, "eval_count": 9},
    ]
    content = "\n".join(json.dumps(x) for x in lines).encode()
    transport, seen = recorder(lambda r, b: httpx.Response(200, content=content))
    chunks = [
        c async for c in await ollama("http://o", "m", transport=transport).complete([Message.user("q")], stream=True)
    ]
    assert [c.delta for c in chunks if c.delta] == ["Runway ", "is 10.65 months."]
    assert chunks[-1].done and chunks[-1].completion is not None
    assert chunks[-1].completion.text == "Runway is 10.65 months." and chunks[-1].completion.usage.output_tokens == 9
    assert seen[0]["body"]["stream"] is True


async def test_ollama_errors_are_typed() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    down = ollama("http://o", "m", transport=httpx.MockTransport(refuse))
    with pytest.raises(LLMUnavailable, match="not reachable"):
        await down.complete([Message.user("q")])
    with pytest.raises(LLMUnavailable):
        _ = [c async for c in await down.complete([Message.user("q")], stream=True)]
    missing = OllamaProvider(
        "http://o", "qwen3:8b", transport=httpx.MockTransport(lambda r: httpx.Response(404, text="model not found"))
    )
    with pytest.raises(LLMUnavailable, match="not pulled"):
        await missing.complete([Message.user("q")])
    broken = ollama("http://o", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    with pytest.raises(LLMError) as info:
        await broken.complete([Message.user("q")])
    assert not isinstance(info.value, LLMUnavailable)


async def test_ollama_embed_and_loaded_models() -> None:
    def handler(request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "size_vram": 1}]})
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]] * len(body["input"])})

    transport, seen = recorder(handler)
    provider = ollama("http://o", "m", embed_model="nomic-embed-text", transport=transport)
    assert await provider.embed(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert seen[0]["body"]["model"] == "nomic-embed-text"
    assert (await provider.loaded_models())[0]["name"] == "qwen3:8b"
    assert await provider.embed([]) == []


async def test_ollama_warm_up_loads_with_the_chat_context_size() -> None:
    """A cold load from a slow disk took 217 s on the founder's PC; chat calls with a 180 s timeout aborted it."""
    transport, seen = recorder(lambda r, b: httpx.Response(200, json={"done": True}))
    seconds = await ollama("http://o", "qwen3:8b", num_ctx=8192, transport=transport).warm_up()
    assert seconds >= 0 and seen[0]["path"] == "/api/generate"
    assert seen[0]["body"] == {"model": "qwen3:8b", "keep_alive": "30m", "options": {"num_ctx": 8192}}
    down = ollama("http://o", "m", transport=httpx.MockTransport(lambda r: httpx.Response(404, text="no")))
    with pytest.raises(LLMUnavailable):
        await down.warm_up()


async def test_ollama_loads_an_unloaded_model_before_chatting() -> None:
    """After keep_alive expiry the model is unloaded; a 180 s chat call would abort a 217 s cold load forever."""
    loaded: list[dict[str, Any]] = []

    def handler(request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": loaded})
        if request.url.path == "/api/generate":
            loaded.append({"name": "qwen3:8b", "model": "qwen3:8b"})
            return httpx.Response(200, json={"done": True})
        return httpx.Response(200, json={"message": {"content": "hi"}})

    transport, seen = recorder(handler)
    provider = OllamaProvider("http://o", "qwen3:8b", transport=transport)
    await asyncio.gather(provider.complete([Message.user("a")]), provider.complete([Message.user("b")]))
    paths = [s["path"] for s in seen]
    assert paths.count("/api/generate") == 1 and paths[:2] == ["/api/ps", "/api/generate"]
    assert paths.count("/api/chat") == 2
    await provider.complete([Message.user("c")])  # checked within the last 60 s: no new /api/ps call
    assert [s["path"] for s in seen].count("/api/ps") == 1
    provider._loaded_at = -1e9  # a minute later, and the model is still loaded: no reload
    await provider.complete([Message.user("d")])
    assert [s["path"] for s in seen].count("/api/generate") == 1


# --- cloud providers -------------------------------------------------------------------------------------------
async def test_anthropic_tools_and_json() -> None:
    def handler(request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        if body.get("tool_choice"):
            content = [{"type": "tool_use", "id": "t1", "name": "respond", "input": {"choice": "yes"}}]
        else:
            content = [
                {"type": "text", "text": "Let me check."},
                {"type": "tool_use", "id": "t2", "name": "get_metric", "input": {"name": "mrr"}},
            ]
        return httpx.Response(200, json={"content": content, "usage": {"input_tokens": 12, "output_tokens": 3}})

    transport, seen = recorder(handler)
    provider = AnthropicAPIProvider("sk-test", "claude-x", transport=transport)
    call = ToolCall(id="t0", name="get_metric", arguments={"name": "runway"})
    messages = [
        Message.system("sys"),
        Message.user("q"),
        Message.assistant("", [call]),
        Message.tool(call, "10.65"),
    ]
    completion = await provider.complete(messages, tools=[TOOL])
    assert completion.text == "Let me check." and completion.tool_calls[0].id == "t2"
    sent = seen[0]
    assert sent["headers"]["x-api-key"] == "sk-test" and sent["body"]["system"] == "sys"
    assert sent["body"]["messages"][1]["content"][0]["type"] == "tool_use"
    assert sent["body"]["messages"][2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t0", "content": "10.65"}],
    }
    assert sent["body"]["tools"][0]["input_schema"] == TOOL.parameters
    as_json = await provider.complete([Message.user("q")], json_schema={"type": "object"})
    assert as_json.json() == {"choice": "yes"} and completion.usage.input_tokens == 12


async def test_anthropic_auth_failure_is_unavailable() -> None:
    provider = AnthropicAPIProvider("bad", "m", transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no")))
    with pytest.raises(LLMUnavailable):
        await provider.complete([Message.user("q")])
    bad_request = AnthropicAPIProvider(
        "k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad"))
    )
    with pytest.raises(LLMError) as info:
        await bad_request.complete([Message.user("q")])
    assert not isinstance(info.value, LLMUnavailable)


async def test_gemini_function_calls_and_json_config() -> None:
    def handler(request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        parts = [
            {"text": "thinking", "thought": True},
            {"functionCall": {"name": "get_metric", "args": {"name": "arr"}}},
        ]
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": parts}}],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 2},
            },
        )

    transport, seen = recorder(handler)
    provider = GeminiProvider("g-key", "gemini-2.5-flash", transport=transport)
    completion = await provider.complete(
        [Message.system("s"), Message.user("q")], tools=[TOOL], json_schema={"type": "object"}
    )
    assert completion.text == "" and completion.tool_calls[0].arguments == {"name": "arr"}
    sent = seen[0]
    assert (
        sent["path"] == "/v1beta/models/gemini-2.5-flash:generateContent"
        and sent["headers"]["x-goog-api-key"] == "g-key"
    )
    assert sent["body"]["systemInstruction"] == {"parts": [{"text": "s"}]}
    assert sent["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert sent["body"]["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"] == TOOL.parameters
    empty = GeminiProvider(
        "k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"candidates": []}))
    )
    with pytest.raises(LLMError, match="no candidates"):
        await empty.complete([Message.user("q")])


async def test_claude_sdk_provider_with_a_fake_sdk() -> None:
    seen: dict[str, Any] = {}

    class Options:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    async def query(prompt: str, options: Options) -> Any:
        seen["prompt"] = prompt
        yield SimpleNamespace(content=[SimpleNamespace(text='{"ok": true}')])
        yield SimpleNamespace(usage={"input_tokens": 4, "output_tokens": 2})

    sdk = SimpleNamespace(ClaudeAgentOptions=Options, query=query)
    provider = ClaudeAgentSDKProvider("oauth-token", "claude-x", sdk=sdk)
    completion = await provider.complete(
        [Message.system("be brief"), Message.user("hi")], json_schema={"type": "object"}
    )
    assert completion.json() == {"ok": True} and completion.usage.output_tokens == 2
    assert seen["model"] == "claude-x" and seen["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-token"
    assert "JSON Schema" in seen["system_prompt"] and "USER: hi" in seen["prompt"] and seen["allowed_tools"] == []
    with pytest.raises(LLMError, match="does not support tool calls"):
        await provider.complete([Message.user("q")], tools=[TOOL])


async def test_claude_sdk_missing_package_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    def boom(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", boom)
    with pytest.raises(LLMUnavailable, match="not installed"):
        await ClaudeAgentSDKProvider("t", "m").complete([Message.user("q")])


# --- router ----------------------------------------------------------------------------------------------------
async def test_router_never_sends_local_agents_to_the_cloud() -> None:
    local, cloud = FakeProvider(["local"]), FakeProvider(["cloud"], name="cloudy", is_cloud=True)
    router = LLMRouter(local, cloud, cloud_allowed=True)
    assert (await router.complete("local", [Message.user("q")])).text == "local"
    assert (await router.complete("cloud_allowed", [Message.user("q")])).text == "cloud"
    assert LLMRouter(local, cloud, cloud_allowed=False).chain("cloud") == [local]


async def test_router_falls_back_to_local_and_records_it() -> None:
    local = FakeProvider(["from ollama"])
    cloud = FakeProvider([LLMUnavailable("no credits")], name="anthropic", is_cloud=True)
    completion = await LLMRouter(local, cloud, cloud_allowed=True).complete("cloud", [Message.user("q")])
    assert completion.text == "from ollama" and completion.fallback_from == "anthropic"
    local_down = LLMRouter(FakeProvider([LLMUnavailable("down")]))
    with pytest.raises(LLMUnavailable):
        await local_down.complete("local", [Message.user("q")])


async def test_router_skips_cloud_without_tool_support_and_streams_with_fallback() -> None:
    local = FakeProvider(["a", "streamed"])
    sdk = FakeProvider(name="claude_sdk", is_cloud=True, supports_tools=False)
    router = LLMRouter(local, sdk, cloud_allowed=True)
    assert router.chain("cloud", needs_tools=True) == [local]
    assert (await router.complete("cloud", [Message.user("q")], tools=[TOOL])).text == "a"
    failing = FakeProvider([LLMUnavailable("x")], name="gemini", is_cloud=True)
    chunks = [c async for c in LLMRouter(local, failing, cloud_allowed=True).stream("cloud", [Message.user("q")])]
    assert chunks[0].delta == "streamed" and chunks[-1].completion is not None
    assert chunks[-1].completion.fallback_from == "gemini"


def test_build_router_from_settings() -> None:
    s = Settings(_env_file=None, llm_provider="ollama", ollama_chat_model="qwen3:8b", ollama_keep_alive="")
    local = build_local_provider(s)
    assert isinstance(local, OllamaProvider) and local.model == "qwen3:8b" and local.think is False
    assert local.keep_alive is None
    assert build_cloud_provider(s) is None  # cloud is off by default
    cloud_on = Settings(_env_file=None, cloud_allowed=True, deep_provider=DeepProvider.ANTHROPIC, anthropic_api_key="k")
    assert isinstance(build_cloud_provider(cloud_on), AnthropicAPIProvider)
    gemini = Settings(_env_file=None, cloud_allowed=True, deep_provider=DeepProvider.GEMINI, gemini_api_key="k")
    assert isinstance(build_cloud_provider(gemini), GeminiProvider)
    sdk = Settings(
        _env_file=None, cloud_allowed=True, deep_provider=DeepProvider.CLAUDE_SDK, claude_code_oauth_token="t"
    )
    assert isinstance(build_cloud_provider(sdk), ClaudeAgentSDKProvider)
    no_key = Settings(_env_file=None, cloud_allowed=True, deep_provider=DeepProvider.GEMINI)
    assert build_cloud_provider(no_key) is None
    assert isinstance(build_router(Settings(_env_file=None, llm_provider="fake")).local, FakeProvider)


def test_default_chat_model_is_qwen3_with_thinking_off() -> None:
    s = Settings(_env_file=None)
    assert s.ollama_chat_model == "qwen3:8b" and s.ollama_think is False and s.team_approval == "cloud_only"
    assert (s.max_local_agents, s.max_cloud_agents) == (2, 6)


def test_parse_json_text_and_schema_example() -> None:
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('Sure! {"a": 2} hope this helps') == {"a": 2}
    with pytest.raises(LLMError):
        parse_json_text("no json here")
    schema = {
        "type": "object",
        "properties": {"c": {"enum": ["x", "y"]}, "p": {"type": "number"}, "l": {"type": "array"}},
        "required": ["c", "p", "l"],
    }
    assert schema_example(schema) == {"c": "x", "p": 0, "l": []}


async def test_fake_provider_script() -> None:
    provider = FakeProvider(
        ["one", [ToolCall(name="t")], lambda m, t, s: "computed", Completion(text="c", provider="x", model="y")]
    )
    assert (await provider.complete([Message.user("q")])).text == "one"
    assert (await provider.complete([Message.user("q")])).tool_calls[0].name == "t"
    assert (await provider.complete([Message.user("q")])).text == "computed"
    assert (await provider.complete([Message.user("q")])).provider == "x"
    assert (await provider.complete([Message.user("q")], json_schema={"type": "object", "properties": {}})).json() == {}
    assert len(provider.calls) == 5
