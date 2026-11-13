"""Builds and holds the voice engines (VAD, STT, TTS) for the app, loads them off the event loop, and measures VRAM.

Real engines load once in a worker thread at start-up, so the first spoken turn does not wait for a model. Each one
falls back on its own: Whisper on CUDA to Whisper on CPU, Silero to the energy detector, Kokoro to nothing (the
answer is still shown; the reason is in `/api/voice/status`). VRAM is read through NVML before and after loading:
the GPU is shared with Docker Ollama, so the difference is what the voice models added.
"""

from __future__ import annotations

import asyncio
import importlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.config import Settings
from app.voice.metrics import VoiceMetrics
from app.voice.session import VoiceConfig
from app.voice.stt import STT, FakeSTT, FasterWhisperSTT
from app.voice.tts import TTS, CachedTTS, FakeTTS, KokoroTTS
from app.voice.vad import VAD, EnergyVAD, build_vad


def vram_used_gb() -> float | None:
    """Memory in use on GPU 0, every process included (Ollama's too), or None without NVML or a GPU."""
    try:
        nvml = importlib.import_module("pynvml")
        nvml.nvmlInit()
        try:
            info = nvml.nvmlDeviceGetMemoryInfo(nvml.nvmlDeviceGetHandleByIndex(0))
            return round(info.used / 2**30, 3)
        finally:
            nvml.nvmlShutdown()
    except Exception:
        return None


def vram_total_gb() -> float | None:
    try:
        nvml = importlib.import_module("pynvml")
        nvml.nvmlInit()
        try:
            return round(nvml.nvmlDeviceGetMemoryInfo(nvml.nvmlDeviceGetHandleByIndex(0)).total / 2**30, 3)
        finally:
            nvml.nvmlShutdown()
    except Exception:
        return None


@dataclass
class VoiceEngines:
    vad: VAD
    stt: STT | None
    tts: TTS | None
    notes: list[str] = field(default_factory=list)


class VoiceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.metrics = VoiceMetrics()
        self.engines: VoiceEngines | None = None
        self.loading = False
        self.load_ms: float | None = None
        self.vram_before_gb: float | None = None
        self.vram_after_gb: float | None = None
        self.stt_vram_gb: float | None = None  # measured around the Whisper load only (Kokoro and VAD use the CPU)
        self._lock = threading.Lock()
        self._ready = asyncio.Event()

    def config(self) -> VoiceConfig:
        s = self.settings
        return VoiceConfig(
            mode=s.voice_mode,
            vad_threshold=s.voice_vad_threshold,
            end_silence_ms=s.voice_end_silence_ms,
            barge_in_ms=s.voice_barge_in_ms,
            partial_interval_ms=s.voice_partial_interval_ms,
            echo_gate=s.voice_echo_gate,
        )

    # ---------------------------------------------------------------------------------------------------- loading
    async def ensure_loaded(self) -> VoiceEngines:
        if self.engines is not None:
            return self.engines
        await asyncio.to_thread(self.load)
        assert self.engines is not None
        return self.engines

    def load(self) -> VoiceEngines:
        with self._lock:
            if self.engines is not None:
                return self.engines
            self.loading = True
            started = time.perf_counter()
            self.vram_before_gb = vram_used_gb()
            s = self.settings
            notes: list[str] = []
            vad, note = build_vad(s.voice_vad) if s.voice_vad != "energy" else (EnergyVAD(), "")
            if note:
                notes.append(note)
            stt: STT | None
            if s.voice_stt == "fake":
                stt = FakeSTT()
            else:
                try:
                    stt_before = vram_used_gb()
                    stt = FasterWhisperSTT(
                        s.voice_stt_model,
                        s.voice_stt_device,
                        s.voice_stt_compute_type,
                        cpu_model=s.voice_stt_cpu_model,
                        download_root=s.voice_models_path() / "whisper",
                    )
                    stt_after = vram_used_gb()
                    if stt_before is not None and stt_after is not None:
                        self.stt_vram_gb = round(stt_after - stt_before, 3)
                    if stt.note:
                        notes.append(f"STT {stt.note}")
                except Exception as exc:
                    stt = None
                    notes.append(f"STT unavailable: {exc}")
            tts: TTS | None
            if s.voice_tts == "fake":
                tts = FakeTTS()
            else:
                try:
                    folder = s.voice_models_path() / "kokoro"
                    tts = CachedTTS(
                        KokoroTTS(folder / s.voice_tts_model, folder / "voices-v1.0.bin", voice=s.voice_tts_voice)
                    )
                except Exception as exc:
                    tts = None
                    notes.append(f"TTS unavailable: {exc}")
            self.engines = VoiceEngines(vad=vad, stt=stt, tts=tts, notes=notes)
            self.vram_after_gb = vram_used_gb()
            self.load_ms = round((time.perf_counter() - started) * 1000, 1)
            self.loading = False
            for line in notes:
                logger.warning("Voice: {}", line)
            logger.info("Voice engines ready in {} ms", self.load_ms)
            return self.engines

    # ---------------------------------------------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        e = self.engines

        def engine(x: Any) -> dict[str, Any] | None:
            if x is None:
                return None
            return {"name": x.name, "model": x.model, "device": x.device, "note": x.note}

        added = (
            round(self.vram_after_gb - self.vram_before_gb, 3)
            if self.vram_after_gb is not None and self.vram_before_gb is not None
            else None
        )
        return {
            "enabled": self.settings.voice_enabled,
            "ready": e is not None and e.stt is not None and e.tts is not None,
            "loading": self.loading,
            "load_ms": self.load_ms,
            "mode": self.settings.voice_mode,
            "vad": {"name": e.vad.name} if e else None,
            "stt": engine(e.stt) if e else None,
            "tts": engine(e.tts) if e else None,
            "notes": e.notes if e else [],
            "vram_gb": {
                "total": vram_total_gb(),
                "used_now": vram_used_gb(),
                "before_voice": self.vram_before_gb,
                "after_voice": self.vram_after_gb,
                "added_by_voice": added,
                # Narrower: around the Whisper load alone. Ollama loading a model at the same moment still inflates it.
                "whisper": self.stt_vram_gb,
            },
            "settings": {
                "end_silence_ms": self.settings.voice_end_silence_ms,
                "barge_in_ms": self.settings.voice_barge_in_ms,
                "vad_threshold": self.settings.voice_vad_threshold,
            },
        }
