"""Which Whisper model, and does the FounderOS vocabulary help? (founder re-test R6)

    python scripts/stt_bakeoff.py                              small.en against large-v3-turbo, on this PC's GPU
    python scripts/stt_bakeoff.py --models small.en            one model only
    python scripts/stt_bakeoff.py --noise 0.02                 louder room noise under the speech

It says each test phrase with Kokoro (the app's own voice, resampled to 16 kHz, with room noise mixed in), then
transcribes it with each model, with and without the domain prompt and hotwords (`app/voice/domain.py`). Per model it
prints: phrases heard right, latency (p50 and slowest), the confidence of right and wrong transcripts, and the VRAM the
model added (nvidia-smi). Run it with qwen3:8b loaded in Ollama to see whether the larger model still fits.

Synthetic speech is cleaner than a microphone: read the numbers as a comparison between models, not as accuracy on
your voice. A larger model is downloaded once into <models>/whisper (large-v3-turbo: about 1.6 GB).
"""

from __future__ import annotations

import argparse
import gc
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.voice.audio import IN_RATE, OUT_RATE, resample  # noqa: E402
from app.voice.domain import HOTWORDS, PROMPT, corrected  # noqa: E402
from app.voice.service import vram_used_gb  # noqa: E402
from app.voice.stt import FasterWhisperSTT  # noqa: E402
from app.voice.tts import KokoroTTS  # noqa: E402

PHRASES = [
    "Should we open a Dubai office?",
    "Re-run the analyst, assume three hires.",
    "Make it a two person team.",
    "Assume three hires.",
    "What is our runway?",
    "What is our churn?",
    "Redo the Devil's Advocate.",
    "Re-run the Market Scout.",
    "What is our gross margin?",
    "How long is our runway if we hire two people?",
    "Stop the team.",
    "Restart with my change.",
    "Go through the risks.",
    "What about net burn?",
    "Should we raise prices by ten percent?",
    "Re-run the Regulatory and Tax adviser.",
]
VOICES = ["af_heart", "am_michael", "bf_emma"]


def key(text: str) -> str:
    """Words only, with spoken numbers and digits treated alike."""
    words = {"two": "2", "three": "3", "ten": "10", "percent": "%", "rerun": "re run", "adviser": "advisor"}
    text = text.replace("&", " and ")
    out = re.sub(r"[^a-z0-9% ]+", " ", text.lower().replace("%", " % "))
    return " ".join(words.get(w, w) for w in out.split())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default="small.en,large-v3-turbo")
    parser.add_argument("--compute", default="int8_float16,int8")
    parser.add_argument("--noise", type=float, default=0.01, help="RMS of the room noise (speech is about 0.1)")
    parser.add_argument("--models-dir", type=Path, default=ROOT / "data" / "models")
    args = parser.parse_args()

    kokoro = args.models_dir / "kokoro"
    rng = np.random.default_rng(7)
    clips: list[tuple[str, str, np.ndarray]] = []
    for voice in VOICES:
        try:
            tts = KokoroTTS(kokoro / "kokoro-v1.0.onnx", kokoro / "voices-v1.0.bin", voice=voice)
        except Exception as exc:
            print(f"voice {voice} unavailable: {exc}")
            continue
        for phrase in PHRASES:
            speech = resample(tts.synthesize(phrase), OUT_RATE, IN_RATE).astype(np.float32)
            noise = rng.normal(0, args.noise, speech.size + IN_RATE // 2).astype(np.float32)
            noise[IN_RATE // 4 : IN_RATE // 4 + speech.size] += speech
            clips.append((voice, phrase, noise))
    print(f"{len(clips)} clips ({len(PHRASES)} phrases x {len(clips) // len(PHRASES)} voices), noise RMS {args.noise}")
    print(f"VRAM in use before any model: {vram_used_gb()} GB\n")

    for model in args.models.split(","):
        for compute in args.compute.split(","):
            before = vram_used_gb()
            try:
                started = time.perf_counter()
                stt = FasterWhisperSTT(model, "cuda", compute, download_root=args.models_dir / "whisper")
                load_s = time.perf_counter() - started
            except Exception as exc:
                print(f"{model} ({compute}): unavailable: {exc}\n")
                continue
            after = vram_used_gb()
            added = None if before is None or after is None else round(after - before, 2)
            for label, prompt, hotwords in (("plain", "", ""), ("with the FounderOS vocabulary", PROMPT, HOTWORDS)):
                stt.prompt, stt.hotwords = prompt, hotwords
                stt.transcribe(clips[0][2])  # warm
                right, times, sure, unsure, misses = 0, [], [], [], []
                for voice, phrase, samples in clips:
                    heard = stt.transcribe(samples)
                    times.append(heard.ms)
                    ok = key(corrected(heard.text)) == key(phrase)
                    right += ok
                    (sure if ok else unsure).append(heard.confidence)
                    if not ok:
                        misses.append(f"      {voice}: {phrase!r} heard as {heard.text!r} ({heard.confidence})")
                print(
                    f"{model} ({compute}), {label}: {right}/{len(clips)} right | p50 {statistics.median(times):.0f} ms"
                    f", slowest {max(times):.0f} ms | VRAM +{added} GB | loaded in {load_s:.1f} s"
                )
                if sure:
                    print(f"    confidence when right: lowest {min(sure)}, median {statistics.median(sure)}")
                if unsure:
                    print(f"    confidence when wrong: {sorted(unsure)}")
                print("\n".join(misses[:12]))
            del stt
            gc.collect()
            time.sleep(1.0)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
