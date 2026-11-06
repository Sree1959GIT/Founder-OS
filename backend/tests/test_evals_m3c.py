"""M3c evals: the labelled set, offline prompt tuning, the provider and embedding bake-offs. Fakes only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agents.registry import PROMPTS_DIR, REGISTRY
from app.engine.embeddings import FakeEmbedder, OllamaEmbedder, task_prefixes
from app.evals.agent_harness import AgentRun, run_agent, score
from app.evals.embedding_bakeoff import EmbedderScore, ModeScore, load_queries, recommend, score_embedder
from app.evals.labelled_eval import CATEGORIES, LabelledCase, check_chat, load_cases, run_offline, summary
from app.evals.prompt_tuning import (
    VERSIONS_DIR,
    VariantScore,
    agents_with_versions,
    apply_version,
    choose_best,
    live_version,
    load_manifest,
    prompt_override,
    record,
    tune_agent,
    versions_of,
)
from app.evals.provider_bakeoff import (
    AGENT_TYPES,
    LaneRow,
    ProviderRow,
    cases_for,
    lane_problem,
    recommend_defaults,
    run_lane,
    run_provider,
    summarise_calls,
)
from app.evals.vault_eval import SAMPLE_VAULT, make_sample_vault, sample_finance
from app.llm.costs import CostLedger
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter


# --- the labelled set ------------------------------------------------------------------------------------------------
def test_there_are_at_least_50_labelled_questions_in_every_category() -> None:
    cases = load_cases()
    assert len(cases) >= 50
    assert len({c.id for c in cases}) == len(cases)
    for category in CATEGORIES:
        assert sum(c.category == category for c in cases) >= 5, category
    for case in cases:
        assert all(agent in REGISTRY for agent in case.agents)
        assert all(agent in REGISTRY for agent in case.tune_for)


def test_every_labelled_question_passes_offline_with_the_llm_down() -> None:
    results = run_offline()
    assert [r.line() for r in results if not r.passed] == []
    assert len(summary(results)) == len(CATEGORIES)


def test_the_labelled_rubric_catches_what_it_is_for() -> None:
    case = LabelledCase(
        id="x",
        category="pricing",
        question="q",
        intent="decision",
        agents=["financial_analyst"],
        decision_type="pricing",
        must_say=["10.65"],
        must_not=["you decided"],
        cited=["notes/a.md"],
        goal_away=True,
    )
    reply = {"answer": "You decided. The founder agrees.", "intent": "finance", "agents": [], "decision_type": "hire"}
    problems = " ".join(check_chat(case, "live", reply).problems)
    for word in ("intent finance", "not on the team", "decision type hire", "10.65", "you decided", "notes/a.md"):
        assert word in problems
    assert "the founder" in problems and "moves away" in problems


# --- prompt tuning ---------------------------------------------------------------------------------------------------
def test_every_tuned_agent_has_questions_and_a_live_version_on_record() -> None:
    agents = agents_with_versions()
    assert {"people_ops", "regulatory_tax", "devils_advocate", "librarian"} <= set(agents)
    for agent in agents:
        assert len(versions_of(agent)) >= 2
        assert sum(agent in c.tune_for for c in load_cases()) >= 3, agent
    assert all(a in load_manifest() for a in agents)
    assert live_version("people_ops") in versions_of("people_ops")


def test_a_version_is_kept_as_written_and_the_override_is_only_for_the_measurement() -> None:
    spec = REGISTRY["people_ops"]
    live = spec.prompt()
    with prompt_override("people_ops", "VARIANT"):
        assert spec.prompt() == "VARIANT"
        assert REGISTRY["librarian"].prompt() != "VARIANT"
    assert spec.prompt() == live


async def test_tuning_measures_each_version_and_a_tie_keeps_the_live_one(tmp_path: Path) -> None:
    for version in ("v1", "v2", "v3"):
        (tmp_path / "people_ops").mkdir(exist_ok=True)
        (tmp_path / "people_ops" / f"{version}.md").write_text(version, encoding="utf-8")

    async def run(agent: str, question: str) -> AgentRun:
        text = REGISTRY[agent].prompt()
        passes = text == "v3" or (text == "v2" and question == "a") or (text == "v1" and question == "b")
        return AgentRun(agent, question, text, "done", True, 0, 10.0, problems=[] if passes else ["no"])

    scores = await tune_agent("people_ops", run, root=tmp_path, questions=["a", "b"])
    assert [(s.version, s.passed) for s in scores] == [("v1", 1), ("v2", 1), ("v3", 2)]
    assert choose_best(scores, "v1").version == "v3"  # type: ignore[union-attr]
    assert choose_best(scores[:2], "v1").version == "v1"  # type: ignore[union-attr]
    assert choose_best(scores[:2], "v2").version == "v2"  # type: ignore[union-attr]
    manifest = tmp_path / "MANIFEST.json"
    record("people_ops", scores, scores[2], model="m", date="2026-11-05", path=manifest)
    saved = json.loads(manifest.read_text(encoding="utf-8"))["people_ops"]
    assert saved["best"] == "v3" and saved["results"]["v1"]["passed"] == 1
    prompts = tmp_path / "live"
    prompts.mkdir()
    (prompts / "people_ops.md").write_text("v1", encoding="utf-8")
    assert live_version("people_ops", tmp_path, prompts) == "v1"
    apply_version("people_ops", "v3", tmp_path, prompts)
    assert live_version("people_ops", tmp_path, prompts) == "v3"
    (prompts / "people_ops.md").write_text("edited by hand", encoding="utf-8")
    assert live_version("people_ops", tmp_path, prompts) is None


def test_repairs_and_latency_break_a_tie() -> None:
    def scored(version: str, repairs: int, latency: float) -> VariantScore:
        return VariantScore("a", version, [AgentRun("a", "q", "t", "done", True, repairs, latency)])

    best = min([scored("v1", 1, 10.0), scored("v2", 0, 50.0), scored("v3", 0, 20.0)], key=VariantScore.rank)
    assert best.version == "v3"


def test_the_score_catches_the_off_brief_wording_seen_live() -> None:
    assert "names no owner" in score("people_ops", "q", "It is fine.", None, True)
    assert "gives no first steps" in score("people_ops", "q", "You own it.", None, True)
    assert any("points" in p for p in score("regulatory_tax", "q", "Ask your adviser.", None, True))
    assert any("risks" in p for p in score("devils_advocate", "q", "- Risk: x.", None, True))
    assert any(
        "decided to decide" in p for p in score("librarian", "q", 'You decided to "Decide whether". [a.md]', None, True)
    )
    assert score("people_ops", "q", "", None, True) == ["empty answer"]
    good = "- Risk: a. Likelihood: low. Impact: low. Mitigation: b.\n" * 3
    assert score("devils_advocate", "q", good, None, True) == []


# --- the provider bake-off -------------------------------------------------------------------------------------------
@pytest.fixture
def data(tmp_path: Path) -> tuple[Any, Any]:
    return sample_finance(tmp_path / "finance"), make_sample_vault(tmp_path / "vault")


def test_every_agent_type_has_questions_for_the_bake_off() -> None:
    for agent in AGENT_TYPES:
        assert len(cases_for(agent, 3)) == 3, agent


async def test_a_model_is_scored_and_a_cloud_model_never_sees_a_local_only_agent(data: tuple[Any, Any]) -> None:
    finance, vault = data

    def owner(messages: list[Any], tools: Any, schema: Any) -> str:
        return "You own this. First steps: call one customer, then a second, then a third."

    local = FakeProvider(default=owner, name="local", model="small")
    rows = await run_provider(local, finance, vault, agents=("people_ops",), per_agent=2)
    assert rows[0].passed == 2 and rows[0].cost_per_answer(None) == 0.0
    cloud = FakeProvider(default=owner, name="cloudy", model="cloud-model", is_cloud=True)
    router = LLMRouter(local, cloud, cloud_allowed=True)
    rows = await run_provider(cloud, finance, vault, agents=("librarian", "people_ops"), per_agent=1, router=router)
    assert "local-only" in rows[0].skipped and not rows[0].runs
    assert len(rows[1].runs) == 1


async def test_run_agent_counts_a_repair_and_does_not_count_rules_as_a_pass(data: tuple[Any, Any]) -> None:
    finance, vault = data
    invented = "You own this at $48,123. First steps: call."
    provider = FakeProvider(
        [invented, "You own this. First steps: call one customer."],
        default=lambda *_: "You own this. First steps: call one customer.",
    )
    run = await run_agent("people_ops", "Who would own a pilot?", LLMRouter(provider), finance, vault)
    assert run.repairs == 1

    def down(*_: Any) -> str:
        from app.llm.base import LLMUnavailable

        raise LLMUnavailable("down")

    fallback = await run_agent("people_ops", "Who owns it?", LLMRouter(FakeProvider(default=down)), finance, vault)
    assert fallback.problems[0].startswith("the model did not answer")


async def test_the_lane_test_wants_one_short_sentence_with_no_figure() -> None:
    assert lane_problem("") == "empty"
    assert lane_problem("Runway is 10 months.") == "states a figure"
    assert lane_problem(" ".join(["word"] * 40)) == "too long"
    assert lane_problem("The team is still working.") == ""
    row = await run_lane(FakeProvider(default=lambda *_: "The team is still working.", model="tiny"))
    assert row.passed == len(row.replies) == 5
    assert row.cells()[0] == "tiny"


def test_calls_are_summarised_from_the_ledger_file(tmp_path: Path) -> None:
    path = tmp_path / "llm_calls.jsonl"
    rows = [
        {"agent_type": "advisor", "model": "qwen3:8b", "latency_ms": 2000, "est_cost_usd": 0.0},
        {"agent_type": "advisor", "model": "qwen3:8b", "latency_ms": 4000, "est_cost_usd": 0.0, "error": "x"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    assert summarise_calls(path) == [["advisor", "qwen3:8b", "2", "3.0", "$0.0000", "1"]]
    assert summarise_calls(tmp_path / "missing.jsonl") == []


def test_defaults_are_proposed_by_pass_rate_then_cost_then_speed(tmp_path: Path) -> None:
    def row(model: str, passed: bool, latency: float, cloud: bool = False) -> ProviderRow:
        run = AgentRun("people_ops", "q", "t", "done", True, 0, latency, 1000, 1000, problems=[] if passed else ["x"])
        return ProviderRow(model, "people_ops", cloud, [run])

    ledger = CostLedger(tmp_path / "c.jsonl", prices={"cloud": (1.0, 1.0)})
    rows = [row("slow", True, 9000), row("fast", True, 1000), row("bad", False, 100), row("cloud", True, 500, True)]
    lines = recommend_defaults(rows, [], ledger)
    assert lines == ["people_ops: fast (1/1, 1.0 s)"]
    assert "no model passed" in recommend_defaults([row("bad", False, 100)], [], ledger)[0]
    good = LaneRow("tiny", [("ok", 1.0, ""), ("ok", 1.0, "")])
    assert "tiny" in recommend_defaults(rows, [good], ledger)[-1]
    assert "keep the templates" in recommend_defaults(rows, [LaneRow("x", [("", 9.0, "empty")])], ledger)[-1]


# --- the embedding bake-off ------------------------------------------------------------------------------------------
def test_each_embedding_model_gets_its_documented_prefixes() -> None:
    assert task_prefixes("nomic-embed-text") == ("search_document: ", "search_query: ")
    assert task_prefixes("embeddinggemma:latest") == ("title: none | text: ", "task: search result | query: ")
    assert task_prefixes("qwen3:8b") == ("", "")
    embedder = OllamaEmbedder("http://x", "embeddinggemma")
    assert embedder.name == "ollama:embeddinggemma"


def test_every_labelled_query_points_at_a_real_note() -> None:
    queries = load_queries()
    assert len(queries) >= 30
    for query in queries:
        assert query.relevant and all((SAMPLE_VAULT / path).is_file() for path in query.relevant), query.query


def test_the_embedding_scorer_runs_over_the_sample_vault() -> None:
    result = score_embedder(FakeEmbedder(), load_queries()[:6])
    assert not result.error and result.dim == 64 and result.chunks > 0
    assert set(result.modes) == {"dense", "hybrid"}
    assert 0.0 <= result.modes["dense"].mrr <= 1.0 and result.modes["hybrid"].recall_at_k > 0
    assert result.rows()[0][0] == "fake:64"


def test_a_failed_embedder_is_reported_not_raised() -> None:
    embedder = FakeEmbedder()
    embedder.fail = True
    result = score_embedder(embedder, load_queries()[:2])
    assert result.error and "fail" in result.rows()[0][-1]


def test_the_embedding_reading_needs_more_than_noise() -> None:
    def scored(name: str, ranks: list[int | None]) -> EmbedderScore:
        return EmbedderScore(name, modes={"hybrid": ModeScore("hybrid", ranks)})

    nomic, gemma = scored("ollama:nomic-embed-text", [1, 1, 2]), scored("ollama:embeddinggemma", [1, 1, 1])
    assert "embeddinggemma beats" in recommend([nomic, gemma], "nomic")
    assert "licence" in recommend([nomic, gemma], "nomic")
    close = scored("ollama:embeddinggemma", [1, 1, 2])
    assert "keep ollama:nomic-embed-text" in recommend([nomic, close], "nomic")
    assert "Not enough" in recommend([nomic], "nomic")


def test_nothing_in_the_app_rewrites_a_prompt() -> None:
    """Tuning is offline: the app itself only ever reads its prompts."""
    app_dir = PROMPTS_DIR.parent.parent
    for path in app_dir.rglob("*.py"):
        if path.name == "prompt_tuning.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert not ("PROMPTS_DIR" in text and "write_text" in text), path
    assert VERSIONS_DIR.parent == PROMPTS_DIR
