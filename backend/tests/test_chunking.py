from __future__ import annotations

from app.engine.chunking import ApproxTokenizer, chunk_document, get_tokenizer
from app.vault.parsers import Section

TOK = ApproxTokenizer()


def para(word: str, n: int) -> str:
    return " ".join(f"{word}{i}." if i % 12 == 11 else f"{word}{i}" for i in range(n))


def test_small_doc_is_one_parent_one_child() -> None:
    parents = chunk_document("notes/a.md", "A", [Section("Intro", "Hello world.")], TOK)
    assert len(parents) == 1 and len(parents[0].children) == 1
    child = parents[0].children[0]
    assert parents[0].id == "notes/a.md#p0" and child.id == "notes/a.md#p0.c0"
    assert child.parent_id == parents[0].id and child.heading == "Intro"
    assert child.embed_text == "A > Intro\nHello world."


def test_sizes_are_bounded_and_text_is_preserved() -> None:
    sections = [Section(f"S{i}", "\n\n".join(para(f"w{i}x", 150) for _ in range(4))) for i in range(5)]
    parents = chunk_document("notes/big.md", "Big", sections, TOK, parent_tokens=1000, child_tokens=250)
    assert len(parents) > 1
    for parent in parents:
        assert parent.tokens <= 1000
        assert all(child.tokens <= 250 for child in parent.children)
        assert all(child.parent_id == parent.id for child in parent.children)
    original = sum(TOK.count(s.text) for s in sections)
    assert abs(sum(p.tokens for p in parents) - original) <= original * 0.02
    # Every child heading comes from its own section.
    assert {c.heading for p in parents for c in p.children} == {f"S{i}" for i in range(5)}


def test_long_unbroken_text_and_table_rows_are_split() -> None:
    giant = " ".join(f"token{i}" for i in range(3000))  # no sentence ends, no newlines
    parents = chunk_document("x.txt", "x", [Section("", giant)], TOK, child_tokens=250)
    assert all(c.tokens <= 250 for p in parents for c in p.children)
    rows = "\n".join(f"Row {i}: a={i}; b=value{i}" for i in range(400))  # CSV summary: one paragraph of lines
    parents = chunk_document("t.csv", "t", [Section("Sheet t", rows)], TOK)
    children = [c for p in parents for c in p.children]
    assert len(children) > 5 and all(c.tokens <= 250 for c in children)
    assert children[0].text.startswith("Row 0:")  # split at line breaks, not mid-row


def test_ids_and_hashes_are_stable() -> None:
    sections = [Section("H", para("w", 600))]
    first = chunk_document("p.md", "P", sections, TOK)
    second = chunk_document("p.md", "P", sections, TOK)
    assert [c.content_hash for p in first for c in p.children] == [c.content_hash for p in second for c in p.children]
    changed = chunk_document("p.md", "P", [Section("H", para("w", 600) + " extra")], TOK)
    assert first[0].children[0].content_hash == changed[0].children[0].content_hash
    assert first[-1].children[-1].content_hash != changed[-1].children[-1].content_hash


def test_get_tokenizer_approx_and_fallback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assert get_tokenizer("approx").name == "approx"
    import app.engine.chunking as chunking

    def boom(self) -> None:  # type: ignore[no-untyped-def]
        raise OSError("offline")

    monkeypatch.setattr(chunking.TiktokenTokenizer, "__init__", boom)
    assert get_tokenizer("tiktoken").name == "approx"
    assert TOK.count("Hello, world") == 5  # Hello (2) + "," (1) + world (2)


def test_children_do_not_cross_headings_but_parents_pack_sections() -> None:
    sections = [Section("Doc", "Intro."), Section("Doc > Pricing", "Price text."), Section("Doc > Churn", "Churn.")]
    parents = chunk_document("n.md", "N", sections, TOK)
    assert len(parents) == 1
    assert [c.heading for c in parents[0].children] == ["Doc", "Doc > Pricing", "Doc > Churn"]
    assert parents[0].text == "Intro.\n\nPrice text.\n\nChurn."
