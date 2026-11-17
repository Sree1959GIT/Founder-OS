"""Download every model FounderOS uses, once. Re-running skips what is already there.

    python scripts/download_models.py               Ollama models, then the voice models
    python scripts/download_models.py --no-voice    Ollama models only
    python scripts/download_models.py --no-ollama   voice models only (Whisper, Kokoro)
    python scripts/download_models.py --check       report what is there and what is missing; download nothing

Ollama models (`OLLAMA_CHAT_MODEL`, default qwen3:8b, about 5.2 GB; `OLLAMA_EMBED_MODEL`, default nomic-embed-text,
about 0.3 GB; `FAST_LANE_MODEL` when set) are pulled through Ollama's own HTTP API at `OLLAMA_BASE_URL`, so this works
the same for the native Ollama app and for Ollama in a Docker container, with or without the `ollama` command.

Voice models (Whisper `VOICE_STT_MODEL`, default small.en, and the CPU fallback base.en; Kokoro-82M ONNX and its
voices, about 900 MB in all) go to `<DATA_DIR>/models` through `scripts/download_voice_models.py`.

Exit code 0 when every model is there at the end, 1 otherwise (setup.bat goes on either way: the app starts without
them and the health badge says what is missing).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402


def ollama_models(settings: Settings) -> list[str]:
    names = [settings.ollama_chat_model, settings.ollama_embed_model, settings.fast_lane_model]
    return list(dict.fromkeys(n.strip() for n in names if n and n.strip()))


def _has(pulled: set[str], name: str) -> bool:
    return name in pulled or f"{name}:latest" in pulled


def pulled_models(base: str) -> set[str] | None:
    """The models Ollama has, or None when it does not answer."""
    try:
        response = httpx.get(f"{base}/api/tags", timeout=10)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    return {str(m.get("name", "")) for m in response.json().get("models", [])}


def pull(base: str, name: str) -> bool:
    """Stream `/api/pull` and print progress on one line. True when Ollama reports success."""
    print(f"  pulling {name} ...", flush=True)
    last = ""
    try:
        with httpx.stream("POST", f"{base}/api/pull", json={"model": name}, timeout=httpx.Timeout(30, read=600)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("error"):
                    print(f"\n  [ERROR] {name}: {event['error']}")
                    return False
                status = str(event.get("status", ""))
                total, done = event.get("total"), event.get("completed")
                shown = f"{status} {done * 100 // total}%" if total and done is not None else status
                if shown != last:
                    print(f"\r    {shown[:70]:<70}", end="", flush=True)
                    last = shown
                if status == "success":
                    print()
                    return True
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        print(f"\n  [ERROR] {name}: {exc}")
        return False
    print()
    return False


def do_ollama(settings: Settings, check: bool) -> bool:
    base = settings.ollama_base_url.rstrip("/")
    print(f"Ollama at {base}:")
    pulled = pulled_models(base)
    if pulled is None:
        print("  [MISSING] Ollama is not answering. Start the Ollama app or its Docker container")
        print("            (or set OLLAMA_BASE_URL in .env), then run this script again.")
        return False
    ok = True
    for name in ollama_models(settings):
        if _has(pulled, name):
            print(f"  have {name}")
        elif check:
            print(f"  [MISSING] {name}")
            ok = False
        else:
            ok = pull(base, name) and ok
    return ok


def do_voice(check: bool) -> bool:
    print("Voice models:")
    if check:
        settings = Settings()
        models = settings.voice_models_path()
        kokoro = [models / "kokoro" / settings.voice_tts_model, models / "kokoro" / "voices-v1.0.bin"]
        whisper = models / "whisper"
        ok = True
        for path in kokoro:
            have = path.is_file() and path.stat().st_size > 0
            print(f"  {'have' if have else '[MISSING]'} {path.name}")
            ok = ok and have
        for size in dict.fromkeys([settings.voice_stt_model, settings.voice_stt_cpu_model]):
            have = any(whisper.glob(f"models--*--faster-whisper-{size}/snapshots/*/model.bin"))
            print(f"  {'have' if have else '[MISSING]'} Whisper {size}")
            ok = ok and have
        return ok
    script = ROOT / "scripts" / "download_voice_models.py"
    return subprocess.call([sys.executable, str(script)]) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-ollama", action="store_true", help="skip the Ollama models")
    parser.add_argument("--no-voice", action="store_true", help="skip Whisper and Kokoro")
    parser.add_argument("--check", action="store_true", help="only report what is there")
    args = parser.parse_args()
    settings = Settings()
    ok = True
    if not args.no_ollama:
        ok = do_ollama(settings, args.check) and ok
    if not args.no_voice:
        ok = do_voice(args.check) and ok
    missing = "Some models are missing (see above). FounderOS still starts without them."
    print("All models are there." if ok else missing)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
