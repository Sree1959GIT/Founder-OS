"""Text to speech (PRD F5): Kokoro-82M (ONNX) sentence by sentence, behind an interface with a fake.

Kokoro runs on the CPU by default: it is fast enough there for one sentence at a time, and it leaves the shared GPU
to qwen3:8b and Whisper. Short fixed lines (acknowledgements) are cached, so they cost nothing after the first time.
Licence note (PRD §12): the weights are Apache-2.0 and kokoro-onnx is MIT, but its phonemizer and espeak-ng are GPL-3.0.
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
from loguru import logger

from app.voice.audio import OUT_RATE, resample

CACHE_CHARS = 80  # lines up to this length are kept once synthesised
CACHE_SIZE = 64


class TTS(Protocol):
    name: str
    device: str
    model: str
    note: str

    def synthesize(self, text: str) -> np.ndarray:
        """float32 samples at OUT_RATE. Blocking: callers run it in a thread."""
        ...


@dataclass
class FakeTTS:
    """A quiet tone, 60 ms a word: tests hear audio frames without a model."""

    ms_per_word: float = 60.0
    delay_s: float = 0.0
    name: str = "fake"
    device: str = "cpu"
    model: str = "fake"
    note: str = ""
    spoken: list[str] = field(default_factory=list)

    def synthesize(self, text: str) -> np.ndarray:
        if self.delay_s:
            time.sleep(self.delay_s)
        self.spoken.append(text)
        words = max(1, len(text.split()))
        n = int(OUT_RATE * words * self.ms_per_word / 1000)
        t = np.arange(n, dtype=np.float32) / OUT_RATE
        return (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class KokoroTTS:
    name = "kokoro"

    def __init__(
        self, model_path: Path, voices_path: Path, voice: str = "af_heart", speed: float = 1.0, threads: int = 8
    ) -> None:
        from kokoro_onnx import Kokoro

        if not model_path.is_file() or not voices_path.is_file():
            raise FileNotFoundError(
                f"Kokoro files missing ({model_path.name}, {voices_path.name}): "
                "run python scripts/download_voice_models.py"
            )
        import onnxruntime as ort

        started = time.perf_counter()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads  # measured on an i9-13900HX: 8 threads 1.2 s, the default 1.8 s
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        self._kokoro = Kokoro.from_session(session, str(voices_path))
        self.voice, self.speed = voice, speed
        self.model = model_path.name
        self.device = "cpu"
        self.note = ""
        self.synthesize("Ready.")
        logger.info("TTS Kokoro {} ready in {:.0f} ms", self.model, (time.perf_counter() - started) * 1000)

    def synthesize(self, text: str) -> np.ndarray:
        samples, rate = self._kokoro.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        return resample(np.asarray(samples, dtype=np.float32), int(rate), OUT_RATE)


class CachedTTS:
    """Short lines are synthesised once. Everything else passes straight through."""

    def __init__(self, inner: TTS) -> None:
        self.inner = inner
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def device(self) -> str:
        return self.inner.device

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def note(self) -> str:
        return self.inner.note

    def synthesize(self, text: str) -> np.ndarray:
        key = text.strip()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        audio = self.inner.synthesize(key)
        if len(key) <= CACHE_CHARS:
            self._cache[key] = audio
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return audio


_SPOKEN_FIXES = [
    (re.compile(r"\[[^\]]*\]"), ""),  # source paths in brackets are for the screen
    (re.compile(r"\*\*|__|`"), ""),
    (re.compile(r"\s+%"), " percent"),
    (re.compile(r"%"), " percent"),
    (re.compile(r"\s{2,}"), " "),
]


_CLAUSE = re.compile(r"(?<=[,;:])\s+")
FIRST_CHUNK_CHARS = 60


def speech_chunks(text: str) -> list[str]:
    """A long sentence is synthesised clause by clause, so its first words play while the rest is being made."""
    if len(text) <= FIRST_CHUNK_CHARS:
        return [text]
    chunks: list[str] = []
    for clause in _CLAUSE.split(text):
        if chunks and len(chunks[-1]) < 25:
            chunks[-1] = f"{chunks[-1]} {clause}"  # a clause of two words alone sounds clipped
        else:
            chunks.append(clause)
    return [c for c in chunks if c.strip()]


def for_speech(text: str) -> str:
    """What the screen shows, made sayable: no source brackets or markdown; "%" said as "percent"."""
    out = text
    for pattern, repl in _SPOKEN_FIXES:
        out = pattern.sub(repl, out)
    return out.strip()
