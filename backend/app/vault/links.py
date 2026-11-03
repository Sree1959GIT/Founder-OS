"""Obsidian-style `[[wikilinks]]`: parsing, resolution to vault paths, and rename-safe rewriting.

Supported forms: `[[Note]]`, `[[Note|alias]]`, `[[Note#Heading]]`, `[[Note#Heading|alias]]`, `[[folder/Note]]`,
`[[report.pdf]]` and embeds (`![[...]]`). Links inside fenced code blocks and inline code are ignored, as in Obsidian.

Resolution (case-insensitive, like Obsidian): a target containing `/` matches a vault path (without `.md`, or a
path suffix); otherwise it matches a file name stem (Markdown) or full file name (other files), then a frontmatter
alias. When several notes share a name, the one in the linking note's folder wins, then the shortest path.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
_FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
MARKDOWN_SUFFIXES = (".md", ".markdown")


@dataclass(frozen=True)
class WikiLink:
    """One link occurrence. `start`/`end` index the original text (the whole `[[...]]`)."""

    target: str
    heading: str | None
    alias: str | None
    embed: bool
    start: int
    end: int

    def render(self, target: str) -> str:
        inner = target
        if self.heading is not None:
            inner += f"#{self.heading}"
        if self.alias is not None:
            inner += f"|{self.alias}"
        return inner


def _mask_code(text: str) -> str:
    """Replace fenced code blocks and inline code with spaces (same length), so offsets stay valid."""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        match = _FENCE_RE.match(line)
        if fence is None and match:
            fence = match.group(2)[0] * len(match.group(2))
            out.append(re.sub(r"[^\n]", " ", line))
            continue
        if fence is not None:
            if match and match.group(2).startswith(fence):
                fence = None
            out.append(re.sub(r"[^\n]", " ", line))
            continue
        out.append(_INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line))
    return "".join(out)


def parse_links(text: str) -> list[WikiLink]:
    """Every wikilink outside code, in document order."""
    links: list[WikiLink] = []
    for match in WIKILINK_RE.finditer(_mask_code(text)):
        inner = text[match.start(2) : match.end(2)]
        target_part, _, alias = inner.partition("|")
        target, _, heading = target_part.partition("#")
        target = target.strip()
        if not target and not heading:
            continue
        links.append(
            WikiLink(
                target=target,
                heading=heading.strip() if "#" in target_part else None,
                alias=alias if "|" in inner else None,
                embed=bool(match.group(1)),
                start=match.start(),
                end=match.end(),
            )
        )
    return links


def _norm(value: str) -> str:
    value = value.strip().replace("\\", "/").strip("/").lower()
    for suffix in MARKDOWN_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def link_key(path: str) -> str:
    """How a vault path is addressed in a link: Markdown without its suffix, other files with it."""
    return _norm(path)


class LinkResolver:
    """Maps link targets to vault paths (POSIX, relative to the vault root)."""

    def __init__(self, paths: Iterable[str], aliases: dict[str, list[str]] | None = None) -> None:
        self._by_key: dict[str, str] = {}
        self._by_name: dict[str, list[str]] = {}
        self._by_alias: dict[str, list[str]] = {}
        for path in sorted(paths):
            key = link_key(path)
            self._by_key[key] = path
            self._by_name.setdefault(key.rsplit("/", 1)[-1], []).append(path)
        for path, names in (aliases or {}).items():
            for alias in names:
                self._by_alias.setdefault(_norm(alias), []).append(path)

    @staticmethod
    def _pick(candidates: list[str], source: str | None) -> str:
        if len(candidates) > 1 and source is not None:
            folder = str(PurePosixPath(source).parent)
            same = [c for c in candidates if str(PurePosixPath(c).parent) == folder]
            if same:
                candidates = same
        return sorted(candidates, key=lambda c: (c.count("/"), len(c), c))[0]

    def resolve(self, target: str, source: str | None = None) -> str | None:
        """The vault path a link target points to, or None when it is unresolved."""
        key = _norm(target)
        if not key:
            return source  # `[[#Heading]]` links to the note itself
        if "/" in key:
            if key in self._by_key:
                return self._by_key[key]
            suffix_hits = [p for k, p in self._by_key.items() if k.endswith("/" + key)]
            return self._pick(suffix_hits, source) if suffix_hits else None
        if key in self._by_name:
            return self._pick(self._by_name[key], source)
        if key in self._by_alias:
            return self._pick(self._by_alias[key], source)
        return None

    def is_unique_name(self, path: str) -> bool:
        return len(self._by_name.get(link_key(path).rsplit("/", 1)[-1], [])) <= 1


def rewrite_links(text: str, replacement: Callable[[WikiLink], str | None]) -> tuple[str, int]:
    """Give each link the target `replacement(link)` returns (None = leave it), keeping heading and alias.

    Returns (text, number of links changed).
    """
    pieces: list[str] = []
    last = 0
    count = 0
    for link in parse_links(text):
        new_target = replacement(link) if link.target else None
        if new_target is None:
            continue
        pieces.append(text[last : link.start])
        pieces.append(f"{'!' if link.embed else ''}[[{link.render(new_target)}]]")
        last = link.end
        count += 1
    pieces.append(text[last:])
    return "".join(pieces), count


def link_text_for(path: str, resolver: LinkResolver, source: str | None = None) -> str:
    """The shortest link target that resolves to `path` from `source`: the bare name if that works, else the path."""
    name = PurePosixPath(path).name
    for suffix in MARKDOWN_SUFFIXES:
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    if resolver.is_unique_name(path) and resolver.resolve(name, source) == path:
        return name
    full = path
    for suffix in MARKDOWN_SUFFIXES:
        if full.lower().endswith(suffix):
            return full[: -len(suffix)]
    return full
