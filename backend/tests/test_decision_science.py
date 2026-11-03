"""Weighted scoring, expected value, decision trees, kill criteria and calibration (Brier)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.engine.calibration import CalibrationError, CalibrationStore, PredictionIn, brier_score
from app.engine.decision_science import (
    ChanceNode,
    DecisionNode,
    EVOption,
    KillCriterion,
    ScoringRequest,
    TerminalNode,
    evaluate_kill_criteria,
    expected_values,
    solve_decision_tree,
    weighted_scoring,
)
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine


def scoring_request() -> ScoringRequest:
    return ScoringRequest.model_validate(
        {
            "criteria": [
                {"name": "Revenue impact", "weight": 3, "axis": "value"},
                {"name": "Strategic fit", "weight": 1, "axis": "value"},
                {"name": "Effort", "weight": 2, "direction": "cost", "axis": "feasibility"},
            ],
            "options": [
                {"name": "Dubai office", "scores": {"Revenue impact": 5, "Strategic fit": 3, "Effort": 5}, "cost": 400},
                {"name": "Price rise", "scores": {"Revenue impact": 4, "Strategic fit": 4, "Effort": 1}},
                {"name": "Rebrand", "scores": {"Revenue impact": 1, "Strategic fit": 2, "Effort": 4}},
            ],
        }
    )


def test_weighted_scoring_by_hand() -> None:
    result = weighted_scoring(scoring_request())
    assert result.weights == {"Revenue impact": 0.5, "Strategic fit": 0.1667, "Effort": 0.3333}
    by_name = {o.name: o for o in result.options}
    # Price rise: 0.5*(3/4) + (1/6)*(3/4) + (1/3)*(1 - 0/4) = 0.375 + 0.125 + 0.3333
    assert by_name["Price rise"].total == pytest.approx(0.8333, abs=1e-4)
    # Dubai: 0.5*1 + (1/6)*0.5 + (1/3)*0 = 0.5833
    assert by_name["Dubai office"].total == pytest.approx(0.5833, abs=1e-4)
    assert [o.name for o in result.options] == ["Price rise", "Dubai office", "Rebrand"]
    assert [o.rank for o in result.options] == [1, 2, 3]
    assert by_name["Price rise"].quadrant == "Quick win"
    assert by_name["Dubai office"].quadrant == "Big bet"  # value (3*1 + 1*0.5)/4 = 0.875, feasibility 0
    assert by_name["Rebrand"].quadrant == "Deprioritise"
    assert by_name["Dubai office"].cost == 400


def test_scoring_validation() -> None:
    raw = scoring_request().model_dump()
    raw["options"][0]["scores"]["Effort"] = 9
    with pytest.raises(ValidationError, match="outside"):
        ScoringRequest.model_validate(raw)
    raw = scoring_request().model_dump()
    del raw["options"][1]["scores"]["Effort"]
    with pytest.raises(ValidationError, match="cover exactly"):
        ScoringRequest.model_validate(raw)


def test_expected_value() -> None:
    options = [
        EVOption.model_validate(
            {
                "name": "Launch",
                "outcomes": [
                    {"label": "hit", "probability": 0.3, "value": 1_000_000},
                    {"label": "meh", "probability": 0.5, "value": 100_000},
                    {"label": "flop", "probability": 0.2, "value": -400_000},
                ],
            }
        ),
        EVOption.model_validate({"name": "Wait", "outcomes": [{"label": "same", "probability": 1, "value": 0}]}),
    ]
    launch, wait = expected_values(options)
    assert launch.name == "Launch"
    assert launch.expected_value == 270_000  # 300k + 50k - 80k
    assert launch.probability_of_loss == 0.2
    assert (launch.worst, launch.best) == (-400_000, 1_000_000)
    assert wait.expected_value == 0 and wait.std_dev == 0
    with pytest.raises(ValidationError, match="sum to"):
        EVOption.model_validate({"name": "x", "outcomes": [{"label": "a", "probability": 0.5, "value": 1}]})


def test_decision_tree_pilot_first() -> None:
    """Go big now (EV 0.4*900 - 0.6*300 = 180) vs pilot (cost 50) that reveals the market first."""
    tree = DecisionNode.model_validate(
        {
            "name": "Dubai",
            "choices": [
                {
                    "label": "Open office now",
                    "node": {
                        "type": "chance",
                        "branches": [
                            {"label": "demand", "probability": 0.4, "node": {"type": "terminal", "value": 900}},
                            {"label": "no demand", "probability": 0.6, "node": {"type": "terminal", "value": -300}},
                        ],
                    },
                },
                {
                    "label": "Pilot first",
                    "cost": 50,
                    "node": {
                        "type": "chance",
                        "branches": [
                            {
                                "label": "pilot works",
                                "probability": 0.4,
                                "node": {
                                    "type": "decision",
                                    "choices": [
                                        {"label": "scale", "node": {"type": "terminal", "value": 850}},
                                        {"label": "stop", "node": {"type": "terminal", "value": 0}},
                                    ],
                                },
                            },
                            {
                                "label": "pilot fails",
                                "probability": 0.6,
                                "node": {
                                    "type": "decision",
                                    "choices": [
                                        {"label": "scale", "node": {"type": "terminal", "value": -300}},
                                        {"label": "stop", "node": {"type": "terminal", "value": 0}},
                                    ],
                                },
                            },
                        ],
                    },
                },
                {"label": "Do nothing", "node": {"type": "terminal", "value": 0}},
            ],
        }
    )
    result = solve_decision_tree(tree)
    # Pilot: 0.4*850 + 0.6*0 - 50 = 290 > 180 > 0
    assert result.expected_value == 290
    assert result.policy["/"] == "Pilot first"
    assert result.choice_values["/"] == {"Open office now": 180, "Pilot first": 290, "Do nothing": 0}
    assert result.policy["/Pilot first/pilot works"] == "scale"
    assert result.policy["/Pilot first/pilot fails"] == "stop"


def test_tree_validation_and_terminal_root() -> None:
    assert solve_decision_tree(TerminalNode(value=5)).expected_value == 5
    with pytest.raises(ValidationError, match="sum to"):
        ChanceNode.model_validate(
            {"branches": [{"label": "a", "probability": 0.7, "node": {"type": "terminal", "value": 1}}]}
        )


def test_kill_criteria_use_live_metrics(loaded_db: FinanceDB) -> None:
    criteria = [
        KillCriterion(name="Runway floor", metric="runway", operator="<", threshold=12),
        KillCriterion(name="Margin floor", metric="gross_margin", operator="<", threshold=0.5),
    ]
    runway, margin = evaluate_kill_criteria(MetricsEngine(loaded_db), criteria)
    assert runway.triggered is True and runway.value == 10.65
    assert runway.condition == "runway < 12"
    assert runway.lineage.metric == "runway"
    assert margin.triggered is False
    with pytest.raises(ValidationError, match="unknown metric"):
        KillCriterion(name="x", metric="happiness", operator=">", threshold=1)


# --- calibration -----------------------------------------------------------------------------------------------
def test_brier_score_by_hand() -> None:
    assert brier_score([]) is None
    # (0.9-1)^2 + (0.7-0)^2 + (0.5-1)^2 = 0.01 + 0.49 + 0.25 = 0.75 -> / 3
    assert brier_score([(0.9, True), (0.7, False), (0.5, True)]) == pytest.approx(0.25)


def test_calibration_store_round_trip(tmp_path: Path) -> None:
    store = CalibrationStore(tmp_path)
    a = store.add(PredictionIn(statement="Churn stays under 2%", probability=0.8))
    b = store.add(PredictionIn(statement="Dubai pilot signs 3 customers", probability=0.3, owner="devils_advocate"))
    store.add(PredictionIn(statement="Pending one", probability=0.6))
    store.resolve(a.id, True)
    store.resolve(b.id, True)

    reopened = CalibrationStore(tmp_path)  # persisted to disk
    assert len(reopened.list()) == 3
    assert [p.statement for p in reopened.list(pending=True)] == ["Pending one"]
    scores = {s.owner: s for s in reopened.scores()}
    assert scores["founder"].resolved == 1 and scores["founder"].pending == 1
    assert scores["founder"].brier_score == pytest.approx(0.04)  # (0.8 - 1)^2
    assert scores["devils_advocate"].brier_score == pytest.approx(0.49)  # (0.3 - 1)^2
    assert scores["all"].brier_score == pytest.approx(0.265)
    assert scores["all"].hit_rate == 1.0


def test_calibration_errors(tmp_path: Path) -> None:
    store = CalibrationStore(tmp_path)
    with pytest.raises(CalibrationError, match="no prediction"):
        store.resolve("missing", True)
    with pytest.raises(ValidationError):
        PredictionIn(statement="x", probability=1.5)
    (tmp_path / "calibration.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CalibrationError, match="corrupt"):
        store.list()
