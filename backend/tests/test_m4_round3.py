"""M4 re-test RX1 to RX12, round 3 (2026-11-08): 58, 51, 54, 52, 56."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents.dedupe import near_duplicate, without_repeats
from app.agents.horizon import Projection, asked_period, horizon_lead
from app.agents.runtime import rule_metric, single_metric
from app.config import Settings
from app.llm.base import ToolCall
from app.llm.fake import FakeProvider
from app.main import create_app

# ---- 58: every metric name and common synonym maps to its own routine
METRIC_QUESTIONS = [
    ("What is our gross revenue churn?", "revenue_churn"),
    ("What's our revenue churn?", "revenue_churn"),
    ("What is our MRR churn?", "revenue_churn"),
    ("What is our net revenue churn?", "nrr"),
    ("What is our net revenue retention?", "nrr"),
    ("What is our NRR?", "nrr"),
    ("What is our NDR?", "nrr"),
    ("What is our logo churn?", "logo_churn"),
    ("What is our customer churn?", "logo_churn"),
    ("What is our churn rate?", "logo_churn"),
    ("What's our churn?", "logo_churn"),
    ("What is our gross burn?", "gross_burn"),
    ("What is our gross burn rate?", "gross_burn"),
    ("What is our net burn?", "net_burn"),
    ("What is our burn rate?", "net_burn"),
    ("What's our burn?", "net_burn"),
    ("What is our gross margin?", "gross_margin"),
    ("What is our margin?", "gross_margin"),
    ("What is our MRR?", "mrr"),
    ("What is our monthly recurring revenue?", "mrr"),
    ("What is our ARR?", "arr"),
    ("What is our annual recurring revenue?", "arr"),
    ("What is our CAC?", "cac"),
    ("What is our customer acquisition cost?", "cac"),
    ("What is our LTV/CAC?", "ltv_cac"),
    ("What is our LTV:CAC?", "ltv_cac"),
    ("What is our LTV to CAC?", "ltv_cac"),
    ("What is our LTV?", "ltv"),
    ("What is our CAC payback?", "cac_payback"),
    ("What is our runway?", "runway"),
    ("What is our ARPA?", "arpa"),
]


@pytest.mark.parametrize(("question", "metric"), METRIC_QUESTIONS)
def test_every_metric_question_routes_to_its_own_metric(question: str, metric: str) -> None:
    assert single_metric(question) == metric
    assert rule_metric(question) == metric


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings.model_copy(update={"auto_load_sample_data": True}))) as c:
        yield c


def _script(client: TestClient, replies: list[Any]) -> None:
    client.app.state.orchestrator.router.local = FakeProvider(list(replies))  # type: ignore[attr-defined]


def _ask(client: TestClient, message: str) -> dict[str, Any]:
    return client.post("/api/chat", json={"message": message, "stream": False}).json()


def test_gross_revenue_churn_is_answered_with_gross_revenue_churn_and_its_period(client: TestClient) -> None:
    _script(client, ["What drives it?"])
    body = _ask(client, "What is our gross revenue churn?")
    assert [m["metric"] for m in body["metrics"]] == ["revenue_churn"]
    assert body["answer"].startswith("Gross revenue churn (monthly) is ")
    assert re.search(r" for [A-Z][a-z]+ to [A-Z][a-z]+ \d{4}", body["answer"])  # 45: "for August to October 2026"
    assert "burn" not in body["answer"].lower()
    assert body["verification"]["state"] == "verified"


def test_net_revenue_churn_is_shown_as_retention_and_says_so(client: TestClient) -> None:
    _script(client, ["What drives it?"])
    body = _ask(client, "What is our net revenue churn?")
    assert body["metrics"][0]["metric"] == "nrr"
    assert body["answer"].startswith("Net revenue churn is shown as its counterpart, net revenue retention")
    assert body["verification"]["state"] == "assumptions"


def test_an_answer_that_gives_another_metric_is_never_verified(client: TestClient) -> None:
    """Seen live: "Your gross burn is $428,612.47 as of 2026-10, but that's not the same as gross revenue churn"."""
    _script(
        client,
        [
            [ToolCall(name="get_metric", arguments={"name": "gross_burn"})],
            "Gross burn (monthly) is $428,612.47.",
            "Your gross burn is $428,612.47, but that's not the same as gross revenue churn.",
        ],
    )
    body = _ask(client, "Explain our gross revenue churn trend over the last year")
    assert "revenue_churn" not in [m["metric"] for m in body["metrics"]]
    assert body["verification"]["state"] == "not_verified"
    assert any("Gross revenue churn" in r for r in body["verification"]["reasons"])


# ---- 51: nothing ran, nothing to vouch for
def test_a_greeting_has_no_verified_badge(client: TestClient) -> None:
    _script(client, ["Hello! What would you like to look at?"])
    body = _ask(client, "Hello")
    assert body["verification"]["state"] == "not_run"


# ---- 54: no sentence twice, in the founder's exact words
def test_the_drafted_question_twice_is_asked_once() -> None:
    text = (
        "You already have a proposed memo on this [decisions/2026-10-dubai.md]: what has changed since you drafted it? "
        "What has changed since you drafted the proposal?"
    )
    assert without_repeats(text) == (
        "You already have a proposed memo on this [decisions/2026-10-dubai.md]: what has changed since you drafted it? "
    )


def test_the_goal_said_twice_is_said_once() -> None:
    goal = "Bring logo churn under 1.5 % a month"
    text = (
        "Proposed: New customers only, $0.00 a month, runway +0.18 months. "
        f'The full model moves you away from your goal "{goal}". '
        "This also moves you away from your goal to bring logo churn under 1.5 % a month. "
        "What matters more to you this year?"
    )
    out = without_repeats(text, [goal])
    assert out.count("logo churn") == 1 and out.rstrip().endswith("What matters more to you this year?")


def test_different_figures_are_never_duplicates() -> None:
    assert not near_duplicate("Runway is 10.65 months today.", "Runway is 12.10 months today.")
    assert not near_duplicate("What is the main risk?", "What will it cost?")


# ---- 52: a projection that runs past the month cash runs out says so
def test_a_projection_past_zero_cash_says_you_must_stay_funded() -> None:
    projection = Projection(
        as_of="2026-10",
        first_month="2026-11",
        last_month="2028-10",
        months=24,
        mrr=120000.0,
        cash=-250000.0,
        adjusted=False,
        zero_cash_month="2027-10",
    )
    asked = asked_period("What will our MRR be in 2031?", "2026-10")
    assert asked is not None
    lead = horizon_lead("What will our MRR be in 2031?", asked, projection)
    assert "that you stay funded after cash runs out in Oct 2027" in lead
    clean = projection.model_copy(update={"zero_cash_month": None})
    assert "stay funded" not in horizon_lead("What will our MRR be in 2031?", asked, clean)
