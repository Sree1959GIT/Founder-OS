"""The specialist eval stays green offline, and its checks catch what they are for."""

from __future__ import annotations

from app.evals.agents_eval import AgentCase, check_reply, load_cases, run_offline


def test_there_is_one_case_per_new_agent() -> None:
    assert {c.agent for c in load_cases()} == {
        "devils_advocate",
        "market_scout",
        "revenue_customer",
        "people_ops",
        "regulatory_tax",
        "prioritiser",
        "perspective_lens",
        "memo_writer",
    }


def test_every_specialist_passes_offline_with_no_llm_and_with_a_careless_one() -> None:
    results = run_offline()
    assert len(results) == 2 * len(load_cases())
    assert [r.line() for r in results if not r.passed] == []


def test_the_checks_catch_a_missing_agent_artifact_and_memo() -> None:
    case = AgentCase(id="x", question="q", agent="memo_writer", artifact="decision_memo", memo=True)
    assert "not on the team" in check_reply(case, "live", {"agents": []}).problems[0]
    reply = {"agents": [{"type": "memo_writer", "status": "done", "artifacts": [], "text": ""}], "answer": ""}
    problems = check_reply(case, "live", reply).problems
    assert "no decision_memo artifact" in problems and "no memo written" in problems
