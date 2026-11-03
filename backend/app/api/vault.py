"""`/api/vault/*`: browse, write, rename and upload vault files; link graph; index status. `/api/search`: hybrid RAG."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, model_validator

from app.api.data import CHUNK_BYTES, safe_file_name
from app.deps import SettingsDep, VaultDep
from app.vault.parsers import SUPPORTED_SUFFIXES

router = APIRouter(tags=["vault"])


class NoteWrite(BaseModel):
    """Either the full file `content`, or `frontmatter` + `body` (rendered as YAML frontmatter)."""

    content: str | None = None
    frontmatter: dict[str, Any] | None = None
    body: str | None = None
    create_only: bool = Field(False, description="Fail with 409 when the file already exists")

    @model_validator(mode="after")
    def _one_form(self) -> NoteWrite:
        if self.content is None and self.body is None and self.frontmatter is None:
            raise ValueError("send `content`, or `frontmatter` and/or `body`")
        if self.content is not None and (self.body is not None or self.frontmatter is not None):
            raise ValueError("send either `content` or `frontmatter`/`body`, not both")
        return self


class RenameRequest(BaseModel):
    from_path: str = Field(min_length=1)
    to_path: str = Field(min_length=1)


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=50)
    mode: Literal["hybrid", "bm25", "dense"] = "hybrid"
    folder: str | None = None


def _status(vault: VaultDep) -> dict[str, Any]:
    return {
        "root": str(vault.vault.root),
        "workspace_id": vault.workspace_id,
        "watching": vault.watching,
        "store_note": vault.store_note,
        **vault.index.status(),
    }


@router.get("/vault/status")
def status(vault: VaultDep) -> dict[str, Any]:
    """Index size, embedder / vector store in use, whether semantic search works, files that failed to parse."""
    return _status(vault)


@router.get("/vault/notes")
def list_notes(vault: VaultDep, folder: str | None = None) -> dict[str, Any]:
    items = vault.vault.list_files()
    if folder:
        prefix = folder.strip("/") + "/"
        items = [i for i in items if i["path"].startswith(prefix)]
    return {"notes": items, "count": len(items)}


@router.get("/vault/notes/{path:path}")
def read_note(path: str, vault: VaultDep) -> dict[str, Any]:
    """Content, frontmatter, outgoing links (with the path each resolves to) and backlinks."""
    return vault.vault.read_note(path)


@router.put("/vault/notes/{path:path}")
def write_note(path: str, note: NoteWrite, vault: VaultDep) -> dict[str, Any]:
    """Create or replace a `.md`/`.txt` note; the index and link graph are updated before this returns."""
    rel = vault.vault.write_note(
        path, note.content, frontmatter=note.frontmatter, body=note.body, create_only=note.create_only
    )
    vault.apply_changes({rel})
    return vault.vault.read_note(rel)


@router.delete("/vault/notes/{path:path}")
def delete_note(path: str, vault: VaultDep) -> dict[str, Any]:
    rel = vault.vault.delete(path)
    vault.apply_changes({rel})
    return {"deleted": rel}


@router.post("/vault/rename")
def rename(request: RenameRequest, vault: VaultDep) -> dict[str, Any]:
    """Move/rename a file and rewrite every `[[link]]` to it (headings and aliases are kept)."""
    result = vault.vault.rename(request.from_path, request.to_path)
    vault.apply_changes({result.from_path, result.to_path, *result.updated_files})
    return {
        "from_path": result.from_path,
        "to_path": result.to_path,
        "updated_files": result.updated_files,
        "links_rewritten": result.links_rewritten,
    }


@router.post("/vault/upload")
def upload(
    settings: SettingsDep,
    vault: VaultDep,
    file: Annotated[UploadFile, File(description="PDF, CSV, XLSX, MD or TXT")],
    folder: Annotated[str, Form()] = "sources",
) -> dict[str, Any]:
    """Store a document in the vault (default folder `sources/`) and index it."""
    name = safe_file_name(file.filename or "upload")
    if not any(name.lower().endswith(s) for s in SUPPORTED_SUFFIXES):
        raise HTTPException(415, f"unsupported file type; use one of {sorted(SUPPORTED_SUFFIXES)}")
    limit = settings.max_upload_mb * 1024 * 1024
    data = bytearray()
    while chunk := file.file.read(CHUNK_BYTES):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, f"file is larger than {settings.max_upload_mb} MB")
    rel = vault.vault.save_upload(f"{folder.strip('/')}/{name}" if folder.strip("/") else name, bytes(data))
    vault.apply_changes({rel})
    indexed = vault.index.status()
    return {"path": rel, "size": len(data), "error": indexed["errors"].get(rel)}


@router.get("/vault/links")
def links(vault: VaultDep) -> dict[str, Any]:
    """The link graph (also written to `.index/links.json`): outgoing links, backlinks and unresolved targets."""
    graph = vault.vault.graph
    return {
        "notes": {p: {"title": n.title, "aliases": n.aliases, "tags": n.tags} for p, n in sorted(graph.notes.items())},
        "outgoing": graph.outgoing,
        "backlinks": graph.backlinks,
        "unresolved": graph.unresolved,
    }


@router.post("/vault/reindex")
def reindex(vault: VaultDep, full: bool = False) -> dict[str, Any]:
    """Rescan the vault (normally not needed: the watcher does this). `full=true` re-parses every file."""
    vault.index.refresh(full=full)
    return _status(vault)


@router.get("/search")
def search(
    vault: VaultDep,
    q: Annotated[str, Query(min_length=1, max_length=2000)],
    k: Annotated[int, Query(ge=1, le=50)] = 5,
    mode: Literal["hybrid", "bm25", "dense"] = "hybrid",
    folder: str | None = None,
) -> dict[str, Any]:
    """Hybrid search (BM25 + vectors, RRF k=60). Returns parent chunks with citations `{path, heading, chunk_id}`."""
    return vault.index.search(q, k=k, mode=mode, folder=folder)


@router.post("/search")
def search_post(request: SearchRequest, vault: VaultDep) -> dict[str, Any]:
    return vault.index.search(request.q, k=request.k, mode=request.mode, folder=request.folder)
