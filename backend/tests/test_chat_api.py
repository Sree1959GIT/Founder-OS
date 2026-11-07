from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.chat import sse
from app.config import Settings
from app.llm.base import LLMUnavailable, ToolCall
from app.llm.fake import FakeProvider
from app.main import create_app

RUNWAY_SCRIPT: list[Any] = [
    [ToolCall(name="get_metric", arguments={"name": "runway"})],
    "Runway (actual burn) is 10.65 months as of 2026-10.",
    "You have 10.65 months of runway at today's burn. What would you cut first if growth stalls?",
]


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings.model_copy(update={"auto_load_sample_data": True}))
    with TestClient(app) as c:
        yield c


def _down(_messages: Any, _tools: Any, _schema: Any) -> Any:
    raise LLMUnavailable("down")


def script(client: TestClient, replies: list[Any]) -> FakeProvider:
    provider = FakeProvider(list(replies))
    client.app.state.orchestrator.router.local = provider  # type: ignore[attr-defined]
    return provider


def parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    frames = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":"))
        frames.append((fields["event"], json.loads(fields["data"])))
    return frames


def test_chat_json_answers_runway_with_lineage(client: TestClient) -> None:
    script(client, RUNWAY_SCRIPT)
    response = client.post("/api/chat", json={"message": "Walk me through our runway.", "stream": False})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("You have 10.65 months") and body["verified"] is True
    metric = body["metrics"][0]
    assert metric["metric"] == "runway" and metric["value"] == 10.65 and metric["unit"] == "months"
    assert metric["lineage"]["sql"] and metric["lineage"]["source_files"] and metric["lineage"]["formula"]
    assert body["intent"] == "finance" and body["team"][0]["type"] == "financial_analyst"
    assert body["agents"][0]["verified"] is True and body["elapsed_ms"] > 0 and "advise" in body["timings_ms"]
    run = client.get(f"/api/runs/{body['run_id']}").json()
    assert run["status"] == "finished" and run["result"]["answer"] == body["answer"]
    assert run["events"][0]["type"] == "run.started"


def test_chat_streams_events_deltas_and_done(client: TestClient) -> None:
    script(client, RUNWAY_SCRIPT)
    with client.stream("POST", "/api/chat", json={"message": "What's our runway?"}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        frames = parse_sse(response.read().decode("utf-8"))
    kinds = [k for k, _ in frames]
    assert kinds[0] == "run" and kinds[-1] == "done" and kinds.count("run.finished") == 1
    assert {"team.proposed", "agent.spawned", "agent.tool_call", "agent.artifact", "agent.done", "delta"} <= set(kinds)
    assert kinds.index("agent.done") < kinds.index("delta")
    text = "".join(d["text"] for k, d in frames if k == "delta")
    done = frames[-1][1]
    assert text == done["answer"] and done["metrics"][0]["value"] == 10.65


def test_chat_without_ollama_still_answers_from_rules(client: TestClient) -> None:
    script(client, [])
    client.app.state.orchestrator.router.local.default = lambda m, t, s: LLMUnavailable("Ollama not reachable")  # type: ignore[attr-defined]
    body = client.post("/api/chat", json={"message": "What's our runway?", "stream": False}).json()
    assert "10.65 months" in body["answer"] and body["advisor_provider"] == "rules"
    assert body["metrics"][0]["value"] == 10.65 and body["agents"][0]["provider"] == "rules"


def test_chitchat_needs_no_team(client: TestClient) -> None:
    script(client, ["Hello! What decision is on your mind?"])
    body = client.post("/api/chat", json={"message": "hello", "stream": False}).json()
    assert body["team"] == [] and body["answer"].startswith("Hello") and body["intent"] == "chitchat"


def test_agents_endpoint_and_errors(client: TestClient) -> None:
    agents = client.get("/api/agents").json()
    assert agents["approval_policy"] == "cloud_only" and agents["max_local_agents"] == 2
    assert {"advisor", "planner", "financial_analyst", "memo_writer", "market_scout"} <= {
        a["type"] for a in agents["agents"]
    }
    assert all(a["provider"] == "fake" and "this_month" in a for a in agents["agents"])
    assert agents["cloud"]["allowed"] is False and agents["cloud"]["cap_usd"] > 0
    assert client.get("/api/runs/run_nope").status_code == 404
    assert client.post("/api/runs/run_nope/approve", json={"approved": True}).status_code == 409
    assert client.post("/api/runs/run_nope/cancel").status_code == 409
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_sse_frame_format() -> None:
    assert sse("delta", {"text": "hi"}, 7) == 'id: 7\nevent: delta\ndata: {"text": "hi"}\n\n'


def test_a_single_metric_question_is_answered_by_code_with_one_short_llm_call(client: TestClient) -> None:
    provider = script(client, ["What does that burn rest on?"])
    body = client.post("/api/chat", json={"message": "What's our runway?", "stream": False}).json()
    assert body["verified"] is True
    assert body["issues"] == []
    assert body["answer"].startswith("Runway (actual burn) is 10.65 months as of ")
    assert "$1,835,125.06" in body["answer"]
    assert body["answer"].endswith("What does that burn rest on?")
    agent = body["agents"][0]
    assert agent["written_by_code"] is True
    assert [c["tool"] for c in agent["tool_calls"]] == ["get_metric"]
    assert body["metrics"][0]["lineage"]["source_files"]
    assert len(provider.calls) == 1  # the question only: no planning, no tool loop, no findings
    assert provider.calls[0]["tools"] is None
    assert sum(len(m.content) for m in provider.calls[0]["messages"]) < 600


def test_a_metric_question_from_the_model_with_a_figure_is_dropped(client: TestClient) -> None:
    script(client, ["Is the $150 billion market real?"])
    body = client.post("/api/chat", json={"message": "What's our runway?", "stream": False}).json()
    assert body["verified"] is True
    assert "150" not in body["answer"]
    assert body["answer"].endswith(".")


def test_a_metric_answer_needs_no_model(client: TestClient) -> None:
    client.app.state.orchestrator.router.local = FakeProvider(default=_down)  # type: ignore[attr-defined]
    body = client.post("/api/chat", json={"message": "What's our runway?", "stream": False}).json()
    assert body["verified"] is True
    assert body["answer"].startswith("Runway (actual burn) is 10.65 months")
    assert body["advisor_provider"] == "rules"


def test_the_number_streams_before_the_question(client: TestClient) -> None:
    script(client, ["What does that burn rest on?"])
    with client.stream("POST", "/api/chat", json={"message": "What's our runway?"}) as response:
        frames = parse_sse(response.read().decode())
    deltas = [d["text"] for kind, d in frames if kind == "delta"]
    assert deltas[0].startswith("Runway (actual burn) is 10.65 months")
    assert deltas[1] == " What does that burn rest on?"


@pytest.mark.parametrize(
    "question",
    [
        "What's our runway?",
        "What's our MRR?",
        "What is our ARR?",
        "What's our net burn?",
        "What is our gross margin?",
        "What's our CAC?",
        "What's our logo churn?",
        "What is our NRR?",
        "What's our LTV?",
        "What's our LTV:CAC?",
        "What's our payback?",
        "What's our ARPA?",
        "What's our headcount cost?",
        "What's our gross burn?",
    ],
)
def test_every_plain_metric_question_verifies(client: TestClient, question: str) -> None:
    script(client, ["What does that rest on?"])
    body = client.post("/api/chat", json={"message": question, "stream": False}).json()
    assert body["verified"] is True, body["issues"]
    assert body["agents"][0]["written_by_code"] is True, question
