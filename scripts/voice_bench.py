"""Voice latency on this PC (M5): end of speech to first spoken word, to the first sentence of the answer, barge-in.

    python scripts/voice_bench.py                      against http://127.0.0.1:8000 (the backend must be running)
    python scripts/voice_bench.py --turns 5            five runway questions (p50 over them)
    python scripts/voice_bench.py --no-barge-in

It plays the WAV fixtures in backend/tests/fixtures/voice into /ws/voice in real time (hands-free mode, as a
microphone would), so the backend's own VAD finds the end of speech. Then it asks the Dubai question and, as soon as
FounderOS starts speaking, plays "Wait, stop..." over it. It prints the backend's measurements and VRAM.
Set "Ask before a team runs" to Never first, or the Dubai run waits for your approval.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.voice.audio import FRAME, IN_RATE, float_to_pcm16, read_wav, resample  # noqa: E402

FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "voice"


def pcm(name: str) -> bytes:
    samples, rate = read_wav(FIXTURES / f"{name}.wav")
    return float_to_pcm16(resample(samples, rate, IN_RATE))


async def play(ws: Any, data: bytes) -> None:
    """Real time: one 32 ms frame every 32 ms, then a second of silence so the end of speech is found."""
    step = FRAME * 2
    silence = bytes(step)
    started = time.perf_counter()
    frames = [data[i : i + step] for i in range(0, len(data), step)] + [silence] * 32
    for n, frame in enumerate(frames):
        await ws.send(frame)
        delay = started + (n + 1) * FRAME / IN_RATE - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)


async def turn(url: str, name: str, *, barge_with: str | None = None, timeout: float = 90) -> dict[str, Any]:
    out: dict[str, Any] = {"fixture": name}
    async with websockets.connect(url, max_size=None) as ws:
        ready = json.loads(await ws.recv())
        out["session_id"] = ready.get("session_id")
        sender = asyncio.create_task(play(ws, pcm(name)))
        barging: asyncio.Task[None] | None = None
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.perf_counter())
            except TimeoutError:
                break
            if isinstance(raw, bytes):
                continue
            message = json.loads(raw)
            kind = message.get("type")
            if kind == "transcript":
                out["heard"] = message["text"]
            elif kind == "metrics" and "turn" in message:
                out["turn"] = message["turn"]
            elif kind == "metrics" and "barge_in" in message:
                out["barge_in"] = message["barge_in"]
            elif kind == "say":
                out.setdefault("said", []).append(f"[{message['lane']}] {message['text']}")
                if barge_with and barging is None:  # interrupt the first thing FounderOS says
                    await sender
                    barging = asyncio.create_task(play(ws, pcm(barge_with)))
                if not barge_with and message["lane"] == "answer":
                    break
            elif kind == "interrupt" and barge_with:
                out["interrupted"] = True
                await asyncio.sleep(0.5)
                break
        sender.cancel()
        if barging is not None:
            barging.cancel()
    return out


def fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f} ms"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--no-barge-in", action="store_true")
    args = parser.parse_args()
    url = args.backend.replace("http", "ws", 1) + "/ws/voice?mode=duplex"
    status = httpx.get(f"{args.backend}/api/voice/status", timeout=60).json()
    print(f"STT {status['stt']} | TTS {status['tts']} | VAD {status['vad']}")
    runs = [asyncio.run(turn(url, "runway")) for _ in range(max(1, args.turns))]
    firsts = [r["turn"]["first_audio_ms"] for r in runs if r.get("turn", {}).get("first_audio_ms") is not None]
    answers = [r["turn"]["first_answer_audio_ms"] for r in runs if r.get("turn", {}).get("first_answer_audio_ms")]
    for r in runs:
        t = r.get("turn", {})
        print(
            f"runway: heard {r.get('heard')!r}; STT {fmt(t.get('stt_ms'))}; first words {fmt(t.get('first_audio_ms'))}"
            f" ({t.get('first_audio_lane')}); first answer sentence {fmt(t.get('first_answer_audio_ms'))}"
        )
    print(f"p50 first words {fmt(statistics.median(firsts) if firsts else None)} (target 1 s)")
    print(f"p50 metric answer {fmt(statistics.median(answers) if answers else None)} (target about 3 s)")
    if not args.no_barge_in:
        r = asyncio.run(turn(url, "dubai", barge_with="stop_wait", timeout=180))
        b = r.get("barge_in", {})
        print(f"dubai: first words {fmt(r.get('turn', {}).get('first_audio_ms'))}; said {r.get('said', [])[:3]}")
        print(
            f"barge-in: audio paused {fmt(b.get('paused_ms'))} after speech began; speech cancelled "
            f"{fmt(b.get('stopped_ms'))} ({b.get('verdict')} by {b.get('by')}); "
            f"interrupted={r.get('interrupted', False)}"
        )
    vram = httpx.get(f"{args.backend}/api/voice/status", timeout=30).json()["vram_gb"]
    print(
        f"VRAM GB: total {vram['total']}, in use now {vram['used_now']}, Whisper load {vram.get('whisper')} "
        f"(before/after all voice models: {vram['before_voice']} / {vram['after_voice']}; "
        "Ollama may have loaded between)"
    )
    metrics = httpx.get(f"{args.backend}/api/voice/metrics", timeout=30).json()
    print("backend p50 (ms):", json.dumps(metrics["p50_ms"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
