"""Per-turn voice latency (PRD F5: "metrics logged per turn and shown in a debug overlay").

All times are server-side `perf_counter` milliseconds from the end of the founder's speech (the last voiced frame, or
the push-to-talk release), so the endpointer's silence wait is inside the figure, as the founder hears it.
"""

from __future__ import annotations

import statistics
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TurnMetric:
    id: str = field(default_factory=lambda: f"vt_{uuid.uuid4().hex[:8]}")
    session_id: str = ""
    mode: str = "ptt"
    text: str = ""
    speech_ms: float = 0.0
    stt_ms: float | None = None  # transcription alone
    turn_ms: float | None = None  # end of speech to the lane's decision (classify, start a run)
    first_audio_ms: float | None = None  # end of speech to the first audio sent, any lane
    first_audio_lane: str = ""
    first_answer_audio_ms: float | None = None  # end of speech to the first sentence of the verified answer
    tts_first_ms: float | None = None  # synthesis time of the first sentence
    kind: str = ""  # what the turn was: run, queued, amendment, answered, stop, backchannel...

    def as_dict(self) -> dict[str, Any]:
        return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in asdict(self).items()}


@dataclass
class BargeIn:
    id: str = field(default_factory=lambda: f"vb_{uuid.uuid4().hex[:8]}")
    session_id: str = ""
    paused_ms: float | None = None  # speech onset to "pause" sent (audio stops at the client)
    stopped_ms: float | None = None  # speech onset to "interrupt" sent (speech cancelled)
    client_flush_ms: float | None = None  # the client's own measure: message received to audio silent
    verdict: str = ""  # barge_in or backchannel
    by: str = ""
    text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _p50(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


class VoiceMetrics:
    def __init__(self, keep: int = 200) -> None:
        self.turns: deque[TurnMetric] = deque(maxlen=keep)
        self.barge_ins: deque[BargeIn] = deque(maxlen=keep)

    def summary(self) -> dict[str, Any]:
        def pick(name: str, lane: str | None = None) -> list[float]:
            out = []
            for t in self.turns:
                value = getattr(t, name)
                if value is not None and (lane is None or t.first_audio_lane == lane):
                    out.append(value)
            return out

        stops = [b.stopped_ms for b in self.barge_ins if b.stopped_ms is not None]
        pauses = [b.paused_ms for b in self.barge_ins if b.paused_ms is not None]
        flushes = [b.client_flush_ms for b in self.barge_ins if b.client_flush_ms is not None]
        return {
            "turns": len(self.turns),
            "p50_ms": {
                "stt": _p50(pick("stt_ms")),
                "first_audio": _p50(pick("first_audio_ms")),
                "first_answer_audio": _p50(pick("first_answer_audio_ms")),
                "tts_first": _p50(pick("tts_first_ms")),
                "barge_in_pause": _p50(pauses),
                "barge_in_stop": _p50(stops),
                "client_flush": _p50(flushes),
            },
            "recent_turns": [t.as_dict() for t in list(self.turns)[-10:]],
            "recent_barge_ins": [b.as_dict() for b in list(self.barge_ins)[-10:]],
        }
