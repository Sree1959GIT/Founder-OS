"""The Markdown vault: `<VAULT_PATH>/<workspace>/` with folders profile/, notes/, decisions/, journal/, sources/.

- Paths in the API are POSIX paths relative to the vault root (`notes/pricing.md`). `resolve()` rejects anything
  that could escape the vault or misbehave on Windows (`..`, absolute or drive paths, hidden segments such as
  `.index`/`.obsidian`, reserved device names like `CON`, and characters Windows forbids).
- The link graph (wikilinks, frontmatter `aliases`, backlinks, unresolved links) lives in `.index/links.json` and is
  rebuilt from the files, so edits made in Obsidian or Notepad are picked up (the watcher calls `refresh_links`).
- `rename()` moves a file and rewrites every `[[link]]` that pointed at it, keeping `#heading` and `|alias` parts.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from loguru import logger

from app.vault.links import LinkResolver, link_text_for, parse_links, rewrite_links
from app.vault.parsers import (
    MARKDOWN_SUFFIXES,
    SUPPORTED_SUFFIXES,
    TEXT_SUFFIXES,
    as_str_list,
    decode_text,
    parse_markdown,
    render_frontmatter,
)

FOLDERS = ("profile", "notes", "decisions", "journal", "sources")
INDEX_DIR_NAME = ".index"
LINKS_FILE_NAME = "links.json"
WRITABLE_SUFFIXES = MARKDOWN_SUFFIXES | TEXT_SUFFIXES
MAX_NOTE_BYTES = 2 * 1024 * 1024
_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(\..*)?$", re.IGNORECASE)
_FORBIDDEN_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


class VaultError(Exception):
    """Base class; maps to HTTP 422."""


class VaultPathError(VaultError):
    """The path is not a safe vault path (HTTP 400)."""


class NoteNotFoundError(VaultError):
    """HTTP 404."""


class NoteExistsError(VaultError):
    """HTTP 409."""


@dataclass
class NoteLinks:
    title: str
    aliases: list[str]
    tags: list[str]
    links: list[dict[str, Any]]  # unresolved form: target / heading / alias / embed


@dataclass
class LinkGraph:
    notes: dict[str, NoteLinks] = field(default_factory=dict)
    outgoing: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # links with `resolved`
    backlinks: dict[str, list[str]] = field(default_factory=dict)
    unresolved: dict[str, list[str]] = field(default_factory=dict)
    resolver: LinkResolver = field(default_factory=lambda: LinkResolver([]))


@dataclass
class RenameResult:
    from_path: str
    to_path: str
    updated_files: list[str]
    links_rewritten: int


def _mtime_iso(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC).isoformat(timespec="seconds")


def atomic_write(path: Path, data: bytes) -> None:
    """Write via a hidden temp file + `os.replace`, so readers (and the watcher) never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class VaultManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[int, int, NoteLinks]] = {}  # path -> (mtime_ns, size, parsed)
        self._graph = LinkGraph()

    # ----------------------------------------------------------------- paths
    @property
    def index_dir(self) -> Path:
        return self.root / INDEX_DIR_NAME

    def ensure_layout(self) -> None:
        for folder in FOLDERS:
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str) -> Path:
        """Absolute path for a vault-relative path, or `VaultPathError`."""
        cleaned = (rel or "").replace("\\", "/").strip()
        if not cleaned or cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned) or len(cleaned) > 400:
            raise VaultPathError(f"not a vault-relative path: {rel!r}")
        parts = cleaned.split("/")
        for part in parts:
            if part in ("", ".", "..") or part.startswith("."):
                raise VaultPathError(f"invalid path segment {part!r} in {rel!r}")
            if _FORBIDDEN_CHARS.search(part) or part.endswith((" ", ".")) or _WINDOWS_RESERVED.match(part):
                raise VaultPathError(f"path segment {part!r} is not allowed on Windows")
        path = self.root.joinpath(*parts)
        if not path.resolve().is_relative_to(self.root):
            raise VaultPathError(f"path escapes the vault: {rel!r}")
        return path

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    @staticmethod
    def is_indexable(rel: str) -> bool:
        parts = rel.split("/")
        return (
            not any(p.startswith(".") or p.startswith("~$") for p in parts)
            and PurePosixPath(rel).suffix.lower() in SUPPORTED_SUFFIXES
        )

    def iter_files(self) -> list[str]:
        """Every supported file (sorted), skipping hidden folders such as `.index`, `.obsidian` and `.trash`."""
        if not self.root.is_dir():
            return []
        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            base = Path(dirpath)
            for name in filenames:
                rel = (base / name).relative_to(self.root).as_posix()
                if self.is_indexable(rel):
                    found.append(rel)
        return sorted(found)

    # ----------------------------------------------------------------- links
    def _note_links(self, rel: str) -> NoteLinks | None:
        path = self.root / rel
        try:
            stat = path.stat()
        except OSError:
            return None
        cached = self._cache.get(rel)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]
        try:
            parsed = parse_markdown(decode_text(path.read_bytes()), path.stem)
        except OSError:
            return None
        info = NoteLinks(
            title=parsed.title,
            aliases=as_str_list(parsed.frontmatter.get("aliases") or parsed.frontmatter.get("alias")),
            tags=as_str_list(parsed.frontmatter.get("tags")),
            links=[
                {"target": link.target, "heading": link.heading, "alias": link.alias, "embed": link.embed}
                for link in parse_links(parsed.body)
            ],
        )
        self._cache[rel] = (stat.st_mtime_ns, stat.st_size, info)
        return info

    def refresh_links(self) -> LinkGraph:
        """Rebuild the link graph from the files and write `.index/links.json`."""
        with self._lock:
            files = self.iter_files()
            notes: dict[str, NoteLinks] = {}
            for rel in files:
                if PurePosixPath(rel).suffix.lower() in MARKDOWN_SUFFIXES:
                    info = self._note_links(rel)
                    if info is not None:
                        notes[rel] = info
            self._cache = {k: v for k, v in self._cache.items() if k in notes}
            resolver = LinkResolver(files, {p: n.aliases for p, n in notes.items()})
            graph = LinkGraph(notes=notes, resolver=resolver)
            for source, info in notes.items():
                resolved_links = []
                for link in info.links:
                    target = resolver.resolve(link["target"], source)
                    resolved_links.append({**link, "resolved": target})
                    if target is None:
                        graph.unresolved.setdefault(link["target"], [])
                        if source not in graph.unresolved[link["target"]]:
                            graph.unresolved[link["target"]].append(source)
                    elif target != source:
                        sources = graph.backlinks.setdefault(target, [])
                        if source not in sources:
                            sources.append(source)
                graph.outgoing[source] = resolved_links
            self._graph = graph
            self._write_links_file(graph)
            return graph

    def _write_links_file(self, graph: LinkGraph) -> None:
        payload = {
            "version": 1,
            "generated_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
            "notes": {
                path: {"title": n.title, "aliases": n.aliases, "tags": n.tags, "links": graph.outgoing.get(path, [])}
                for path, n in sorted(graph.notes.items())
            },
            "backlinks": {k: sorted(v) for k, v in sorted(graph.backlinks.items())},
            "unresolved": {k: sorted(v) for k, v in sorted(graph.unresolved.items())},
        }
        try:
            atomic_write(self.index_dir / LINKS_FILE_NAME, json.dumps(payload, indent=2).encode("utf-8"))
        except OSError as exc:  # the in-memory graph still works (PRD R3)
            logger.error("Cannot write {}: {}", self.index_dir / LINKS_FILE_NAME, exc)

    @property
    def graph(self) -> LinkGraph:
        return self._graph

    # ----------------------------------------------------------------- CRUD
    def list_files(self) -> list[dict[str, Any]]:
        graph = self._graph
        items = []
        for rel in self.iter_files():
            path = self.root / rel
            try:
                size, modified = path.stat().st_size, _mtime_iso(path)
            except OSError:
                continue
            note = graph.notes.get(rel)
            items.append(
                {
                    "path": rel,
                    "title": note.title if note else PurePosixPath(rel).stem,
                    "folder": rel.split("/")[0] if "/" in rel else "",
                    "kind": PurePosixPath(rel).suffix.lower().lstrip("."),
                    "tags": note.tags if note else [],
                    "size": size,
                    "modified": modified,
                    "backlinks": len(graph.backlinks.get(rel, [])),
                }
            )
        return items

    def read_note(self, rel: str) -> dict[str, Any]:
        path = self.resolve(rel)
        if not path.is_file():
            raise NoteNotFoundError(f"no such file in the vault: {rel}")
        rel = self.relative(path)
        graph = self._graph
        result: dict[str, Any] = {
            "path": rel,
            "kind": path.suffix.lower().lstrip("."),
            "size": path.stat().st_size,
            "modified": _mtime_iso(path),
            "backlinks": sorted(graph.backlinks.get(rel, [])),
        }
        if path.suffix.lower() in WRITABLE_SUFFIXES:
            text = decode_text(path.read_bytes())
            parsed = parse_markdown(text, path.stem) if path.suffix.lower() in MARKDOWN_SUFFIXES else None
            result |= {
                "title": parsed.title if parsed else path.stem,
                "content": text,
                "frontmatter": parsed.frontmatter if parsed else {},
                "body": parsed.body if parsed else text,
                "links": graph.outgoing.get(rel, []),
                "warnings": parsed.warnings if parsed else [],
            }
        else:
            result |= {"title": path.stem, "content": None, "frontmatter": {}, "body": None, "links": []}
            result["warnings"] = ["binary file: use /api/search to read its text"]
        return result

    def write_note(
        self,
        rel: str,
        content: str | None = None,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str | None = None,
        create_only: bool = False,
    ) -> str:
        """Create or replace a Markdown/TXT note. Either `content`, or `frontmatter` + `body`."""
        path = self.resolve(rel)
        if path.suffix.lower() not in WRITABLE_SUFFIXES:
            raise VaultError("only .md and .txt notes can be written; upload other files")
        if content is None:
            content = render_frontmatter(frontmatter or {}, body or "")
        data = content.encode("utf-8")
        if len(data) > MAX_NOTE_BYTES:
            raise VaultError(f"note is larger than {MAX_NOTE_BYTES // 1024 // 1024} MB")
        with self._lock:
            if create_only and path.exists():
                raise NoteExistsError(f"already exists: {rel}")
            atomic_write(path, data)
        return self.relative(path)

    def save_upload(self, rel: str, data: bytes) -> str:
        path = self.resolve(rel)
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise VaultError(f"unsupported file type: {path.suffix or '(none)'}")
        with self._lock:
            atomic_write(path, data)
        return self.relative(path)

    def delete(self, rel: str) -> str:
        path = self.resolve(rel)
        with self._lock:
            if not path.is_file():
                raise NoteNotFoundError(f"no such file in the vault: {rel}")
            rel = self.relative(path)
            path.unlink()
        return rel

    def rename(self, src: str, dst: str) -> RenameResult:
        """Move a file and rewrite the links that pointed at it, in every Markdown note."""
        source, target = self.resolve(src), self.resolve(dst)
        if source.suffix.lower() != target.suffix.lower():
            raise VaultError("a rename must keep the file type (same suffix)")
        with self._lock:
            if not source.is_file():
                raise NoteNotFoundError(f"no such file in the vault: {src}")
            same_file = source.resolve() == target.resolve()  # case-only rename on Windows
            if target.exists() and not same_file:
                raise NoteExistsError(f"already exists: {dst}")
            old_graph = self.refresh_links()
            src_rel = self.relative(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            dst_rel = self.relative(target)
            new_graph = self.refresh_links()
            new_name = link_text_for(dst_rel, new_graph.resolver)
            updated: list[str] = []
            total = 0
            for rel in list(new_graph.notes):
                old_rel = src_rel if rel == dst_rel else rel

                def points_at_old(link: Any, _new: str = rel, _old: str = old_rel) -> bool:
                    was = old_graph.resolver.resolve(link.target, _old) == src_rel
                    still = new_graph.resolver.resolve(link.target, _new) == dst_rel
                    return was and not still

                path = self.root / rel
                text = decode_text(path.read_bytes())
                rewritten, count = rewrite_links(text, points_at_old, new_name)
                if count:
                    atomic_write(path, rewritten.encode("utf-8"))
                    updated.append(rel)
                    total += count
            if updated:
                self.refresh_links()
        return RenameResult(from_path=src_rel, to_path=dst_rel, updated_files=updated, links_rewritten=total)
