"""Speech to text (PRD F5): faster-whisper on the GPU, with a CPU fallback, behind an interface with a fake.

Sizes for the founder's PC (RTX 4080 Laptop, 12 GB, shared with qwen3:8b in Docker Ollama): `small.en` with
`int8_float16` on CUDA (about 0.5 GB of VRAM measured, see HANDOVER), `base.en` int8 on CPU as the fallback.
A CUDA load that fails, or that loads but cannot run (missing cuBLAS / cuDNN DLLs on Windows), falls back to CPU at
start-up, never in the middle of a turn.
"""

from __future__ import annotations

import contextlib
import math
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
from loguru import logger

from app.voice.audio import IN_RATE


@dataclass
class Transcript:
    text: str
    ms: float
    audio_ms: float
    confidence: float = 1.0  # 0 to 1: how sure the recogniser is of these words (1.0 when it does not say)


class STT(Protocol):
    name: str
    device: str
    model: str
    note: str

    def transcribe(self, samples: np.ndarray) -> Transcript:
        """16 kHz mono float32 in; the words out. Blocking: callers run it in a thread."""
        ...


@dataclass
class FakeSTT:
    """Scripted transcripts, in order (the last one repeats). Tests feed WAV fixtures and read these back."""

    script: list[str] = field(default_factory=lambda: ["What is our runway?"])
    delay_s: float = 0.0
    name: str = "fake"
    device: str = "cpu"
    model: str = "fake"
    note: str = ""
    heard: list[int] = field(default_factory=list)  # sample counts, so tests can check what reached the STT
    confidences: list[float] = field(default_factory=list)  # one per script line; missing means sure

    def transcribe(self, samples: np.ndarray) -> Transcript:
        started = time.perf_counter()
        # The script line is taken when the audio arrives, not after the delay: two utterances being transcribed at
        # once must not swap their words.
        index = min(len(self.heard), len(self.script) - 1)
        self.heard.append(int(samples.size))
        text = self.script[index] if self.script else ""
        if self.delay_s:
            time.sleep(self.delay_s)
        confidence = self.confidences[index] if index < len(self.confidences) else 1.0
        return Transcript(text, (time.perf_counter() - started) * 1000, samples.size * 1000 / IN_RATE, confidence)


def add_cuda_dll_dirs() -> list[str]:
    """Windows: make the CUDA DLLs from the `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` wheels findable.

    CTranslate2 loads cublas64_12.dll and cuDNN 9 at run time; without them a CUDA model loads and then fails
    ("Library cublas64_12.dll is not found"). The wheels put them in site-packages/nvidia/*/bin, which Windows
    does not search. Nothing happens on other systems or when the wheels are absent.
    """
    if os.name != "nt":
        return []
    try:
        import nvidia
    except ImportError:
        return []
    added = []
    for root in getattr(nvidia, "__path__", []):
        for folder in sorted(Path(root).glob("*/bin")):
            with contextlib.suppress(OSError):
                os.add_dll_directory(str(folder))
            if str(folder) not in os.environ.get("PATH", ""):
                os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            added.append(str(folder))
    return added


class FasterWhisperSTT:
    name = "faster_whisper"

    def __init__(
        self,
        model: str = "small.en",
        device: str = "auto",
        compute_type: str = "auto",
        cpu_model: str = "base.en",
        download_root: Path | None = None,
        cpu_threads: int = 8,
        prompt: str = "",
        hotwords: str = "",
    ) -> None:
        from faster_whisper import WhisperModel

        self.note = ""
        # Founder re-test R6: the recogniser is told what it is likely to hear (agent and metric names, "Dubai",
        # "hires", "runway"). Empty strings turn that off.
        self.prompt, self.hotwords = prompt.strip(), hotwords.strip()
        if device in ("auto", "cuda"):
            add_cuda_dll_dirs()
        attempts: list[tuple[str, str, str]] = []
        if device in ("auto", "cuda"):
            attempts.append((model, "cuda", "int8_float16" if compute_type == "auto" else compute_type))
        if device in ("auto", "cpu"):
            attempts.append((cpu_model if device == "auto" else model, "cpu", "int8"))
        errors: list[str] = []
        for size, dev, ctype in attempts:
            try:
                started = time.perf_counter()
                engine = WhisperModel(
                    size,
                    device=dev,
                    compute_type=ctype,
                    download_root=str(download_root) if download_root else None,
                    cpu_threads=cpu_threads,
                )
                self._model, self.model, self.device, self.compute_type = engine, size, dev, ctype
                self.transcribe(np.zeros(IN_RATE // 2, dtype=np.float32))  # a CUDA DLL problem shows up here
                logger.info(
                    "STT {} on {} ({}) ready in {:.0f} ms", size, dev, ctype, (time.perf_counter() - started) * 1000
                )
                break
            except Exception as exc:
                errors.append(f"{size} on {dev}: {exc}")
                logger.warning("STT {} on {} unavailable: {}", size, dev, exc)
        else:
            raise RuntimeError("; ".join(errors) or "no device to try")
        if errors:
            self.note = f"fell back to {self.device}: {errors[0]}"

    def transcribe(self, samples: np.ndarray) -> Transcript:
        started = time.perf_counter()
        segments, _ = self._model.transcribe(
            np.asarray(samples, dtype=np.float32),
            language="en",
            beam_size=1,
            vad_filter=False,  # our own VAD already cut the utterance
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=self.prompt or None,
            hotwords=self.hotwords or None,
        )
        parts = _iter(segments)
        text = " ".join(s.text.strip() for s in parts).strip()
        return Transcript(
            text, (time.perf_counter() - started) * 1000, samples.size * 1000 / IN_RATE, confidence_of(parts)
        )


def confidence_of(segments: list[object]) -> float:
    """The recogniser's own confidence, 0 to 1: the mean token probability over the segments, weighted by length,
    and lowered when it thinks there was no speech at all. Segments without these fields count as sure."""
    total, weight, no_speech = 0.0, 0.0, 0.0
    for segment in segments:
        logprob = getattr(segment, "avg_logprob", None)
        if logprob is None:
            continue
        size = max(1, len(str(getattr(segment, "text", "")).split()))
        total += math.exp(min(0.0, float(logprob))) * size
        weight += size
        no_speech = max(no_speech, float(getattr(segment, "no_speech_prob", 0.0) or 0.0))
    if not weight:
        return 1.0
    return round((total / weight) * (1.0 - no_speech if no_speech > 0.6 else 1.0), 3)


def _iter(segments: Iterable[object]) -> list[object]:
    return list(segments)  # faster-whisper decodes lazily: the work happens here
