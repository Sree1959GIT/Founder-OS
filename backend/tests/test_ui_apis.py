"""APIs added for the M4 UI: settings, priorities, the run stream, the frame on a proposal, run all locally."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.settings import FILE_NAME
from app.config import Settings
from app.llm.fake import FakeProvider
from app.main import create_app


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings.model_copy(update={"auto_load_sample_data": True}))
    with TestClient(app) as c:
        yield c


def _frames(text: str) -> list[tuple[str, dict[str, Any]]]:
    frames = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":"))
        frames.append((fields["event"], json.loads(fields["data"])))
    return frames


# --- settings -------------------------------------------------------------------------------------------------------
def test_settings_show_choices_and_never_a_key(settings: Settings) -> None:
    secret = "sk-this-must-never-appear"
    app = create_app(settings.model_copy(update={"anthropic_api_key": SecretStr(secret)}))
    with TestClient(app) as client:
        body = client.get("/api/settings")
        assert secret not in body.text
        view = body.json()
    assert view["cloud_allowed"] is False
    anthropic = next(p for p in view["providers"] if p["name"] == "anthropic")
    assert anthropic == {"name": "anthropic", "configured": True}
    assert "privacy filter" in view["privacy_note"]
    assert any(a["type"] == "market_scout" for a in view["agents"])


def test_settings_change_routing_at_once_and_survive_a_restart(settings: Settings) -> None:
    base = settings.model_copy(update={"gemini_api_key": SecretStr("k"), "auto_load_sample_data": False})
    app = create_app(base)
    with TestClient(app) as client:
        update = {
            "cloud_allowed": True,
            "agent_models": {"market_scout": "gemini:gemini-test"},
            "cloud_monthly_cap_usd": 5.0,
            "team_approval": "always",
            "max_local_agents": 3,
        }
        view = client.put("/api/settings", json=update).json()
        assert view["cloud_allowed"] is True and view["cloud_monthly_cap_usd"] == 5.0
        orchestrator = app.state.orchestrator
        assert orchestrator.approval_policy == "always" and orchestrator.max_local == 3
        assert orchestrator.router.cloud_allowed is True
        assert orchestrator.router.routes["market_scout"].model == "gemini-test"
        assert orchestrator.router.ledger.monthly_cap_usd == 5.0
        health = client.get("/api/health").json()
        cloud = next(d for d in health["dependencies"] if d["name"] == "cloud")
        assert cloud["info"]["cloud_allowed"] is True
        assert '"k"' not in (settings.workspace_data_dir() / FILE_NAME).read_text(encoding="utf-8")
    again = create_app(base)
    with TestClient(again) as client:
        assert again.state.orchestrator.router.cloud_allowed is True
        assert client.put("/api/settings", json={"cloud_allowed": False}).json()["cloud_allowed"] is False
        assert again.state.orchestrator.router.cloud_allowed is False
        # What was not sent stays as chosen.
        assert client.get("/api/settings").json()["team_approval"] == "always"


def test_a_bad_or_damaged_settings_file_keeps_the_safe_defaults(settings: Settings) -> None:
    path = settings.workspace_data_dir() / FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    app = create_app(settings.model_copy(update={"auto_load_sample_data": False}))
    with TestClient(app) as client:
        assert client.get("/api/settings").json()["cloud_allowed"] is False
        assert client.put("/api/settings", json={"cloud_monthly_cap_usd": -1}).status_code == 422
        assert client.put("/api/settings", json={"team_approval": "sometimes"}).status_code == 422


# --- priorities -----------------------------------------------------------------------------------------------------
def test_priorities_start_empty_with_the_design_weights(client: TestClient) -> None:
    view = client.get("/api/priorities").json()
    assert view["options"] == [] and view["scoring"] is None
    assert [c["weight"] for c in view["criteria"]] == [0.35, 0.25, 0.25, 0.15]


def test_priorities_are_scored_in_code_and_kept_in_the_vault(client: TestClient) -> None:
    criteria = client.get("/api/priorities").json()["criteria"]
    names = [c["name"] for c in criteria]
    options = [
        {"name": "Dubai office", "scores": dict(zip(names, [5, 5, 1, 1], strict=True)), "cost": 100.0},
        {"name": "Onboarding fix", "scores": dict(zip(names, [2, 2, 5, 5], strict=True)), "cost": 10.0},
    ]
    view = client.put("/api/priorities", json={"criteria": criteria, "options": options}).json()
    by_name = {o["name"]: o for o in view["scoring"]["options"]}
    assert by_name["Dubai office"]["value"] > by_name["Onboarding fix"]["value"]
    assert by_name["Dubai office"]["feasibility"] < by_name["Onboarding fix"]["feasibility"]
    note = client.get(f"/api/vault/notes/{view['path']}").json()
    assert "Dubai office" in note["content"] and "Quadrant" in note["content"]
    assert [o["name"] for o in client.get("/api/priorities").json()["options"]] == ["Dubai office", "Onboarding fix"]


def test_priorities_refuse_a_score_off_the_scale(client: TestClient) -> None:
    criteria = client.get("/api/priorities").json()["criteria"]
    scores = {c["name"]: 9 for c in criteria}
    answer = client.put("/api/priorities", json={"criteria": criteria, "options": [{"name": "x", "scores": scores}]})
    assert answer.status_code == 422


# --- the lane's run stream ------------------------------------------------------------------------------------------
def test_a_lane_run_streams_its_text_then_the_result(client: TestClient) -> None:
    client.app.state.orchestrator.router.local = FakeProvider(["What does that burn rest on?"])  # type: ignore[attr-defined]
    run_id = client.post("/api/conversation/turn", json={"text": "What's our runway?"}).json()["run_id"]
    with client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        frames = _frames(response.read().decode())
    kinds = [kind for kind, _ in frames]
    assert "delta" in kinds and kinds[-1] == "done"
    assert frames[-1][1]["answer"].startswith("Runway (actual burn) is 10.65 months")
    assert client.get(f"/api/runs/{run_id}/stream").status_code == 409  # delivered once
    assert client.get("/api/runs/run_nope/stream").status_code == 404


def test_run_detail_has_the_message_and_frame(client: TestClient) -> None:
    client.app.state.orchestrator.router.local = FakeProvider(default=lambda *_: "Fine?")  # type: ignore[attr-defined]
    body = client.post("/api/chat", json={"message": "Should we open a Dubai office?", "stream": False}).json()
    run = client.get(f"/api/runs/{body['run_id']}").json()
    assert run["message"] == "Should we open a Dubai office?"
    assert run["decision_frame"]["type"] == "new_office"
    proposed = next(e for e in run["events"] if e["type"] == "team.proposed")
    assert proposed["data"]["decision_frame"]["default_option"]
    assert proposed["data"]["decision_frame"]["cost_model"]["cases"]


# --- run all locally ------------------------------------------------------------------------------------------------
def test_run_all_locally_keeps_cloud_agents_off_the_cloud(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"auto_load_sample_data": True, "team_approval": "always"}))
    with TestClient(app) as client:
        orchestrator = app.state.orchestrator
        local = FakeProvider(default=lambda *_: "A short local answer.", name="local-fake")
        cloud = FakeProvider(default=lambda *_: "From the cloud.", name="cloud-fake", is_cloud=True)
        orchestrator.router.local, orchestrator.router.cloud, orchestrator.router.cloud_allowed = local, cloud, True
        orchestrator.router.ledger = None

        async def go() -> Any:
            run = orchestrator.start("Should we open a Dubai office? What is the market like?")
            for _ in range(500):
                if run.plan is not None:
                    break
                await asyncio.sleep(0.01)
            assert any(i.is_cloud for i in run.plan.team)
            from app.agents.graph import TeamEdit

            assert orchestrator.approve(run.run_id, True, TeamEdit(local_only=True))
            return await run.task

        result = client.portal.call(go)  # type: ignore[union-attr]
        assert result.approved
        assert cloud.calls == []
        assert all(not i.is_cloud and i.local_only for i in result.team)
        assert local.calls


# --- column mappings --------------------------------------------------------------------------------------------------
def test_a_saved_mapping_lets_a_messy_file_load(client: TestClient) -> None:
    messy = "Kol A,Kol B,Kol C,Kol D|2026-10,Rent,opex,1000|".replace("|", chr(10)).encode()

    def upload() -> Any:
        files = {"file": ("messy.csv", messy, "text/csv")}
        return client.post("/api/data/upload", files=files, data={"table": "pnl"})

    assert upload().status_code >= 400
    columns = {"Kol A": "month", "Kol B": "account", "Kol C": "category", "Kol D": "amount"}
    saved = client.put("/api/data/mappings", json={"key": "messy.csv", "table": "pnl", "columns": columns})
    assert saved.status_code == 200
    assert saved.json()["messy.csv"]["columns"] == columns
    assert upload().status_code == 200


def test_a_mapping_must_name_real_columns_once_each(client: TestClient) -> None:
    def put(table: str, columns: dict[str, str]) -> int:
        return client.put("/api/data/mappings", json={"key": "x.csv", "table": table, "columns": columns}).status_code

    assert put("nonsense", {"a": "month"}) == 422
    assert put("pnl", {"a": "nonsense"}) == 422
    assert put("pnl", {"a": "month", "b": "month"}) == 422


def test_a_mapping_is_found_under_the_name_ingest_uses(client: TestClient) -> None:
    messy = "Kol A, Kol B,Kol C,Kol D|2026-10,Rent,opex,1000|".replace("|", chr(10)).encode()
    columns = {"Kol A": "month", " Kol B": "account", "Kol C": "category", "Kol D": "amount"}
    name = "pnl (1).csv"
    assert client.put("/api/data/mappings", json={"key": name, "table": "pnl", "columns": columns}).status_code == 200
    files = {"file": (name, messy, "text/csv")}
    assert client.post("/api/data/upload", files=files, data={"table": "pnl"}).status_code == 200


# --- what the review found -----------------------------------------------------------------------------------------
def test_cloud_off_in_settings_also_stops_the_cloud_decision_model(settings: Settings) -> None:
    base = settings.model_copy(
        update={"decision_provider": "jev", "jev_api_key": SecretStr("k"), "cloud_allowed": True}
    )
    with TestClient(create_app(base)) as client:
        orchestrator = client.app.state.orchestrator  # type: ignore[attr-defined]
        assert orchestrator.decisions.provider.name == "jev"
        assert client.put("/api/settings", json={"cloud_allowed": False}).status_code == 200
        assert orchestrator.decisions.provider.name != "jev"


def test_the_matrix_uses_the_same_four_words_on_the_board_and_in_the_note(client: TestClient) -> None:
    criteria = client.get("/api/priorities").json()["criteria"]
    high = {c["name"]: 5 for c in criteria}
    options = [{"name": "Top right", "scores": high, "cost": None}]
    view = client.put("/api/priorities", json={"criteria": criteria, "options": options}).json()
    assert view["scoring"]["options"][0]["quadrant"] == "Do now"
    note = client.get("/api/vault/notes/notes/priorities.md").json()
    assert "Do now" in note["content"]
    assert "Quick win" not in note["content"]
