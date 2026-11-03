from __future__ import annotations

from app.vault.links import LinkResolver, link_text_for, parse_links, rewrite_links


def test_parse_link_forms() -> None:
    text = "See [[Pricing]], [[notes/churn#Reasons|why]], ![[chart.png]] and [[Plan#Annual]] and [[#Local]]."
    links = parse_links(text)
    assert [(link.target, link.heading, link.alias, link.embed) for link in links] == [
        ("Pricing", None, None, False),
        ("notes/churn", "Reasons", "why", False),
        ("chart.png", None, None, True),
        ("Plan", "Annual", None, False),
        ("", "Local", None, False),
    ]
    first = links[0]
    assert text[first.start : first.end] == "[[Pricing]]"


def test_links_in_code_are_ignored() -> None:
    text = "Real [[A]].\n```\n[[NotALink]]\n```\nInline `[[Nope]]` and [[B|b]].\n~~~python\n[[Also]]\n~~~\n"
    assert [link.target for link in parse_links(text)] == ["A", "B"]


def test_resolver_by_name_path_alias_and_ambiguity() -> None:
    paths = ["notes/pricing.md", "profile/company.md", "notes/plan.md", "journal/plan.md", "sources/deck.pdf"]
    resolver = LinkResolver(paths, {"profile/company.md": ["Northwind", "NWA"]})
    assert resolver.resolve("Pricing") == "notes/pricing.md"  # case-insensitive stem
    assert resolver.resolve("pricing.md") == "notes/pricing.md"
    assert resolver.resolve("notes/pricing") == "notes/pricing.md"
    assert resolver.resolve("northwind") == "profile/company.md"
    assert resolver.resolve("deck.pdf") == "sources/deck.pdf"
    assert resolver.resolve("deck") is None  # non-Markdown files need their suffix
    assert resolver.resolve("missing") is None
    # Two notes named "plan": the one in the linking note's folder wins.
    assert resolver.resolve("plan", source="journal/today.md") == "journal/plan.md"
    assert resolver.resolve("plan", source="notes/x.md") == "notes/plan.md"
    assert resolver.resolve("journal/plan") == "journal/plan.md"
    assert resolver.resolve("", source="notes/x.md") == "notes/x.md"
    assert link_text_for("notes/pricing.md", resolver) == "pricing"
    assert link_text_for("notes/plan.md", resolver) == "notes/plan"


def test_rewrite_keeps_heading_alias_and_embed() -> None:
    text = "[[old]] [[Old#H|label]] ![[old]] [[other]] `[[old]]`"
    new, count = rewrite_links(text, lambda link: link.target.lower() == "old", "new-name")
    assert count == 3
    assert new == "[[new-name]] [[new-name#H|label]] ![[new-name]] [[other]] `[[old]]`"
