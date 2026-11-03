"""Parent-child chunking for retrieval (PRD F2).

Children (~250 tokens) are what we embed and score: they are small enough to match a specific question. Parents
(~1000 tokens) are what we return, because they carry enough context to answer it. Every child knows its parent.

Splitting respects structure: text is cut into blocks at blank lines (paragraphs, list groups, table rows), blocks
that are still too big are cut at sentence ends and finally at word boundaries. Blocks never cross a section
(heading), so each child has exactly one heading for its citation; small sections are packed together into one parent.

Token counts use tiktoken `cl100k_base` (an approximation of the embedding model's tokenizer, as the PRD says).
tiktoken downloads its vocabulary on first use, so when it is unavailable (offline first run, tests) we fall back to
`ApproxTokenizer`, a deterministic regex estimate. Chunk boundaries can then differ slightly; nothing else changes.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from dataclasses import dataclass, field
from typing import Protocol

from loguru import logger

from app.vault.parsers import Section

PARENT_TOKENS = 1000
CHILD_TOKENS = 250
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[A-Z0-9#*-])")
_LINE_RE = re.compile(r"\n+")
_APPROX_PIECE_RE = re.compile(r"\w+|[^\w\s]")


class Tokenizer(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class ApproxTokenizer:
    """~cl100k: one token per punctuation mark, one per 4 characters of each word (minimum one)."""

    name = "approx"

    def count(self, text: str) -> int:
        return sum(max(1, math.ceil(len(piece) / 4)) for piece in _APPROX_PIECE_RE.findall(text))


class TiktokenTokenizer:
    name = "tiktoken:cl100k_base"

    def __init__(self) -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))


def get_tokenizer(kind: str = "tiktoken") -> Tokenizer:
    """`tiktoken` (falls back to `approx` when the vocabulary cannot be loaded) or `approx`."""
    if kind == "approx":
        return ApproxTokenizer()
    try:
        return TiktokenTokenizer()
    except Exception as exc:  # no network on first use, missing package, corrupt cache...
        logger.warning("tiktoken unavailable ({}); using the approximate token counter", type(exc).__name__)
        return ApproxTokenizer()


@dataclass
class ChildChunk:
    id: str
    parent_id: str
    path: str
    heading: str
    text: str
    tokens: int
    embed_text: str  # title + heading + text: what the embedding model sees
    content_hash: str


@dataclass
class ParentChunk:
    id: str
    path: str
    heading: str
    text: str
    tokens: int
    children: list[ChildChunk] = field(default_factory=list)


@dataclass
class _Block:
    heading: str
    text: str
    tokens: int


def _pack_strings(pieces: list[tuple[str, int]], limit: int, sep: str) -> list[str]:
    """Join consecutive (text, tokens) pieces while the (additive) token estimate stays within `limit`."""
    out: list[str] = []
    current: list[str] = []
    size = 0
    for text, tokens in pieces:
        if current and size + tokens > limit:
            out.append(sep.join(current))
            current, size = [], 0
        current.append(text)
        size += tokens
    if current:
        out.append(sep.join(current))
    return out


def _split_block(text: str, limit: int, tokenizer: Tokenizer) -> list[str]:
    """Cut text that is over `limit` tokens at line breaks, then sentence ends, then word boundaries."""
    if tokenizer.count(text) <= limit:
        return [text]
    for pattern, sep in ((_LINE_RE, "\n"), (_SENTENCE_RE, " ")):
        parts = [part.strip() for part in re.split(pattern, text) if part.strip()]
        if len(parts) > 1:
            pieces = [piece for part in parts for piece in _split_block(part, limit, tokenizer)]
            return _pack_strings([(piece, tokenizer.count(piece)) for piece in pieces], limit, sep)
    words = text.split()
    return _pack_strings([(word, tokenizer.count(word)) for word in words], limit, " ")


def _blocks(sections: list[Section], child_tokens: int, tokenizer: Tokenizer) -> list[_Block]:
    blocks: list[_Block] = []
    for section in sections:
        for paragraph in re.split(r"\n\s*\n", section.text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for piece in _split_block(paragraph, child_tokens, tokenizer):
                blocks.append(_Block(section.heading, piece, tokenizer.count(piece)))
    return blocks


def _pack(blocks: list[_Block], limit: int) -> list[list[_Block]]:
    """Greedy packing in order; a new group starts when the limit would be exceeded."""
    groups: list[list[_Block]] = []
    current: list[_Block] = []
    size = 0
    for block in blocks:
        if current and size + block.tokens > limit:
            groups.append(current)
            current, size = [], 0
        current.append(block)
        size += block.tokens
    if current:
        groups.append(current)
    return groups


def chunk_document(
    path: str,
    title: str,
    sections: list[Section],
    tokenizer: Tokenizer,
    parent_tokens: int = PARENT_TOKENS,
    child_tokens: int = CHILD_TOKENS,
) -> list[ParentChunk]:
    """Parents (with their children) for one document. Ids are stable for unchanged content: `path#p0.c1`."""
    parents: list[ParentChunk] = []
    for p_index, group in enumerate(_pack(_blocks(sections, child_tokens, tokenizer), parent_tokens)):
        parent_id = f"{path}#p{p_index}"
        parent = ParentChunk(
            id=parent_id,
            path=path,
            heading=group[0].heading,
            text="\n\n".join(b.text for b in group),
            tokens=sum(b.tokens for b in group),
        )
        # Children never cross a heading, so every citation names the exact section it came from.
        runs = [list(run) for _, run in itertools.groupby(group, key=lambda b: b.heading)]
        child_groups = [g for run in runs for g in _pack(run, child_tokens)]
        for c_index, child_group in enumerate(child_groups):
            heading = child_group[0].heading
            text = "\n\n".join(b.text for b in child_group)
            context = " > ".join(part for part in (title, heading) if part)
            embed_text = f"{context}\n{text}" if context else text
            parent.children.append(
                ChildChunk(
                    id=f"{parent_id}.c{c_index}",
                    parent_id=parent_id,
                    path=path,
                    heading=heading,
                    text=text,
                    tokens=sum(b.tokens for b in child_group),
                    embed_text=embed_text,
                    content_hash=hashlib.sha256(embed_text.encode("utf-8")).hexdigest()[:16],
                )
            )
        parents.append(parent)
    return parents
