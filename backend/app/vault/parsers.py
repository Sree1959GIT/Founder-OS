"""Turn vault files into text sections for chunking: Markdown/TXT, PDF (pypdf), CSV/XLSX (summary rows).

Every parser returns a `ParsedDocument` whose `sections` carry the heading used in search citations
(`Pricing > Annual plans`, `Page 3`, `Sheet pnl`). Parsers never raise anything but `ParseError`.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
TEXT_SUFFIXES = frozenset({".txt"})
PDF_SUFFIXES = frozenset({".pdf"})
TABLE_SUFFIXES = frozenset({".csv", ".xlsx"})
SUPPORTED_SUFFIXES = MARKDOWN_SUFFIXES | TEXT_SUFFIXES | PDF_SUFFIXES | TABLE_SUFFIXES

MAX_TABLE_ROWS = 200  # rows rendered per sheet; the summary line still counts every row
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FRONTMATTER_END = ("---", "...")


class ParseError(Exception):
    """A file could not be read or parsed."""


@dataclass
class Section:
    heading: str
    text: str


@dataclass
class ParsedDocument:
    kind: str  # markdown | text | pdf | table
    title: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""  # Markdown body (links are parsed from this)
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def jsonable(value: Any) -> Any:
    """YAML values (dates, nested lists) in a JSON-safe form."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [jsonable(v) for v in value]
    if isinstance(value, dt.date | dt.datetime | dt.time):
        return value.isoformat()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM), falling back to Windows-1252 (Notepad's legacy "ANSI")."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, str | None]:
    """(frontmatter, body, error). Invalid YAML keeps the whole text as body and reports the error."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text, None
    for index in range(1, len(lines)):
        if lines[index].strip() in _FRONTMATTER_END:
            raw = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            try:
                loaded = yaml.safe_load(raw) if raw.strip() else {}
            except yaml.YAMLError as exc:
                return {}, text, f"invalid YAML frontmatter: {str(exc).splitlines()[0]}"
            if loaded is None:
                loaded = {}
            if not isinstance(loaded, dict):
                return {}, text, "frontmatter is not a key/value mapping"
            return jsonable(loaded), body, None
    return {}, text, None


def render_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    if not frontmatter:
        return body
    dumped = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---\n{body}"


def as_str_list(value: Any) -> list[str]:
    """Frontmatter `aliases`/`tags` may be a string, a comma list or a YAML list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def markdown_sections(body: str) -> tuple[list[Section], str | None]:
    """Split on ATX headings outside code fences. Heading paths read `H1 > H2`. Returns (sections, first H1)."""
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    first_h1: str | None = None
    fence: str | None = None

    def flush() -> None:
        text = "".join(buffer).strip()
        heading = " > ".join(title for _, title in stack)
        if text:
            sections.append(Section(heading=heading, text=text))
        buffer.clear()

    for line in body.splitlines(keepends=True):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker[0] * len(marker)
            elif marker.startswith(fence):
                fence = None
            buffer.append(line)
            continue
        heading_match = _HEADING_RE.match(line.rstrip("\r\n")) if fence is None else None
        if heading_match:
            flush()
            level, title = len(heading_match.group(1)), heading_match.group(2).strip()
            if level == 1 and first_h1 is None:
                first_h1 = title
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            buffer.append(line)  # keep the heading text searchable
            continue
        buffer.append(line)
    flush()
    return sections, first_h1


def parse_markdown(text: str, stem: str) -> ParsedDocument:
    frontmatter, body, error = split_frontmatter(text)
    sections, first_h1 = markdown_sections(body)
    title = str(frontmatter.get("title") or first_h1 or stem)
    return ParsedDocument(
        kind="markdown",
        title=title,
        frontmatter=frontmatter,
        body=body,
        sections=sections,
        warnings=[error] if error else [],
    )


def parse_pdf(data: bytes, stem: str) -> ParsedDocument:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError("the PDF is password-protected")
        pages = [page.extract_text() or "" for page in reader.pages]
        meta_title = (reader.metadata.title if reader.metadata else None) or None
    except ParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ParseError(f"cannot read PDF: {exc}") from exc
    sections = [Section(heading=f"Page {i}", text=t.strip()) for i, t in enumerate(pages, start=1) if t.strip()]
    warnings = [] if sections else ["no extractable text (scanned PDF?)"]
    return ParsedDocument(kind="pdf", title=str(meta_title or stem), sections=sections, warnings=warnings)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime) and value.time() == dt.time():
        return value.date().isoformat()
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: str) -> Decimal | None:
    cleaned = value.replace(",", "").replace("$", "").strip()
    if not cleaned or not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def table_section(name: str, rows: list[list[str]]) -> Section:
    """Summary rows for one sheet: shape, columns, numeric ranges (computed in code), then `col=value` rows."""
    rows = [r for r in rows if any(cell for cell in r)]
    if not rows:
        return Section(heading=f"Sheet {name}", text=f"Sheet {name}: empty")
    header = [h or f"column_{i + 1}" for i, h in enumerate(rows[0])]
    data = rows[1:]
    lines = [f"Sheet {name}: {len(data)} rows, {len(header)} columns: {', '.join(header)}."]
    for index, column in enumerate(header):
        values = [_number(r[index]) for r in data if index < len(r) and r[index]]
        numbers = [v for v in values if v is not None]
        if numbers and len(numbers) == len(values):
            lines.append(f"Column {column}: numeric, min {min(numbers)}, max {max(numbers)}.")
    for number, row in enumerate(data[:MAX_TABLE_ROWS], start=2):
        pairs = [f"{header[i]}={cell}" for i, cell in enumerate(row) if i < len(header) and cell]
        lines.append(f"Row {number}: " + "; ".join(pairs))
    if len(data) > MAX_TABLE_ROWS:
        lines.append(f"(+{len(data) - MAX_TABLE_ROWS} more rows not shown)")
    return Section(heading=f"Sheet {name}", text="\n".join(lines))


def parse_csv(data: bytes, stem: str) -> ParsedDocument:
    text = decode_text(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]
    return ParsedDocument(kind="table", title=stem, sections=[table_section(stem, rows)])


def parse_xlsx(data: bytes, stem: str) -> ParsedDocument:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for corrupt files
        raise ParseError(f"cannot read XLSX: {exc}") from exc
    try:
        sections = [
            table_section(sheet.title, [[_cell(v) for v in row] for row in sheet.iter_rows(values_only=True)])
            for sheet in workbook.worksheets
        ]
    finally:
        workbook.close()
    return ParsedDocument(kind="table", title=stem, sections=sections)


def parse_file(path: Path) -> ParsedDocument:
    """Parse one vault file by its suffix."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ParseError(f"unsupported file type: {suffix or '(none)'}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ParseError(f"cannot read file: {exc}") from exc
    if suffix in MARKDOWN_SUFFIXES:
        return parse_markdown(decode_text(data), path.stem)
    if suffix in TEXT_SUFFIXES:
        text = decode_text(data)
        return ParsedDocument(
            kind="text", title=path.stem, body=text, sections=[Section(heading="", text=text.strip())]
        )
    if suffix in PDF_SUFFIXES:
        return parse_pdf(data, path.stem)
    if suffix == ".csv":
        return parse_csv(data, path.stem)
    return parse_xlsx(data, path.stem)
