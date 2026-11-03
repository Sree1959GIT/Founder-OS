from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.vault.parsers import (
    ParseError,
    as_str_list,
    markdown_sections,
    parse_file,
    render_frontmatter,
    split_frontmatter,
)


def make_pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page (correct xref offsets)."""
    objects: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font_id = 3 + 2 * n
    for i, text in enumerate(pages):
        content_id = 4 + 2 * i
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def test_frontmatter_roundtrip_and_errors() -> None:
    fm, body, error = split_frontmatter("---\ntitle: X\ndate: 2026-09-15\ntags: [a, b]\n---\n# Body\n")
    assert fm == {"title": "X", "date": "2026-09-15", "tags": ["a", "b"]}
    assert body == "# Body\n" and error is None
    fm, body, error = split_frontmatter("---\ntitle: [unclosed\n---\ntext")
    assert fm == {} and body.startswith("---") and error and "invalid YAML" in error
    assert split_frontmatter("---\n- a\n- b\n---\nx")[2] == "frontmatter is not a key/value mapping"
    assert split_frontmatter("no frontmatter")[0] == {}
    rendered = render_frontmatter({"title": "Ünïcode", "aliases": ["A"]}, "body\n")
    assert split_frontmatter(rendered)[:2] == ({"title": "Ünïcode", "aliases": ["A"]}, "body\n")
    assert as_str_list("a, b") == ["a", "b"] and as_str_list(["x", 2]) == ["x", "2"] and as_str_list(None) == []


def test_markdown_sections_heading_paths_and_code_fences() -> None:
    body = "intro\n# Top\ntext\n## Sub\nmore\n```\n# not a heading\n```\n# Next\nend\n"
    sections, h1 = markdown_sections(body)
    assert h1 == "Top"
    assert [s.heading for s in sections] == ["", "Top", "Top > Sub", "Next"]
    assert "# not a heading" in sections[2].text


def test_parse_markdown_txt_csv_xlsx_pdf(tmp_path: Path) -> None:
    md = tmp_path / "n.md"
    md.write_text("---\ntitle: Custom\n---\n# Heading\nBody", encoding="utf-8")
    doc = parse_file(md)
    assert doc.kind == "markdown" and doc.title == "Custom" and doc.sections[0].heading == "Heading"

    txt = tmp_path / "legacy.txt"
    txt.write_bytes("Caf\xe9 notes".encode("cp1252"))  # Notepad "ANSI"
    assert parse_file(txt).sections[0].text == "Café notes"

    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("name,price\nA,100\nB,250.5\n", encoding="utf-8")
    text = parse_file(csv_path).sections[0].text
    assert "Sheet prices: 2 rows, 2 columns: name, price." in text
    assert "Column price: numeric, min 100, max 250.5." in text
    assert "Row 3: name=B; price=250.5" in text

    wb = Workbook()
    ws = wb.active
    ws.title = "Plans"
    ws.append(["plan", "seats"])
    ws.append(["Growth", 10])
    xlsx = tmp_path / "plans.xlsx"
    wb.save(xlsx)
    sections = parse_file(xlsx).sections
    assert sections[0].heading == "Sheet Plans" and "Row 2: plan=Growth; seats=10" in sections[0].text

    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(make_pdf(["Runway is ten months", "Annual prepayment idea"]))
    parsed = parse_file(pdf)
    assert [s.heading for s in parsed.sections] == ["Page 1", "Page 2"]
    assert "Annual prepayment" in parsed.sections[1].text


def test_parse_errors(tmp_path: Path) -> None:
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"not a pdf")
    with pytest.raises(ParseError):
        parse_file(bad_pdf)
    bad_xlsx = tmp_path / "bad.xlsx"
    bad_xlsx.write_bytes(b"nope")
    with pytest.raises(ParseError):
        parse_file(bad_xlsx)
    with pytest.raises(ParseError):
        parse_file(tmp_path / "x.docx")
    with pytest.raises(ParseError):
        parse_file(tmp_path / "missing.md")
