"""Download the voice models (M5) into <DATA_DIR>/models, once. Re-running skips files already there.

    python scripts/download_voice_models.py                 Whisper small.en + base.en, Kokoro and voices
    python scripts/download_voice_models.py --kokoro-int8   also the 8-bit Kokoro model (88 MB, from GitHub)

Sources: Whisper as CTranslate2 conversions from Hugging Face (Systran/faster-whisper-*, MIT), Kokoro-82M ONNX from the
kokoro-onnx release "model-files-v1.0" (weights Apache-2.0). Needs the voice packages: pip install -e "backend[voice]".
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402

ATTEMPTS = 2
KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
# The same two files (fp32 model and voices) on Hugging Face, for when GitHub release downloads fail (seen: 504s).
KOKORO_MIRROR = "https://huggingface.co/fastrtc/kokoro-onnx/resolve/main/"
MIRRORED = {"kokoro-v1.0.onnx", "voices-v1.0.bin"}


def fetch(url: str, target: Path, attempts: int = ATTEMPTS) -> None:
    if target.is_file() and target.stat().st_size > 0:
        print(f"  have {target.name}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    print(f"  downloading {target.name} ...", flush=True)
    for attempt in range(1, attempts + 1):
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
                response.raise_for_status()
                with partial.open("wb") as handle:
                    for chunk in response.iter_bytes(1 << 20):
                        handle.write(chunk)
            break
        except httpx.HTTPError as exc:
            if attempt == attempts:
                raise
            print(f"  attempt {attempt} failed ({exc}); trying again in {attempt * 5} s")
            time.sleep(attempt * 5)
    partial.replace(target)
    print(f"  saved {target} ({target.stat().st_size / 2**20:.0f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kokoro-int8", action="store_true", help="also kokoro-v1.0.int8.onnx (88 MB, GitHub only)")
    parser.add_argument("--whisper", default="", help="comma-separated sizes; default: VOICE_STT_MODEL and CPU model")
    args = parser.parse_args()
    settings = Settings()
    models = settings.voice_models_path()
    print(f"Voice models folder: {models}")
    print("Kokoro:")
    names = [settings.voice_tts_model, "voices-v1.0.bin"] + (["kokoro-v1.0.int8.onnx"] if args.kokoro_int8 else [])
    for name in dict.fromkeys(names):
        try:
            fetch(KOKORO + name, models / "kokoro" / name)
        except httpx.HTTPError as exc:
            if name not in MIRRORED:
                print(f"  {name}: {exc}; set VOICE_TTS_MODEL=kokoro-v1.0.onnx to use the mirrored model")
                continue
            print(f"  GitHub failed ({exc}); using the Hugging Face mirror")
            fetch(KOKORO_MIRROR + name, models / "kokoro" / name)
    print("Whisper:")
    try:
        from faster_whisper import download_model
    except ImportError:
        print('  faster-whisper is not installed: pip install -e "backend[voice]"')
        return 1
    sizes = [s for s in (args.whisper or f"{settings.voice_stt_model},{settings.voice_stt_cpu_model}").split(",") if s]
    for size in dict.fromkeys(sizes):
        path = download_model(size, cache_dir=str(models / "whisper"))
        print(f"  have {size} at {path}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
