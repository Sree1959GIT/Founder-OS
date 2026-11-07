"""Founder review 14, 19 and 20: the badge's three states, removed claims counted not shown, and memo figures."""

from __future__ import annotations

from app.agents.sources import Evidence, without_unsupported
from app.agents.verification import verification

ASSUMPTIONS = ["Rent or desk: $5,000 a month (assumption, confirm).", "Travel: $3,000 a month (assumption, confirm)."]


def test_placeholder_assumptions_alone_give_the_amber_state() -> None:
    v = verification(["this rests on 2 assumptions to confirm"], True, ASSUMPTIONS, ["pnl.csv"])
    assert v.state == "assumptions" and v.assumptions == ASSUMPTIONS and v.reasons == []


def test_nothing_to_confirm_and_nothing_failed_is_verified() -> None:
    assert verification([], True, [], ["pnl.csv"]).state == "verified"


def test_a_failed_check_is_not_verified_with_reasons_that_name_no_figure() -> None:
    issues = [
        "Market Scout: number without lineage: 150000000000",
        "Market Scout: removed: unsupported source (2)",
        "advisor: removed: unsupported source (1)",
        "Librarian: notes/economic-overview.md was not returned by a search",
        "this rests on 2 assumptions to confirm",
    ]
    v = verification(issues, True, ASSUMPTIONS, [])
    assert v.state == "not_verified" and v.removed_claims == 3
    text = " ".join(v.reasons)
    assert "150000000000" not in text and "economic-overview" not in text
    assert "3 unsupported claims removed." in v.reasons
    assert "A cited note was not found in your vault." in v.reasons


def test_a_figure_removed_before_it_was_shown_is_counted_not_failed() -> None:
    issues = [
        "Market Scout: number without lineage: $166 billion",
        "Market Scout: removed: unsupported source (1)",
        "this rests on 5 assumptions to confirm",
    ]
    v = verification(issues, True, ASSUMPTIONS, [], resolved=["Market Scout: number without lineage: $166 billion"])
    assert v.state == "assumptions" and v.removed_claims == 1 and v.reasons == []


def test_an_unfinished_agent_is_not_verified() -> None:
    v = verification([], False, [], [])
    assert v.state == "not_verified" and v.reasons == ["An agent did not finish."]


def test_a_figure_from_a_memo_on_record_is_cited_to_it_and_kept() -> None:
    memo = "decisions/2026-11-06-dubai-office.md"
    evidence = Evidence(passages={memo: [3000.0, 6.0]}, records=[memo])
    text = "Your pilot budget on record is $3,000 a month. Review it after 6 months. Dubai's GDP is $150 billion."
    kept, removed = without_unsupported(text, evidence)
    assert f"$3,000 a month [{memo}]." in kept and "Review it after 6 months." in kept
    assert "150 billion" not in kept and len(removed) == 1


def test_without_a_record_the_same_figure_still_goes() -> None:
    kept, removed = without_unsupported("Your pilot budget is $3,000 a month.", Evidence())
    assert kept == "" and removed
