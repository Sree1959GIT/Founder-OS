"""REST endpoints: /api/data/*, /api/metrics/*, /api/scenario*."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.data import safe_file_name
from app.config import Settings
from app.main import create_app
from tests import golden as g


def make(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", vault_path=tmp_path / "vault")
    with make(settings) as c:  # auto_load_sample_data defaults to True
        yield c


@pytest.fixture
def empty_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        vault_path=tmp_path / "vault",
        auto_load_sample_data=False,
        max_upload_mb=1,
    )
    with make(settings) as c:
        yield c


def test_startup_loads_sample_data(client: TestClient) -> None:
    body = client.get("/api/data/tables").json()
    assert {t["table"] for t in body["loaded"]} == {
        "pnl", "bank_balance", "customers", "subscriptions", "pipeline", "marketing_spend", "headcount",
    }  # fmt: skip
    assert {t["table"] for t in body["canonical"]} >= {"pnl", "bank_balance"}
    assert client.get("/api/data/mappings").json()["pnl.csv"]["table"] == "pnl"


def test_startup_survives_missing_sample_folder(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "d", vault_path=tmp_path / "v", sample_data_dir=tmp_path / "missing"
    )
    with make(settings) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/metrics/mrr").status_code == 409


def test_no_data_is_a_clear_409(empty_client: TestClient) -> None:
    response = empty_client.get("/api/metrics/runway")
    assert response.status_code == 409
    assert "Load the sample data" in response.json()["detail"]


def test_metric_endpoint(client: TestClient) -> None:
    body = client.get("/api/metrics/runway").json()
    assert body["value"] == 10.65
    assert body["detail"]["zero_cash_month"] == "2027-09"
    assert body["lineage"]["source_rows"][0]["rows"] == "23-25"
    body = client.get("/api/metrics/net_burn", params={"month": "2025-12", "window": 1}).json()
    assert body["value"] == float(g.net_burn("2025-12", 1))


def test_metric_errors(client: TestClient) -> None:
    assert client.get("/api/metrics/nope").status_code == 422
    assert client.get("/api/metrics/mrr", params={"month": "2030-01"}).status_code == 422
    assert client.get("/api/metrics/mrr", params={"month": "26-1"}).status_code == 422
    assert client.get("/api/metrics/mrr", params={"window": 0}).status_code == 422


def test_metrics_index_and_summary(client: TestClient) -> None:
    index = client.get("/api/metrics").json()
    assert len(index["metrics"]) == 18 and index["months"][-1] == "2026-10"
    body = client.get("/api/metrics/summary").json()
    assert body["unavailable"] == {}
    summary = {m["metric"]: m["value"] for m in body["metrics"]}
    assert summary["mrr"] == 255344.27
    assert summary["net_burn"] == 172280.47
    assert summary["gross_margin"] == 0.7213


def test_cash_projection_endpoint(client: TestClient) -> None:
    body = client.get("/api/metrics/cash-projection").json()
    assert len(body["points"]) == 12
    assert body["base_zero_cash_month"] == "2027-10"
    assert all(p["delta"] == 0 for p in body["points"])
    assert len(client.get("/api/metrics/cash-projection", params={"horizon": 24}).json()["points"]) == 24


def test_cash_projection_growth_modes_and_runway_names(client: TestClient) -> None:
    """Founder feedback: show the growth assumption, allow "no new customers", reconcile with the runway metric."""
    trend = client.get("/api/metrics/cash-projection").json()
    assert trend["growth_mode"] == "trend" and trend["base_runway_months"] == 11.23
    rec = trend["reconciliation"]
    assert (rec["runway_actual_burn_months"], rec["run_rate_runway_months"], rec["growth_gap_months"]) == (
        10.65,
        10.71,
        0.52,
    )
    assert rec["within_tolerance"] is True and rec["explanation"]
    new_customers = {a["name"]: a for a in trend["assumptions"]}["new_customers"]
    assert new_customers["value"] == 5.33 and new_customers["window"] == "2026-08..2026-10"
    assert new_customers["lineage"]["source_rows"][0]["table"] == "customers"
    none = client.get("/api/metrics/cash-projection", params={"growth_mode": "none"}).json()
    assert none["base_runway_months"] == 9.69 and none["base_zero_cash_month"] == "2027-08"
    flat = client.get("/api/metrics/cash-projection", params={"growth_mode": "flat"}).json()
    assert flat["base_runway_months"] == 10.71
    assert client.get("/api/metrics/cash-projection", params={"growth_mode": "rocket"}).status_code == 422
    assert client.post("/api/scenario", json={"growth_mode": "none"}).json()["scenario_runway_months"] == 9.69
    montecarlo = client.post("/api/scenario/montecarlo", json={"adjustments": {"growth_mode": "flat"}}).json()
    assert montecarlo["growth_mode"] == "flat" and len(montecarlo["assumptions"]) == 12
    runway = client.get("/api/metrics/runway").json()
    assert runway["label"] == "Runway (actual burn)" and runway["value"] == 10.65
    assert trend["labels"]["base_runway_months"] == "Projected runway (with growth assumptions)"


def test_kill_criteria_endpoint(client: TestClient) -> None:
    body = {"criteria": [{"name": "Runway", "metric": "runway", "operator": "<", "threshold": 6}]}
    (check,) = client.post("/api/metrics/kill-criteria", json=body).json()
    assert check["triggered"] is False and check["value"] == 10.65


def test_scenario_endpoint(client: TestClient) -> None:
    client.post("/api/scenario", json={})  # warm the driver cache
    started = time.perf_counter()
    response = client.post("/api/scenario", json={"price_change_pct": 10, "churn_change_pts": 2})
    assert time.perf_counter() - started < 0.2
    body = response.json()
    assert response.status_code == 200
    assert len(body["points"]) == 12 and body["points"][0]["month"] == "2026-11"
    assert body["scenario_runway_months"] < body["base_runway_months"]
    assert body["lineage"]["metric"] == "scenario"
    assert client.post("/api/scenario", json={"price_change_pct": -99}).status_code == 422
    assert client.post("/api/scenario", json={"horizon": 99}).status_code == 422


def test_sensitivity_and_montecarlo_endpoints(client: TestClient) -> None:
    grid = client.post("/api/scenario/sensitivity", json={}).json()
    assert len(grid["table"]) == 5 and len(grid["table"][0]) == 5
    assert grid["table"][2][1] == grid["base_value"]  # price 0, churn 0
    bad = client.post("/api/scenario/sensitivity", json={"row_variable": "x"})
    assert bad.status_code == 422
    hires = {"row_variable": "new_hires", "row_values": [0.5, 1]}  # review finding: was HTTP 500
    assert client.post("/api/scenario/sensitivity", json=hires).status_code == 422
    first_month = client.get("/api/metrics/summary", params={"month": "2024-11"}).json()
    assert "net_burn" in first_month["unavailable"] and first_month["metrics"]
    mc = client.post("/api/scenario/montecarlo", json={"runs": 500, "seed": 1}).json()
    assert mc["runs"] == 500 and len(mc["points"]) == 12
    assert client.post("/api/scenario/montecarlo", json={"runs": 500, "seed": 1}).json()["points"] == mc["points"]


def test_guarded_query_endpoint(client: TestClient) -> None:
    ok = client.post("/api/data/query", json={"sql": "SELECT count(*) AS n FROM customers"}).json()
    assert ok["rows"] == [[198]] and ok["lineage"]["source_files"] == ["customers.csv"]
    bad = client.post("/api/data/query", json={"sql": "DROP TABLE customers"})
    assert bad.status_code == 400 and "Only SELECT" in bad.json()["detail"]


def test_upload_csv_with_synonyms(empty_client: TestClient) -> None:
    csv_bytes = b"Period,Line Item,Type,Value\n2026-10,Subscriptions,Revenue,1000\n2026-10,Hosting,COGS,250\n"
    response = empty_client.post("/api/data/upload", files={"file": ("..\\..\\My P&L.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200, response.text
    (report,) = response.json()["tables"]
    assert report["table"] == "pnl" and report["source_file"] == "My P_L.csv"
    assert empty_client.get("/api/metrics/gross_margin").status_code == 409  # bank data still missing
    query = empty_client.post("/api/data/query", json={"sql": "SELECT sum(amount) FROM pnl"}).json()
    assert query["rows"] == [["1250.00"]]


def test_upload_rejections(empty_client: TestClient, tmp_path: Path) -> None:
    r = empty_client.post("/api/data/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    big = b"month,account,category,amount\n" + b"2026-10,A,Revenue,1\n" * 60_000  # > 1 MB
    r = empty_client.post("/api/data/upload", files={"file": ("pnl.csv", big, "text/csv")})
    assert r.status_code == 413
    bad = b"month,account,category,amount\n2026-10,A,Revenue,abc\n"
    r = empty_client.post("/api/data/upload", files={"file": ("pnl.csv", bad, "text/csv")})
    assert r.status_code == 422
    assert r.json()["errors"][0].startswith("row 2")
    assert list((tmp_path / "data" / "default" / "uploads").iterdir()) == []  # rejected uploads are not kept


def test_upload_table_override(empty_client: TestClient) -> None:
    data = b"month,customer_id,amount\n2026-10,C1,10\n"
    r = empty_client.post("/api/data/upload", files={"file": ("x.csv", data)}, data={"table": "subscriptions"})
    assert r.status_code == 200 and r.json()["tables"][0]["table"] == "subscriptions"


def test_load_sample_endpoint(empty_client: TestClient) -> None:
    body = empty_client.post("/api/data/load-sample").json()
    assert len(body["tables"]) == 7
    assert empty_client.get("/api/metrics/mrr").json()["value"] == 255344.27


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pnl.csv", "pnl.csv"),
        ("C:\\Users\\x\\bank.XLSX", "bank.xlsx"),
        ("../../etc/passwd.csv", "passwd.csv"),
        ("a<b>:c|?.csv", "a_b__c__.csv"),
        ("....csv", "upload.csv"),
    ],
)
def test_safe_file_name(raw: str, expected: str) -> None:
    assert safe_file_name(raw) == expected
