"""Reset a workspace to the clean Northwind demo: the shipped sample notes and the sample financials, nothing else.

    python scripts/reset_demo.py            back up and reset the "default" workspace (asks first)
    python scripts/reset_demo.py --yes      no question (for scripts)
    python scripts/reset_demo.py --workspace acme

What it does, with FounderOS closed:
1. Moves `vault/<workspace>/` and `data/<workspace>/` into `data/backups/reset-<UTC time>/`. Nothing is deleted:
   test memos (such as `decisions/2026-11-06-open-dubai-office.md`), uploads, the DuckDB file, the decision and LLM
   logs and the calibration store all go there, and can be copied back by hand.
2. Copies the shipped sample notes (`sample_data/vault/`) into a fresh `vault/<workspace>/`.
3. Keeps your Settings (`ui_settings.json`) unless `--settings` is given.
The next start loads the Northwind financials into the empty DuckDB file (`AUTO_LOAD_SAMPLE_DATA=true`, the default)
and re-indexes the vault; stale search vectors in Qdrant are removed by that re-index. Models, Qdrant's own storage
and `.env` are never touched.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402

SETTINGS_FILE = "ui_settings.json"


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def reset(settings: Settings, workspace: str, keep_settings: bool = True, now: datetime | None = None) -> Path:
    """Back up and reset one workspace. Returns the backup folder."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    vault = settings.workspace_vault_dir(workspace)
    data = settings.workspace_data_dir(workspace)
    backup = settings.workspace_data_dir(workspace).parent / "backups" / f"reset-{stamp}-{workspace}"
    backup.mkdir(parents=True, exist_ok=False)
    kept: bytes | None = None
    if keep_settings and (data / SETTINGS_FILE).is_file():
        kept = (data / SETTINGS_FILE).read_bytes()
    if vault.exists():
        shutil.move(str(vault), str(backup / "vault"))
    if data.exists():
        shutil.move(str(data), str(backup / "data"))
    source = settings.sample_data_path() / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for path in sorted(source.rglob("*")):
            if path.is_file():
                target = vault / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    data.mkdir(parents=True, exist_ok=True)
    if kept is not None:
        (data / SETTINGS_FILE).write_bytes(kept)
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", default=None, help="workspace id (default: WORKSPACE_ID, normally 'default')")
    parser.add_argument("--yes", action="store_true", help="do not ask")
    parser.add_argument("--settings", action="store_true", help="also reset Settings (ui_settings.json)")
    parser.add_argument("--port", type=int, default=8000, help="the backend port to check (default 8000)")
    args = parser.parse_args()
    settings = Settings()
    workspace = args.workspace or settings.workspace_id
    if port_in_use(args.port):
        print(f"[ERROR] Something is listening on port {args.port}: FounderOS is probably running.")
        print("        Close the FounderOS backend and frontend windows, then run this again.")
        return 1
    print(f"This resets workspace '{workspace}' to the Northwind demo:")
    print(f"  vault: {settings.workspace_vault_dir(workspace)}")
    print(f"  data:  {settings.workspace_data_dir(workspace)}")
    print("  Both are moved to data/backups/ first; nothing is deleted.")
    if not args.yes and input("Go ahead? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 0
    try:
        backup = reset(settings, workspace, keep_settings=not args.settings)
    except OSError as exc:
        print(f"[ERROR] {exc}")
        print("        Is a file still open (Obsidian, Excel, an editor)? Close it and run this again.")
        return 1
    print(f"Done. Your old vault and data are in {backup}")
    if not settings.auto_load_sample_data:
        print("[WARN] AUTO_LOAD_SAMPLE_DATA is false: load the financials with Data > Load sample after the start.")
    print("Start FounderOS with run.bat: the Northwind data loads on the first start.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
