"""Voice activity detection (PRD F5): is this 32 ms frame speech, and when has the founder finished speaking?

- `SileroVAD`: the Silero VAD v6 ONNX model that ships inside faster-whisper (MIT), run with onnxruntime on CPU. No
  torch: the `silero-vad` package would pull it in. About 1 MB, well under 1 ms a frame.
- `EnergyVAD`: an RMS threshold. The fallback when Silero cannot load (R3), and the tests' detector.
- `Endpointer`: turns per-frame probabilities into speech start and end-of-utterance after `silence_ms` of quiet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from app.voice.audio import FRAME, FRAME_MS, rms

CONTEXT = 64  # samples of the previous frame that Silero v5 and later read before each 512-sample window


class VAD(Protocol):
    name: str

    def probability(self, frame: np.ndarray) -> float:
        """Probability that this frame (FRAME samples at 16 kHz, float32) is speech."""
        ...

    def reset(self) -> None: ...


class EnergyVAD:
    name = "energy"

    def __init__(self, threshold: float = 0.02) -> None:
        self.threshold = threshold

    def probability(self, frame: np.ndarray) -> float:
        level = rms(frame)
        return float(min(1.0, level / (2 * self.threshold)))

    def reset(self) -> None:
        return None


def bundled_silero_path() -> Path | None:
    try:
        import faster_whisper
    except ImportError:
        return None
    path = Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"
    return path if path.is_file() else None


class SileroVAD:
    name = "silero"

    def __init__(self, model_path: Path | None = None) -> None:
        import onnxruntime as ort

        path = model_path or bundled_silero_path()
        if path is None or not Path(path).is_file():
            raise FileNotFoundError("Silero VAD model not found (install the voice extra: faster-whisper)")
        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self._session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)

    def probability(self, frame: np.ndarray) -> float:
        frame = np.asarray(frame, dtype=np.float32)
        if frame.size != FRAME:
            frame = np.pad(frame[:FRAME], (0, max(0, FRAME - frame.size)))
        window = np.concatenate([self._context, frame])[None, :]
        probs, self._h, self._c = self._session.run(None, {"input": window, "h": self._h, "c": self._c})
        self._context = frame[-CONTEXT:]
        return float(np.asarray(probs).reshape(-1)[0])


def build_vad(kind: str, threshold: float = 0.02) -> tuple[VAD, str]:
    """The detector asked for, or the energy one with the reason Silero could not load."""
    if kind == "silero":
        try:
            return SileroVAD(), ""
        except Exception as exc:  # missing package or model file: never fail the voice lane (R3)
            return EnergyVAD(threshold), f"Silero VAD unavailable ({exc}); using the energy detector"
    return EnergyVAD(threshold), ""


@dataclass
class VadEvent:
    kind: str  # "start" (speech began) or "end" (end of utterance)
    frame_index: int


class Endpointer:
    """Speech starts after `start_ms` of frames above the threshold; the utterance ends after `silence_ms` below."""

    def __init__(self, threshold: float = 0.5, start_ms: float = 96, silence_ms: float = 400) -> None:
        self.threshold = threshold
        self.start_frames = max(1, round(start_ms / FRAME_MS))
        self.silence_frames = max(1, round(silence_ms / FRAME_MS))
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self._voiced = 0
        self._quiet = 0
        self.index = -1
        self.last_voiced_index = -1
        self.speech_started_index = -1

    def push(self, probability: float) -> VadEvent | None:
        self.index += 1
        voiced = probability >= self.threshold
        if voiced:
            self.last_voiced_index = self.index
        if not self.in_speech:
            self._voiced = self._voiced + 1 if voiced else 0
            if self._voiced >= self.start_frames:
                self.in_speech, self._quiet = True, 0
                self.speech_started_index = self.index - self.start_frames + 1
                return VadEvent("start", self.speech_started_index)
            return None
        self._quiet = 0 if voiced else self._quiet + 1
        if self._quiet >= self.silence_frames:
            self.in_speech, self._voiced = False, 0
            return VadEvent("end", self.last_voiced_index)
        return None

    def speech_ms(self) -> float:
        """How long the current utterance has lasted so far."""
        if not self.in_speech:
            return 0.0
        return (self.index - self.speech_started_index + 1) * FRAME_MS
