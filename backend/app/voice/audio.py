"""PCM helpers for the voice pipeline (PRD F5): 16 kHz mono int16 in, 24 kHz mono int16 out.

Plain NumPy and the standard `wave` module, so tests need no audio library, sound card or GPU.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np

IN_RATE = 16_000  # what the browser's AudioWorklet sends
OUT_RATE = 24_000  # what Kokoro speaks
FRAME = 512  # samples per VAD frame at 16 kHz (32 ms): the window Silero VAD v5 and later expects
FRAME_MS = FRAME * 1000 / IN_RATE


def pcm16_to_float(data: bytes) -> np.ndarray:
    """Little-endian int16 bytes to float32 in [-1, 1]. An odd trailing byte is dropped."""
    usable = len(data) - (len(data) % 2)
    return np.frombuffer(data[:usable], dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


def resample(samples: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Linear resampling: good enough for speech between 16, 22.05, 24 and 48 kHz."""
    samples = np.asarray(samples, dtype=np.float32)
    if src == dst or samples.size == 0:
        return samples
    n = round(samples.size * dst / src)
    x_old = np.linspace(0.0, 1.0, num=samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def read_wav(source: Path | bytes) -> tuple[np.ndarray, int]:
    """Mono float32 samples and the sample rate. Stereo is averaged; 8, 16 and 32-bit PCM are read."""
    with wave.open(io.BytesIO(source) if isinstance(source, bytes) else str(source), "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dtype = {1: np.uint8, 2: np.dtype("<i2"), 4: np.dtype("<i4")}.get(width)
    if dtype is None:
        raise ValueError(f"unsupported WAV sample width: {width} bytes")
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if width == 1:
        data = (data - 128.0) / 128.0
    else:
        data /= float(2 ** (8 * width - 1))
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data.astype(np.float32), rate


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(float_to_pcm16(samples))


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0


class FrameBuffer:
    """Cuts an incoming byte stream of any chunk size into fixed VAD frames."""

    def __init__(self, frame: int = FRAME) -> None:
        self.frame = frame
        self._pending = np.zeros(0, dtype=np.float32)

    def push(self, data: bytes) -> list[np.ndarray]:
        self._pending = np.concatenate([self._pending, pcm16_to_float(data)])
        count = self._pending.size // self.frame
        frames = [self._pending[i * self.frame : (i + 1) * self.frame] for i in range(count)]
        self._pending = self._pending[count * self.frame :]
        return frames
