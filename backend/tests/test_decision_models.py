"""M3c: Laya and Jev behind the decision interface (fakes only), the bake-off harness, the Laya training file."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.agents.setup import build_decisions
from app.config import Settings
from app.decision.base import Decision, DecisionError, DecisionService, FakeDecisionProvider
from app.decision.jev import JEV_URL, JevProvider, routing_state
from app.decision.laya import LayaProvider, parse_answer, questions_for
from app.evals.decision_bakeoff import (
    QUESTIONS,
    BakeoffRow,
    CascadeProvider,
    Prediction,
    RoutingExample,
    RulesProvider,
    expected_calibration_error,
    load_examples,
    recommend,
    run_bakeoff,
    table,
)
from app.llm.fake import FakeProvider
from app.llm.privacy import NameIndex
from app.llm.router import LLMRouter

OPTIONS = ["finance", "decision"]


def _answer(choice: str = "finance", p: float = 0.9, **extra: Any) -> dict[str, Any]:
    return {
        "answers": {"pick": {"choice": choice, "confidence": p, "probabilities": {choice: p}}},
        **extra,
    }


# --- Laya ------------------------------------------------------------------------------------------------------------
async def test_laya_asks_a_typed_choice_and_reads_the_probability() -> None:
    seen: list[Any] = []

    def predictor(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        seen.append((state, questions))
        return _answer(routing={"model": "laya"})

    decision = await LayaProvider(predictor=predictor).choose({"message": "runway?"}, "Which?", OPTIONS)
    assert (decision.choice, decision.probability) == ("finance", 0.9)
    assert decision.provider == "laya:laya"
    assert seen[0][1]["pick"]["type"] == "choice"
    assert set(seen[0][1]["pick"]["criteria"]) == set(OPTIONS)


async def test_laya_without_the_package_raises_a_decision_error_so_the_llm_takes_over() -> None:
    if importlib.util.find_spec("laya") is not None:
        pytest.skip("laya is installed here")
    with pytest.raises(DecisionError, match="not installed"):
        await LayaProvider().choose({}, "Which?", OPTIONS)
    service = DecisionService(LayaProvider(), fallback=FakeDecisionProvider(probability=0.8))
    decision = await service.choose("Which?", OPTIONS)
    assert decision.provider == "fake" and decision.escalated_from == "laya"


async def test_laya_failures_and_bad_answers_are_decision_errors() -> None:
    def boom(state: Any, questions: Any) -> dict[str, Any]:
        raise RuntimeError("CUDA out of memory")

    with pytest.raises(DecisionError, match="CUDA out of memory"):
        await LayaProvider(predictor=boom).choose({}, "Which?", OPTIONS)
    with pytest.raises(DecisionError, match="not an option"):
        await LayaProvider(predictor=lambda s, q: _answer("elsewhere")).choose({}, "Which?", OPTIONS)
    with pytest.raises(DecisionError, match="unusable"):
        parse_answer({"answers": {}}, OPTIONS)


async def test_a_low_confidence_answer_falls_back_to_the_llm() -> None:
    laya = LayaProvider(predictor=lambda s, q: _answer("finance", 0.4))
    service = DecisionService(laya, fallback=FakeDecisionProvider(probability=0.9), min_confidence=0.75)
    decision = await service.choose("Which?", OPTIONS)
    assert decision.escalated_from == "laya:laya"
    confident = LayaProvider(predictor=lambda s, q: _answer("decision", 0.95))
    assert (
        await DecisionService(confident, fallback=FakeDecisionProvider()).choose("Which?", OPTIONS)
    ).choice == "decision"


# --- Jev -------------------------------------------------------------------------------------------------------------
def _names() -> NameIndex:
    index = NameIndex([lambda: [("customer", "Ironcrest Media"), ("person", "Priya Nair")]])
    return index


def _jev(handler: Any, **kwargs: Any) -> JevProvider:
    return JevProvider("sk-jev-secret", transport=httpx.MockTransport(handler), **kwargs)


async def test_jev_sends_the_documented_request_and_counts_its_cost() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = {**_answer(), "model": "jev-1.14.0", "usage": {"input_tokens": 100, "output_tokens": 0}}
        return httpx.Response(200, json=body)

    provider = _jev(handler)
    decision = await provider.choose({"message": "What is our runway?"}, "Which?", OPTIONS)
    assert decision.provider == "jev:jev-1.14.0" and decision.choice == "finance"
    sent = json.loads(requests[0].content)
    assert str(requests[0].url) == JEV_URL
    assert requests[0].headers["authorization"] == "Bearer sk-jev-secret"
    assert sent["model"] == "jev-latest"
    assert sent["questions"]["pick"]["type"] == "choice"
    assert provider.est_cost_usd == pytest.approx(100 / 1e6 * 0.042)


def test_jev_only_ever_receives_non_sensitive_routing_state() -> None:
    state = {
        "message": "Ironcrest Media pays $12,000 and Priya Nair (priya@x.test) says 10% off.\nAcme, 4500\nBeta, 3000",
        "rows": [{"customer": "Ironcrest Media", "mrr": 12000}],
        "note": "a whole vault passage",
    }
    sent = routing_state(state, _names())
    assert set(sent) == {"message"}
    text = sent["message"]
    for private in ("Ironcrest", "Priya", "12,000", "10%", "priya@", "4500", "Acme"):
        assert private not in text, text
    assert "[number]" in text


async def test_jev_fails_closed_and_never_logs_or_raises_the_key() -> None:
    def broken() -> list[tuple[str, str]]:
        raise OSError("locked")

    called: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(1)
        return httpx.Response(401, json={"error": "bad key sk-jev-secret"})

    with pytest.raises(DecisionError, match="could not read the names"):
        await _jev(handler, names=NameIndex([broken])).choose({"message": "hi"}, "Which?", OPTIONS)
    assert not called
    with pytest.raises(DecisionError) as raised:
        await _jev(handler).choose({"message": "hi"}, "Which?", OPTIONS)
    assert "sk-jev-secret" not in str(raised.value)
    with pytest.raises(DecisionError, match="no API key"):
        await JevProvider("").choose({"message": "hi"}, "Which?", OPTIONS)


def test_settings_choose_the_provider_and_the_default_stays_the_llm(tmp_path: Path) -> None:
    def settings(**kwargs: Any) -> Settings:
        return Settings(_env_file=None, data_dir=tmp_path, **kwargs)  # type: ignore[call-arg]

    router = LLMRouter(FakeProvider())
    assert Settings.model_fields["decision_provider"].default == "llm"
    assert build_decisions(settings(decision_provider="llm"), router).provider.name == "llm"
    assert build_decisions(settings(decision_provider="llm"), router).fallback is None
    laya = build_decisions(settings(decision_provider="laya", laya_checkpoint="models/x"), router)
    assert laya.provider.name == "laya" and laya.fallback is not None and laya.fallback.name == "llm"
    assert build_decisions(settings(decision_provider="jev"), router).provider.name == "llm"  # no key
    jev = build_decisions(settings(decision_provider="jev", jev_api_key="k"), router)
    assert jev.provider.name == "jev" and jev.fallback is not None


# --- the labelled examples -------------------------------------------------------------------------------------------
def test_there_are_about_200_examples_of_every_kind_and_label_with_a_held_out_split() -> None:
    examples = load_examples()
    assert len(examples) >= 200
    for kind, (_, options) in QUESTIONS.items():
        labels = {e.label for e in examples if e.kind == kind}
        assert labels == set(options), kind
    train, test = load_examples(split="train"), load_examples(split="test")
    assert len(train) + len(test) == len(examples) and len(test) >= 60
    assert not {e.text for e in train} & {e.text for e in test}


async def test_todays_rules_are_right_when_they_answer() -> None:
    rows = await run_bakeoff({"rules": RulesProvider()}, load_examples())
    turn = next(r for r in rows if r.kind == "turn")
    assert turn.confident_accuracy >= 0.85, [(p.example.text, p.choice) for p in turn.confident if not p.correct]


# --- the harness -----------------------------------------------------------------------------------------------------
async def test_the_harness_reports_accuracy_coverage_and_errors() -> None:
    examples = [RoutingExample("intent", "What's our runway?", "finance"), RoutingExample("intent", "hi", "chitchat")]

    class Half:
        name = "half"

        async def choose(self, state: dict[str, Any], question: str, options: list[str]) -> Decision:
            if state["message"] == "hi":
                raise DecisionError("down")
            return Decision(question=question, options=options, choice="finance", probability=0.9, provider="half")

    rows = await run_bakeoff({"half": Half()}, examples)
    row = rows[0]
    assert (row.n, row.accuracy, row.coverage, row.errors) == (2, 0.5, 0.5, 1)
    assert row.confident_accuracy == 1.0
    assert "half" in table(["provider"], [["half"]])


def test_calibration_scores_a_confident_wrong_model_badly() -> None:
    example = RoutingExample("intent", "x", "finance")
    honest = [Prediction(example, "finance", 0.8, 1.0)] * 8 + [Prediction(example, "decision", 0.8, 1.0)] * 2
    overconfident = [Prediction(example, "finance", 0.99, 1.0)] * 5 + [Prediction(example, "decision", 0.99, 1.0)] * 5
    assert expected_calibration_error(honest) == pytest.approx(0.0)
    assert expected_calibration_error(overconfident) == pytest.approx(0.49)
    assert BakeoffRow("x", "intent", overconfident).brier > BakeoffRow("x", "intent", honest).brier


async def test_the_cascade_uses_the_fallback_only_below_the_threshold() -> None:
    primary = LayaProvider(predictor=lambda s, q: _answer("finance", 0.5))
    fallback = FakeDecisionProvider(rules=lambda s, q, o: ("decision", 0.9))
    decision = await CascadeProvider(primary, fallback).choose({}, "Which?", OPTIONS)
    assert decision.choice == "decision"
    sure = LayaProvider(predictor=lambda s, q: _answer("finance", 0.9))
    assert (await CascadeProvider(sure, fallback).choose({}, "Which?", OPTIONS)).choice == "finance"


def test_the_reading_never_claims_more_than_the_table() -> None:
    example = RoutingExample("intent", "x", "finance")
    good = BakeoffRow("laya", "intent", [Prediction(example, "finance", 0.9, 1.0)] * 10)
    bad = BakeoffRow("llm:qwen3:8b", "intent", [Prediction(example, "decision", 0.9, 1.0)] * 10)
    assert "your call" in recommend([good, bad])
    same = BakeoffRow("laya", "intent", good.predictions)
    other = BakeoffRow("llm:qwen3:8b", "intent", good.predictions)
    assert "keep" in recommend([same, other]).lower()


# --- the training file -----------------------------------------------------------------------------------------------
def _finetune_module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts" / "finetune_laya.py"
    spec = importlib.util.spec_from_file_location("finetune_laya", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_training_file_uses_the_train_split_and_corrected_log_lines_only(tmp_path: Path) -> None:
    module = _finetune_module()
    log = tmp_path / "decision_log.jsonl"
    rows = [
        {"id": "a", "question": "Which?", "options": OPTIONS, "state": {"message": "x"}, "choice": "finance"},
        {"id": "b", "question": "Which?", "options": OPTIONS, "state": {"message": "y"}, "choice": "finance"},
        {"correction_for": "a", "correct": "decision"},
        {"correction_for": "b", "correct": "not an option"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    lines = module.training_lines(log_path=log)
    train = {e.text for e in load_examples(split="train")}
    test = {e.text for e in load_examples(split="test")}
    seen = {line["state"].get("message") or line["state"].get("turn") for line in lines}
    assert train <= seen and not (test & seen)
    assert lines[-1]["questions"]["pick"]["instructions"] == questions_for("Which?", OPTIONS)["pick"]["instructions"]
    assert lines[-1]["expected"] == {"pick": "decision"} and len(lines) == len(train) + 1
    assert all(set(line) == {"state", "questions", "expected"} for line in lines)
    assert all(line["expected"]["pick"] in line["questions"]["pick"]["criteria"] for line in lines)
    out = tmp_path / "train.jsonl"
    module.write_training_file(out, lines)
    assert len(out.read_text(encoding="utf-8").splitlines()) == len(lines)


def test_every_label_has_words_for_the_model() -> None:
    module = _finetune_module()
    assert {e.label for e in load_examples()} <= set(module.OPTION_TEXT)
