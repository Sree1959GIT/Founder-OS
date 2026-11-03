from __future__ import annotations

from app.agents.events import Citation
from app.agents.verifier import extract_figures, verify, verify_citations, verify_numbers

KNOWN = [10.65, 1835125.06, 0.7213, 172280.47, 255344.27]


def test_extracts_money_percent_and_suffixes() -> None:
    text = "Runway is 10.65 months; cash $1,835,125.06, margin 72.13 %, burn $172.3K, ARR $3.06M, loss -12.5."
    figures = {f.text: f.value for f in extract_figures(text)}
    assert figures["10.65"] == 10.65 and figures["$1,835,125.06"] == 1835125.06
    assert figures["72.13 %"] == 72.13 and figures["$172.3K"] == 172300 and figures["$3.06M"] == 3060000
    assert figures["-12.5"] == -12.5


def test_skips_dates_years_and_counting_words() -> None:
    assert extract_figures("Zero cash in 2027-09, over the trailing 3 months, since 2025, 2 options.") == []
    assert [f.value for f in extract_figures("We have 142 customers")] == [142]


def test_numbers_match_lineage_within_rounding() -> None:
    assert verify_numbers("Runway is 10.65 months (about 10.7), cash $1.84M, margin 72.13 %.", KNOWN) == []
    assert verify_numbers("Burn is $172,280.47 a month.", KNOWN) == []
    assert verify_numbers("Runway is 14.2 months.", KNOWN) == ["14.2"]
    assert verify_numbers("A 10 % price rise", [], context="What if we raise prices 10 %?") == []


def test_citation_rules() -> None:
    cites = [Citation(path="notes/pricing-strategy.md", heading="Pricing", chunk_id="notes/pricing-strategy.md#p0")]
    assert verify_citations("Annual plans get 15 % off [notes/pricing-strategy.md].", cites) == []
    assert verify_citations("See [notes/made-up.md].", cites) == ["notes/made-up.md was not returned by a search"]
    assert verify_citations("Some claim.", []) == ["the answer cites no vault source"]
    report = verify("Annual plans get 15 % off.", [15.0], cites, needs_citations=True)
    assert report.ok and report.issues == []
    bad = verify("Runway is 99 months.", KNOWN, [], needs_citations=False)
    assert not bad.ok and bad.unverified_numbers == ["99"] and bad.issues == ["number without lineage: 99"]
