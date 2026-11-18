"""What FounderOS can use on this PC, in plain words. `run.bat` and `setup.bat` call it; it never stops them.

    python scripts/preflight.py

Checks Ollama at `OLLAMA_BASE_URL` (and that the configured models are pulled), Qdrant at `QDRANT_HOST:QDRANT_PORT`,
and the voice models in `<DATA_DIR>/models`. Each line is OK, or MISSING with what to do. FounderOS starts either way:
without Ollama agents answer from rules, without Qdrant search is keyword-only, without the voice models voice is off.
Exit code 0 always, unless `--strict` (then 1 when something is missing).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402


def _download_models() -> Any:
    spec = importlib.util.spec_from_file_location("download_models", ROOT / "scripts" / "download_models.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_ollama(settings: Settings, dm: Any) -> list[str]:
    base = settings.ollama_base_url.rstrip("/")
    try:
        version = httpx.get(f"{base}/api/version", timeout=5).json().get("version", "?")
    except (httpx.HTTPError, ValueError):
        return [
            f"[MISSING] Ollama is not answering at {base}.",
            "          Start the Ollama app or its Docker container (docker start ollama), or set OLLAMA_BASE_URL in",
            "          .env. Without it, agents answer from rules only.",
        ]
    pulled = dm.pulled_models(base) or set()
    lines = [f"[OK]      Ollama {version} at {base}"]
    missing = [n for n in dm.ollama_models(settings) if not dm._has(pulled, n)]
    if missing:
        lines.append(f"[MISSING] Ollama models not pulled: {', '.join(missing)}.")
        lines.append("          Run: .venv\\Scripts\\python.exe scripts\\download_models.py --no-voice")
    return lines


def check_qdrant(settings: Settings) -> list[str]:
    if settings.vector_store == "memory":
        return ["[OK]      Vector search in memory (VECTOR_STORE=memory)"]
    url = f"http://{settings.qdrant_host}:{settings.qdrant_port}"
    try:
        ok = httpx.get(f"{url}/readyz", timeout=3).status_code == 200
    except httpx.HTTPError:
        ok = False
    if ok:
        return [f"[OK]      Qdrant at {url}"]
    return [
        f"[MISSING] Qdrant is not answering at {url}.",
        "          Start Docker Desktop, then: docker compose up -d qdrant. Until then search runs in memory.",
    ]


def check_voice(settings: Settings) -> list[str]:
    models = settings.voice_models_path()
    wanted = [models / "kokoro" / settings.voice_tts_model, models / "kokoro" / "voices-v1.0.bin"]
    missing = [p.name for p in wanted if not (p.is_file() and p.stat().st_size > 0)]
    whisper = models / "whisper"
    for size in dict.fromkeys([settings.voice_stt_model, settings.voice_stt_cpu_model]):
        if not any(whisper.glob(f"models--*--faster-whisper-{size}/snapshots/*/model.bin")):
            missing.append(f"Whisper {size}")
    if not missing:
        return [f"[OK]      Voice models in {models}"]
    return [
        f"[MISSING] Voice models: {', '.join(missing)}. Voice stays off until they are there.",
        "          Run: .venv\\Scripts\\python.exe scripts\\download_models.py --no-ollama",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true", help="exit 1 when anything is missing")
    args = parser.parse_args()
    settings = Settings()
    lines = [*check_ollama(settings, _download_models()), *check_qdrant(settings), *check_voice(settings)]
    print("\n".join(lines))
    missing = any(line.startswith("[MISSING]") for line in lines)
    return 1 if (missing and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
