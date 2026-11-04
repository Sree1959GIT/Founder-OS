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
    response = client.post("/api/chat", json={"message": "What's our runway?", "stream": False})
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
    assert {a["type"] for a in agents["agents"]} == {"advisor", "planner", "financial_analyst", "librarian", "verifier"}
    assert all(a["provider"] == "fake" for a in agents["agents"])
    assert client.get("/api/runs/run_nope").status_code == 404
    assert client.post("/api/runs/run_nope/approve", json={"approved": True}).status_code == 409
    assert client.post("/api/runs/run_nope/cancel").status_code == 409
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_sse_frame_format() -> None:
    assert sse("delta", {"text": "hi"}, 7) == 'id: 7\nevent: delta\ndata: {"text": "hi"}\n\n'
