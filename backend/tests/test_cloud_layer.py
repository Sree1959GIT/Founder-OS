"""The cloud layer: providers, per-agent routes, the privacy filter on every payload, cost, the cap, the voice items."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.agents.guards import in_one_voice
from app.agents.verifier import format_money, one_money_format
from app.config import DeepProvider, Settings
from app.llm.base import LLMError, LLMUnavailable, Message, ToolCall, ToolSpec, Usage
from app.llm.cloud import AnthropicAPIProvider, GeminiProvider, OpenAICompatibleProvider
from app.llm.costs import DEFAULT_PRICES, CallRecord, CostLedger
from app.llm.fake import FakeProvider
from app.llm.names import customer_names, vault_names
from app.llm.privacy import FilterReport, NameIndex, StreamRestorer, filter_messages, filter_text, filter_tool_result
from app.llm.router import LLMRouter, build_cloud_provider, build_router, build_routes
from app.vault.manager import VaultManager

TOOL = ToolSpec(name="t", description="d")
KEY = "sk-SECRET-KEY-123"


def settings(**kwargs: Any) -> Settings:
    return Settings(_env_file=None, **kwargs)


class Recording(FakeProvider):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.seen: list[list[Message]] = []

    async def _complete(self, messages: list[Message], tools: Any, json_schema: Any) -> Any:
        self.seen.append(messages)
        return await super()._complete(messages, tools, json_schema)


# --- the subscription path is gone ----------------------------------------------------------------------------------
def test_there_is_no_subscription_provider() -> None:
    assert "claude_sdk" not in {p.value for p in DeepProvider}
    assert not hasattr(settings(), "claude_code_oauth_token")
    assert build_cloud_provider(settings(cloud_allowed=True, deep_provider="claude_sdk")) is None


# --- providers -------------------------------------------------------------------------------------------------------
async def test_openai_provider_speaks_chat_completions() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        message = {
            "content": None,
            "tool_calls": [{"id": "c1", "function": {"name": "t", "arguments": '{"a": 1}'}}],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": message}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        )

    provider = OpenAICompatibleProvider(KEY, "gpt-x", transport=httpx.MockTransport(handler))
    call = ToolCall(id="c0", name="t", arguments={"b": 2})
    done = await provider.complete(
        [Message.system("s"), Message.user("q"), Message.assistant("", [call]), Message.tool(call, "r")], tools=[TOOL]
    )
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["messages"][2]["tool_calls"][0]["function"]["name"] == "t"
    assert seen["body"]["messages"][3] == {"role": "tool", "tool_call_id": "c0", "content": "r"}
    assert done.tool_calls[0].arguments == {"a": 1}
    assert (done.usage.input_tokens, done.usage.output_tokens) == (7, 3)


async def test_an_openai_compatible_endpoint_uses_its_own_base_url_and_asks_for_json() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    provider = OpenAICompatibleProvider(
        KEY,
        "deepseek-chat",
        name="openai_compatible",
        base_url="https://openrouter.ai/api/v1/",
        transport=httpx.MockTransport(handler),
    )
    done = await provider.complete([Message.user("q")], json_schema={"type": "object"})
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert done.json() == {"ok": True}
    assert done.provider == "openai_compatible"


@pytest.mark.parametrize(
    "make",
    [
        lambda t: AnthropicAPIProvider(KEY, "m", transport=t),
        lambda t: GeminiProvider(KEY, "m", transport=t),
        lambda t: OpenAICompatibleProvider(KEY, "m", transport=t),
    ],
)
async def test_a_key_echoed_in_an_error_never_reaches_the_message(make: Any) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(401, text=f"bad key {KEY}"))
    with pytest.raises(LLMUnavailable) as caught:
        await make(transport).complete([Message.user("q")])
    assert KEY not in str(caught.value)


async def test_gemini_on_vertex_uses_the_vertex_path() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "hi"}]}}]})

    provider = GeminiProvider(KEY, "gemini-x", backend="vertex", transport=httpx.MockTransport(handler))
    assert (await provider.complete([Message.user("q")])).text == "hi"
    assert seen["url"] == "https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-x:generateContent"


async def test_web_search_returns_the_pages_behind_the_answer() -> None:
    def gemini(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["tools"] == [{"google_search": {}}]
        grounding = {"groundingChunks": [{"web": {"uri": "https://x.test/a", "title": "A"}}]}
        candidate = {"content": {"parts": [{"text": "found"}]}, "groundingMetadata": grounding}
        return httpx.Response(200, json={"candidates": [candidate]})

    answer = await GeminiProvider(KEY, "m", transport=httpx.MockTransport(gemini)).web_search("q")
    assert answer.text == "found"
    assert [s.url for s in answer.sources] == ["https://x.test/a"]

    def anthropic(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["tools"][0]["name"] == "web_search"
        block = {"type": "text", "text": "seen", "citations": [{"url": "https://y.test/b", "title": "B"}]}
        return httpx.Response(200, json={"content": [{"type": "server_tool_use"}, block]})

    answer = await AnthropicAPIProvider(KEY, "m", transport=httpx.MockTransport(anthropic)).web_search("q")
    assert answer.text == "seen"
    assert [s.title for s in answer.sources] == ["B"]


# --- settings to routes ----------------------------------------------------------------------------------------------
def test_gemini_replays_parallel_results_in_one_turn_with_the_signature() -> None:
    call_a = ToolCall(id="a", name="f", arguments={}, signature="sig-a")
    call_b = ToolCall(id="b", name="g", arguments={})
    contents = GeminiProvider._contents(
        [
            Message.user("q"),
            Message.assistant("", tool_calls=[call_a, call_b]),
            Message.tool(call_a, "1"),
            Message.tool(call_b, "2"),
        ]
    )
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert len(contents[2]["parts"]) == 2
    assert contents[1]["parts"][0]["thoughtSignature"] == "sig-a" and "thoughtSignature" not in contents[1]["parts"][1]


async def test_gemini_keeps_the_signature_it_was_given() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        part = {"functionCall": {"name": "f", "args": {}}, "thoughtSignature": "sig"}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [part]}}]})

    provider = GeminiProvider(KEY, "m", transport=httpx.MockTransport(reply))
    completion = await provider.complete(
        [Message.user("q")], tools=[ToolSpec(name="f", description="d", parameters={})]
    )
    assert completion.tool_calls[0].signature == "sig"


async def test_anthropic_gets_no_tool_blocks_in_a_request_with_no_tools() -> None:
    bodies: list[dict[str, Any]] = []

    def reply(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}], "usage": {}})

    provider = AnthropicAPIProvider(KEY, "m", transport=httpx.MockTransport(reply))
    call = ToolCall(id="a", name="f", arguments={})
    history = [Message.user("q"), Message.assistant("", tool_calls=[call]), Message.tool(call, "result")]
    await provider.complete(history)
    assert "tool_use" not in json.dumps(bodies[0]) and "tool_result" not in json.dumps(bodies[0])
    assert "result" in json.dumps(bodies[0]["messages"])
    await provider.complete(history, tools=[ToolSpec(name="f", description="d", parameters={})])
    assert "tool_use" in json.dumps(bodies[1])


@pytest.mark.parametrize("row", ["| Acme | 12000 |", "Acme, Pro, 12000", "Acme,12000", "Acme | $1.2M", "Acme\t12k"])
def test_short_data_rows_never_reach_the_cloud(row: str) -> None:
    assert "Acme" not in filter_text(f"Our customers:\n{row}\nThat is all.")


@pytest.mark.parametrize(
    "line", ["In Q3, 12 customers left, 400 stayed.", "Pricing, churn and the pipeline.", "MRR is $400,000."]
)
def test_prose_with_numbers_is_kept(line: str) -> None:
    assert filter_text(line) == line


def test_a_tool_result_that_cannot_be_parsed_is_withheld() -> None:
    cut = '{"rows":[{"customer":"Acme","mrr":12000,"note":"long'
    assert "Acme" not in filter_tool_result(cut) and "withheld" in filter_tool_result(cut)


def test_each_provider_needs_its_own_key() -> None:
    assert build_cloud_provider(settings(cloud_allowed=True, deep_provider="openai")) is None
    openai = build_cloud_provider(settings(cloud_allowed=True, deep_provider="openai", openai_api_key="k"))
    assert openai is not None and openai.name == "openai" and openai.model == "gpt-6.1-terra"
    half = settings(cloud_allowed=True, deep_provider="openai_compatible", openai_compatible_api_key="k")
    assert build_cloud_provider(half) is None
    other = settings(
        cloud_allowed=True,
        deep_provider="openai_compatible",
        openai_compatible_api_key="k",
        openai_compatible_base_url="https://api.deepseek.com/v1",
        openai_compatible_model="deepseek-chat",
    )
    built = build_cloud_provider(other)
    assert built is not None and built.name == "openai_compatible" and built.model == "deepseek-chat"
    vertex = settings(cloud_allowed=True, deep_provider="gemini", gemini_backend="vertex", gemini_api_key="k")
    assert build_cloud_provider(vertex) is None  # Vertex needs its own key
    assert build_cloud_provider(
        settings(cloud_allowed=True, deep_provider="gemini", gemini_backend="vertex", vertex_api_key="k")
    )


def test_cloud_is_off_by_default_even_with_keys() -> None:
    s = settings(anthropic_api_key="k", deep_provider="anthropic", agent_models={"memo_writer": "anthropic"})
    router = build_router(s)
    assert router.cloud is None and router.routes == {}
    assert router.primary("cloud", agent_type="memo_writer") is router.local


def test_each_agent_type_can_choose_its_provider_and_model() -> None:
    s = settings(
        cloud_allowed=True,
        anthropic_api_key="a",
        gemini_api_key="g",
        deep_provider="gemini",
        agent_models={
            "memo_writer": "anthropic:claude-opus-5-5",
            "people_ops": "ollama",
            "market_scout": "nonsense",
            "regulatory_tax": "openai",  # no key
        },
    )
    routes = build_routes(s)
    assert routes["memo_writer"] is not None and routes["memo_writer"].model == "claude-opus-5-5"
    assert routes["people_ops"] is None
    assert "market_scout" not in routes and "regulatory_tax" not in routes
    router = build_router(s)
    assert router.primary("cloud_allowed", agent_type="memo_writer").name == "anthropic"
    assert router.primary("cloud_allowed", agent_type="people_ops") is router.local
    assert router.primary("cloud", agent_type="market_scout").name == "gemini"
    assert router.primary("local", agent_type="memo_writer") is router.local


def test_settings_never_show_a_key() -> None:
    s = settings(openai_api_key=KEY, vertex_api_key=KEY, openai_compatible_api_key=KEY)
    assert KEY not in repr(s)
    assert KEY not in s.model_dump_json()


# --- the privacy filter ----------------------------------------------------------------------------------------------
def test_data_rows_are_removed_and_sentences_with_numbers_stay() -> None:
    text = (
        "Runway is 10.65 months, with net burn of $172,280.47.\n"
        "month,revenue,cogs\n"
        "2026-09,257844.27,71850.06\n"
        "2026-10,255000.00,70000.00\n"
        "| Acme | 12000 | 3 |\n"
        "We see 3, 4 or 5 options for the team and each of them has trade-offs for us to weigh."
    )
    cleaned = filter_text(text)
    assert "257844.27" not in cleaned
    assert "12000" not in cleaned
    assert "10.65 months" in cleaned and "$172,280.47" in cleaned
    assert "3, 4 or 5 options" in cleaned
    assert "data rows removed" in cleaned


def test_emails_are_removed() -> None:
    assert "cfo@acme.test" not in filter_text("Ask cfo@acme.test about it.")


def test_query_rows_never_reach_a_cloud_payload() -> None:
    payload = {"columns": ["customer", "mrr"], "rows": [["Acme", 12000], ["Globex", 9000]], "row_count": 2}
    cleaned = json.loads(filter_tool_result(json.dumps(payload)))
    assert "rows" not in cleaned and cleaned["rows_removed"] == 2
    assert "Acme" not in json.dumps(cleaned)


def test_a_metric_keeps_its_summary_and_gets_a_lineage_id() -> None:
    payload = {
        "metric": "runway",
        "label": "Runway",
        "value": 10.65,
        "as_of": "2026-10",
        "lineage": {"formula": "a/b", "period": "2026-08..2026-10", "inputs": {"closing_cash": 1835125.06}},
    }
    cleaned = json.loads(filter_tool_result(json.dumps(payload)))
    assert cleaned["value"] == 10.65
    assert cleaned["lineage_id"] == "runway@2026-08..2026-10"
    assert "lineage" not in cleaned and "1835125.06" not in json.dumps(cleaned)


def test_an_unnamed_table_is_replaced_by_a_count() -> None:
    payload = {"anything": [{"name": "Acme", "mrr": 12000}, {"name": "Globex", "mrr": 9000}], "metrics": [{"value": 1}]}
    cleaned = json.loads(filter_tool_result(json.dumps(payload)))
    assert cleaned["anything"] == "[2 data rows removed by the privacy filter]"
    assert cleaned["metrics"] == [{"value": 1}]


def test_a_cut_off_tool_result_is_still_filtered() -> None:
    assert "257844.27" not in filter_tool_result('{"text": "x\n2026-09,257844.27,71850.06')


async def test_every_cloud_payload_is_filtered_and_the_local_fallback_sees_the_original() -> None:
    rows = "2026-09,257844.27,71850.06"
    cloud = Recording([LLMUnavailable("down")], name="c", is_cloud=True, model="claude-sonnet-5-5")
    local = Recording(["from local"])
    router = LLMRouter(local, cloud, cloud_allowed=True)
    done = await router.complete("cloud", [Message.system("s"), Message.user(rows)], agent_type="memo_writer")
    assert rows not in cloud.seen[0][1].content
    assert local.seen[0][1].content == rows
    assert done.text == "from local" and done.fallback_from == "c"


async def test_a_streamed_cloud_call_is_filtered_too() -> None:
    rows = "2026-09,257844.27,71850.06"
    cloud = Recording(["hello"], name="c", is_cloud=True)
    router = LLMRouter(FakeProvider(), cloud, cloud_allowed=True)
    [_ async for _ in router.stream("cloud", [Message.user(rows)])]
    assert rows not in cloud.seen[0][0].content


def test_filtering_leaves_the_original_messages_alone() -> None:
    message = Message.user("2026-09,257844.27,71850.06")
    filtered, report = filter_messages([message])
    assert report.rows_removed == 1
    assert filtered[0].content != message.content
    assert message.content == "2026-09,257844.27,71850.06"


# --- cost, latency and the cap ---------------------------------------------------------------------------------------
def ledger(tmp_path: Path, cap: float = 25.0) -> CostLedger:
    return CostLedger(tmp_path / "llm_calls.jsonl", monthly_cap_usd=cap)


def test_cost_comes_from_the_price_table(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    usage = Usage(input_tokens=1_000_000, output_tokens=500_000)
    assert book.estimate("claude-sonnet-5-5", usage) == pytest.approx(2.0 + 5.0)
    assert book.estimate("unknown-model", usage) is None
    assert CostLedger(tmp_path / "x", prices={"m": (1.0, 1.0)}).estimate("m", usage) == pytest.approx(1.5)
    assert "gemini-3.8-flash" in DEFAULT_PRICES


async def test_every_call_is_recorded_with_cost_and_latency_and_no_payload(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    cloud = FakeProvider(["secret answer"], name="anthropic", is_cloud=True, model="claude-sonnet-5-5")
    local = FakeProvider(["local answer"])
    router = LLMRouter(local, cloud, cloud_allowed=True, ledger=book)
    done = await router.complete("cloud", [Message.user("secret question")], agent_type="memo_writer")
    await router.complete("local", [Message.user("q")], agent_type="advisor")
    assert done.est_cost_usd is not None
    stats = book.stats()
    assert stats["memo_writer"]["cloud_calls"] == 1 and stats["advisor"]["cloud_calls"] == 0
    assert stats["advisor"]["est_cost_usd"] == 0
    assert stats["memo_writer"]["latency_ms_p50"] is not None
    written = book.path.read_text(encoding="utf-8")
    assert "secret" not in written
    assert len(written.splitlines()) == 2


async def test_a_failed_call_is_counted_and_costs_nothing(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    cloud = FakeProvider([LLMUnavailable("down")], name="c", is_cloud=True, model="claude-sonnet-5-5")
    router = LLMRouter(FakeProvider(["ok"]), cloud, cloud_allowed=True, ledger=book)
    await router.complete("cloud", [Message.user("q")], agent_type="a")
    assert book.stats()["a"]["errors"] == 1
    assert book.month_spend() == 0


def test_the_cap_sends_cloud_agents_to_ollama(tmp_path: Path) -> None:
    book = ledger(tmp_path, cap=1.0)
    cloud = FakeProvider(name="c", is_cloud=True, model="claude-sonnet-5-5")
    local = FakeProvider()
    router = LLMRouter(local, cloud, cloud_allowed=True, ledger=book)
    assert router.primary("cloud") is cloud
    book.record(CallRecord(provider="c", model="claude-sonnet-5-5", is_cloud=True, est_cost_usd=1.0))
    assert router.chain("cloud") == [local]
    assert book.summary()["over_cap"] is True
    assert book.summary()["remaining_usd"] == 0


def test_a_cap_of_zero_means_no_cloud_calls(tmp_path: Path) -> None:
    local = FakeProvider()
    cloud = FakeProvider(name="c", is_cloud=True, model="claude-sonnet-5-5")
    assert LLMRouter(local, cloud, cloud_allowed=True, ledger=ledger(tmp_path, cap=0)).chain("cloud") == [local]


def test_a_model_with_no_known_price_is_not_called(tmp_path: Path) -> None:
    local = FakeProvider()
    cloud = FakeProvider(name="c", is_cloud=True, model="mystery")
    assert LLMRouter(local, cloud, cloud_allowed=True, ledger=ledger(tmp_path)).chain("cloud") == [local]
    priced = CostLedger(tmp_path / "y", prices={"mystery": (1.0, 2.0)})
    assert LLMRouter(local, cloud, cloud_allowed=True, ledger=priced).chain("cloud") == [cloud, local]


def test_the_month_is_read_back_after_a_restart(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    book.record(CallRecord(provider="c", model="m", is_cloud=True, est_cost_usd=0.5))
    book.path.write_text(book.path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    assert ledger(tmp_path).month_spend() == pytest.approx(0.5)


async def test_a_web_search_goes_through_the_filter_and_the_ledger(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    searches: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        searches.append(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "found"}]}}]})

    cloud = GeminiProvider(KEY, "gemini-3.8-flash", transport=httpx.MockTransport(handler))
    router = LLMRouter(FakeProvider(), cloud, cloud_allowed=True, ledger=book)
    assert router.can_search_web("cloud", "market_scout")
    answer = await router.web_search("cloud", "Dubai office\n2026-09,257844.27,71850.06", agent_type="market_scout")
    assert answer.text == "found"
    assert "257844.27" not in searches[0]
    assert book.stats()["market_scout"]["calls"] == 1
    assert not LLMRouter(FakeProvider()).can_search_web("cloud", "market_scout")
    with pytest.raises(LLMError):
        await LLMRouter(FakeProvider()).web_search("cloud", "q")


# --- small items -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("The founder has already committed to SDRs.", "You have already committed to SDRs."),
        ("the founder's plan works", "your plan works"),
        ("The founder's plan works", "Your plan works"),
        ("Since the founder is hiring, wait.", "Since you are hiring, wait."),
        ("The founder decided to hire.", "You decided to hire."),
        ("The founder wants to hire.", "You want to hire."),
        ("It is up to the founder.", "It is up to you."),
        ("A co-founder has left.", "A co-founder has left."),
        ("Your founder story", "Your founder story"),
    ],
)
def test_the_advisor_speaks_to_the_founder(said: str, expected: str) -> None:
    assert in_one_voice(said) == expected


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("It costs 11,423.62 USD a month.", "It costs $11,423.62 a month."),
        ("It costs $172,280.47 USD monthly.", "It costs $172,280.47 monthly."),
        ("It costs $11,423.62 a month.", "It costs $11,423.62 a month."),
        ("Cash 5.00 GBP", "Cash £5.00"),
    ],
)
def test_money_is_written_one_way(said: str, expected: str) -> None:
    assert one_money_format(said) == expected


def test_format_money() -> None:
    assert format_money(11423.62) == "$11,423.62"
    assert format_money(1000, "INR") == "₹1,000.00"
    assert format_money(1000, "AED") == "1,000.00 AED"


# --- names inside free text (M3c) -------------------------------------------------------------------------------------
def _names() -> NameIndex:
    index = NameIndex(
        [
            lambda: [
                ("customer", "Ironcrest Media"),
                ("customer", "Copperforge Logistics"),
                ("customer", "Global Foods"),
                ("customer", "Global Parts"),
            ],
            lambda: [("person", "Priya Nair"), ("company", "Northwind Analytics"), ("company", "NWA")],
        ]
    )
    index.refresh()
    return index


def test_names_inside_a_sentence_become_stable_pseudonyms() -> None:
    names, report = _names(), FilterReport()
    text = "Ironcrest Media churned; ironcrest media's owner told Priya. Ask Priya Nair about Copperforge."
    cleaned = filter_text(text, report, names)
    for name in ("Ironcrest", "ironcrest", "Priya", "Nair", "Copperforge"):
        assert name not in cleaned, cleaned
    assert cleaned.count("Customer_001") == 2
    assert "Person_001" in cleaned and report.names_replaced >= 4
    assert names.restore("Customer_001 is at risk, says Person_001.") == "Ironcrest Media is at risk, says Priya Nair."


def test_ordinary_words_and_shared_short_forms_are_left_alone() -> None:
    names = _names()
    text = "Global demand is up, and our analytics grew. Copperplate is a font."
    assert filter_text(text, None, names) == text


def test_a_title_marks_a_person_who_is_in_no_source() -> None:
    names = _names()
    cleaned = filter_text("Dr Rao Menon advised against it.", None, names)
    assert "Rao" not in cleaned
    assert names.restore(cleaned) == "Dr Rao Menon advised against it."


def test_names_are_scrubbed_in_tool_results_and_tool_call_arguments() -> None:
    names = _names()
    call = ToolCall(name="search_vault", arguments={"query": "Ironcrest Media renewal"})
    messages = [
        Message.assistant("", [call]),
        Message.tool(call, json.dumps({"results": [{"snippet": "Northwind Analytics lost Ironcrest Media."}]})),
    ]
    filtered, report = filter_messages(messages, names)
    assert "Ironcrest" not in str(filtered[0].tool_calls[0].arguments)
    assert "Ironcrest" not in filtered[1].content and "Northwind" not in filtered[1].content
    assert "Ironcrest" in messages[1].content  # the originals stay for the local fallback
    assert report.names_replaced == 3


async def test_the_router_sends_pseudonyms_and_gives_the_founder_real_names() -> None:
    seen: list[list[Message]] = []

    def reply(messages: list[Message], tools: Any, schema: Any) -> str:
        seen.append(messages)
        return "Customer_001 is the risk."

    cloud = FakeProvider(name="cloudy", model="cloud-model", default=reply, is_cloud=True)
    router = LLMRouter(FakeProvider(name="local", model="local-model"), cloud, cloud_allowed=True)
    router.names = _names()
    completion = await router.complete("cloud", [Message.user("Is Ironcrest Media a risk?")], agent_type="market_scout")
    assert "Ironcrest" not in seen[0][0].content
    assert completion.text == "Ironcrest Media is the risk."


async def test_the_call_stays_local_when_the_names_cannot_be_read() -> None:
    def broken() -> list[tuple[str, str]]:
        raise OSError("database locked")

    cloud = FakeProvider(name="cloudy", model="cloud-model", default=lambda *_: "never", is_cloud=True)
    local = FakeProvider(name="local", model="local-model", default=lambda *_: "local answer")
    router = LLMRouter(local, cloud, cloud_allowed=True)
    router.names = NameIndex([broken])
    completion = await router.complete("cloud", [Message.user("Hello")], agent_type="market_scout")
    assert completion.text == "local answer"
    assert completion.fallback_from == "cloudy"
    assert not cloud.calls


def test_a_pseudonym_split_across_stream_chunks_is_restored() -> None:
    restorer = StreamRestorer(_names())
    out = "".join(restorer.feed(d) for d in ("Ask Cust", "omer_0", "01 now.", " And Co")) + restorer.flush()
    assert out == "Ask Ironcrest Media now. And Co"


def test_names_come_from_the_customers_table_and_vault_fields(tmp_path: Path) -> None:
    db = SimpleNamespace(tables=lambda: set(), connect=None)
    assert list(customer_names(SimpleNamespace(db=db))) == []
    vault = VaultManager(tmp_path)
    vault.ensure_layout()
    vault.write_note(
        "notes/a.md", body="body", frontmatter={"title": "A", "people": ["Priya Nair"], "customer": "Ironcrest Media"}
    )
    vault.write_note("notes/b.md", body="body", frontmatter={"title": "Rao Menon", "tags": ["person"]})
    found = set(vault_names(SimpleNamespace(vault=vault)))
    assert {("person", "Priya Nair"), ("company", "Ironcrest Media"), ("person", "Rao Menon")} <= found


def test_a_name_is_hidden_when_hyphenated_lower_case_or_a_file_slug() -> None:
    names = _names()
    for text in (
        "An Ironcrest-led deal.",
        "ironcrest churn is up.",
        "IRONCREST renewed.",
        "See [customers/ironcrest-media.md].",
        "See customers/ironcrest_media.md.",
        "Ironcrest\nMedia called.",
    ):
        cleaned = filter_text(text, FilterReport(), names)
        assert "ironcrest" not in cleaned.lower(), cleaned
        assert "Customer_001" in cleaned, cleaned


def test_a_name_that_is_also_a_word_is_only_hidden_as_written() -> None:
    index = NameIndex([lambda: [("person", "Will"), ("customer", "Summit")]])
    index.refresh()
    assert filter_text("I think it will reach the summit.", FilterReport(), index) == (
        "I think it will reach the summit."
    )
    hidden = filter_text("Will met Summit.", FilterReport(), index)
    assert "Will" not in hidden and "Summit" not in hidden


def test_text_that_only_regex_thinks_is_the_name_is_hidden_and_never_raises() -> None:
    index = NameIndex([lambda: [("customer", "Kim Ltd")]])
    index.refresh()
    cleaned = filter_text("K\u0131m Ltd signed.", FilterReport(), index)
    assert "K\u0131m" not in cleaned
    assert index.restore(cleaned) == "K\u0131m Ltd signed."


def test_a_thousandth_customer_gets_its_name_back() -> None:
    index = NameIndex([lambda: [("customer", f"Acme Number{i} Ltd") for i in range(1000)]])
    index.refresh()
    cleaned = filter_text("Acme Number999 Ltd left.", FilterReport(), index)
    assert "Customer_1000" in cleaned and index.restore(cleaned) == "Acme Number999 Ltd left."
    restorer = StreamRestorer(index)
    assert restorer.feed("Customer_100") + restorer.feed("0 left.") + restorer.flush() == "Acme Number999 Ltd left."
