"""Where the privacy filter's names come from: the customers table and the vault's people and company notes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.llm.privacy import NameSource

# Frontmatter fields that name someone. Competitors are public, so they are left alone.
PERSON_FIELDS = ("people", "person", "contact", "contacts", "owner", "author", "attendees", "adviser", "advisor")
COMPANY_FIELDS = ("company", "companies", "customer", "customers", "partner", "partners", "investor", "investors")
_PERSON_TAGS = frozenset({"person", "people", "contact"})
_COMPANY_TAGS = frozenset({"company", "customer", "investor", "partner"})


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        return [str(v) for v in value if isinstance(v, str | int)]
    return []


def customer_names(finance: Any) -> Iterable[tuple[str, str]]:
    """A workspace with no customers table has nothing to hide. A broken database raises, and the call stays local."""
    db = getattr(finance, "db", None)
    if db is None or "customers" not in db.tables():
        return []
    with db.connect() as con:
        rows = con.execute("SELECT DISTINCT name FROM customers WHERE name IS NOT NULL").fetchall()
    return [("customer", str(row[0])) for row in rows]


def vault_names(vault: Any) -> Iterable[tuple[str, str]]:
    manager = getattr(vault, "vault", None)
    if manager is None:
        return []
    found: list[tuple[str, str]] = []
    for path in manager.iter_files():
        if not path.endswith(".md"):
            continue
        note = manager.read_note(path)
        front = note.get("frontmatter") or {}
        tags = {str(t).lower() for t in _as_list(front.get("tags"))}
        found += [("person", n) for field in PERSON_FIELDS for n in _as_list(front.get(field))]
        found += [("company", n) for field in COMPANY_FIELDS for n in _as_list(front.get(field))]
        if tags & _PERSON_TAGS:
            found += [("person", n) for n in [note.get("title", ""), *_as_list(front.get("aliases"))]]
        elif tags & _COMPANY_TAGS:
            found += [("company", n) for n in [note.get("title", ""), *_as_list(front.get("aliases"))]]
    return [(kind, name) for kind, name in found if name.strip()]


def name_sources(finance: Any, vault: Any) -> list[NameSource]:
    return [lambda: customer_names(finance), lambda: vault_names(vault)]
