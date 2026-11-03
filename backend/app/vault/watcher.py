"""Re-index the vault when files change on disk (Obsidian, Notepad, Explorer), using watchfiles.

Changes are debounced (~0.4 s) and handed to `VaultService.apply_changes` in a worker thread, so the event loop
never blocks on parsing or embedding. Hidden paths (`.index`, `.obsidian`, temp files) are ignored.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from loguru import logger
from watchfiles import Change, awatch

DEBOUNCE_MS = 400


def make_filter(root: Path) -> Callable[[Change, str], bool]:
    root_str = str(root)

    def keep(_: Change, path: str) -> bool:
        try:
            rel = os.path.relpath(path, root_str)
        except ValueError:  # another drive on Windows
            return False
        parts = Path(rel).parts
        if not parts or parts[0] == "..":
            return False
        name = parts[-1]
        return not any(p.startswith((".", "~$")) for p in parts) and not name.endswith((".tmp", ".swp", "~"))

    return keep


def changed_paths(root: Path, changes: set[tuple[Change, str]]) -> set[str]:
    """Vault-relative POSIX paths for a batch of watchfiles changes."""
    rels: set[str] = set()
    for change, path in changes:
        if change == Change.modified and os.path.isdir(path):
            continue  # Windows reports the parent folder on every save; the file event is enough
        try:
            rels.add(Path(os.path.relpath(path, root)).as_posix())
        except ValueError:
            continue
    return rels


async def watch_vault(
    root: Path, on_change: Callable[[set[str]], object], stop_event: asyncio.Event, force_polling: bool = False
) -> None:
    """Run until `stop_event` is set. `on_change` runs in a thread with the changed vault-relative paths."""
    logger.info("Watching vault {} for changes", root)
    try:
        async for changes in awatch(
            root,
            watch_filter=make_filter(root),
            stop_event=stop_event,
            debounce=DEBOUNCE_MS,
            step=50,
            force_polling=force_polling,
        ):
            rels = changed_paths(root, changes)
            if rels:
                logger.debug("Vault changed: {}", sorted(rels))
                try:
                    await asyncio.to_thread(on_change, rels)
                except Exception as exc:  # keep watching even if one re-index fails
                    logger.exception("Vault re-index failed: {}", exc)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # e.g. the vault folder was deleted: search still works on the last index
        logger.error("Vault watcher stopped: {}", exc)
