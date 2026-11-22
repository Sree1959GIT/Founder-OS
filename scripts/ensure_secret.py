"""Make sure `.env` has FOUNDEROS_SECRET_KEY, the Fernet key that encrypts members' API keys (M7a).

Run by setup.bat / setup.sh and run.bat. Idempotent: an existing key is left alone (changing it would make every saved
API key unreadable). The key is never printed: this script only says whether it created one.

    python scripts/ensure_secret.py           # create it when missing
    python scripts/ensure_secret.py --check   # report only (exit 1 when missing)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
NAME = "FOUNDEROS_SECRET_KEY"
LINE = re.compile(rf"^[ \t]*{NAME}[ \t]*=[ \t]*(\S*)[ \t]*$", re.MULTILINE)


def has_secret(text: str) -> bool:
    match = LINE.search(text)
    return bool(match and match.group(1).strip("\"'"))


def ensure_secret(env_file: Path) -> bool:
    """True when a new key was written. The rest of the file is kept as it was."""
    text = env_file.read_text(encoding="utf-8") if env_file.is_file() else ""
    if has_secret(text):
        return False
    key = Fernet.generate_key().decode("ascii")
    entry = f"{NAME}={key}"
    if LINE.search(text):  # an empty `FOUNDEROS_SECRET_KEY=` line (as in .env.example): fill it in place
        text = LINE.sub(lambda _: entry, text, count=1)
    else:
        text = text + ("" if not text or text.endswith("\n") else "\n") + entry + "\n"
    temporary = env_file.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(env_file)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--check", action="store_true", help="report only")
    args = parser.parse_args(argv)
    present = args.env_file.is_file() and has_secret(args.env_file.read_text(encoding="utf-8"))
    if args.check:
        print(f"[{'OK' if present else 'MISSING'}] {NAME} in {args.env_file.name}")
        return 0 if present else 1
    if ensure_secret(args.env_file):
        print(
            f"[OK] Created {NAME} in {args.env_file.name} (encrypts saved API keys; keep .env private, never share it)"
        )
    else:
        print(f"[OK] {NAME} is set in {args.env_file.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
