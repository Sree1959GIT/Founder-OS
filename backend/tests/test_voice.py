"""M5 voice pipeline: WAV fixtures in, fake STT and TTS, no GPU, microphone or network.

The fixtures in tests/fixtures/voice are real speech (Kokoro-82M, resampled to 16 kHz mono, padded with silence), so
the endpointer sees real speech envelopes; the fake STT returns the words the fixture says.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator
from app.agents.tools import ToolContext
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.main import create_app
from app.voice import turn_taking
from app.voice.audio import FRAME, IN_RATE, FrameBuffer, float_to_pcm16, pcm16_to_float, read_wav, resample
from app.voice.metrics import VoiceMetrics
from app.voice.session import ON_SCREEN, VoiceConfig, VoiceSession
from app.voice.stt import FakeSTT
from app.voice.tts import CachedTTS, FakeTTS, for_speech, speech_chunks
from app.voice.vad import Endpointer, EnergyVAD, build_vad
from tests.test_specialists import _until, slow_provider

FIXTURES = Path(__file__).parent / "fixtures" / "voice"


def wav_bytes(name: str) -> bytes:
    samples, rate = read_wav(FIXTURES / f"{name}.wav")
    return float_to_pcm16(resample(samples, rate, IN_RATE))


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


class Wire:
    """What the session sent: JSON messages and audio bytes."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.audio: list[bytes] = []

    async def send(self, message: dict[str, Any] | bytes) -> None:
        if isinstance(message, bytes):
            self.audio.append(message)
        else:
            self.messages.append(message)

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("type") == kind]


def make(
    finance: Any,
    script: list[str],
    *,
    provider: Any = None,
    mode: str = "ptt",
    decisions: Any = None,
    **config: Any,
) -> tuple[VoiceSession, Wire, FakeSTT, FakeTTS, ConversationManager]:
    orch = AgentOrchestrator(
        LLMRouter(provider or FakeProvider(default=lambda m, t, s: "What would you cut first?")),
        decisions or DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, None, aid),
        approval_policy=config.pop("approval_policy", "cloud_only"),
        approval_timeout_s=5,
    )
    manager = ConversationManager(orch)
    wire, stt, tts = Wire(), FakeSTT(script=script), FakeTTS()
    session = VoiceSession(
        manager, stt, tts, EnergyVAD(), wire.send, config=VoiceConfig(mode=mode, **config), metrics=VoiceMetrics()
    )
    return session, wire, stt, tts, manager


async def stream(session: VoiceSession, data: bytes, chunk: int = FRAME * 2) -> None:
    for i in range(0, len(data), chunk):
        await session.audio(data[i : i + chunk])


# --- audio and VAD ---------------------------------------------------------------------------------------------------
def test_pcm_round_trip_and_framing() -> None:
    tone = (0.3 * np.sin(np.arange(1600) / 5)).astype(np.float32)
    back = pcm16_to_float(float_to_pcm16(tone))
    assert np.max(np.abs(back - tone)) < 1e-3
    buffer = FrameBuffer()
    frames = buffer.push(float_to_pcm16(tone[:700])) + buffer.push(float_to_pcm16(tone[700:]))
    assert len(frames) == 3 and all(f.size == FRAME for f in frames)
    assert resample(tone, 16_000, 24_000).size == 2400


@pytest.mark.parametrize("name", ["runway", "dubai", "uh_huh", "stop_wait"])
def test_each_fixture_is_one_utterance_with_its_end_found(name: str) -> None:
    samples, rate = read_wav(FIXTURES / f"{name}.wav")
    assert rate == IN_RATE
    vad, end = EnergyVAD(), Endpointer(silence_ms=400)
    events = [
        e for i in range(0, samples.size - FRAME, FRAME) if (e := end.push(vad.probability(samples[i : i + FRAME])))
    ]
    kinds = [e.kind for e in events]
    # "Wait, stop. What about...": the pause after "stop." is longer than 400 ms, so that one is two utterances.
    assert kinds == ["start", "end"] * (2 if name == "stop_wait" else 1)
    speech_end_s = events[-1].frame_index * FRAME / IN_RATE
    assert 0.5 < speech_end_s < samples.size / IN_RATE - 0.5  # the padding after the words is silence


def test_silero_missing_falls_back_to_energy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.voice.vad.bundled_silero_path", lambda: None)
    vad, note = build_vad("silero")
    assert vad.name == "energy" and "Silero VAD unavailable" in note


def test_silero_finds_speech_in_a_fixture_when_installed() -> None:
    pytest.importorskip("faster_whisper")
    vad, note = build_vad("silero")
    assert vad.name == "silero", note
    samples, _ = read_wav(FIXTURES / "runway.wav")
    probs = [vad.probability(samples[i : i + FRAME]) for i in range(0, samples.size - FRAME, FRAME)]
    assert max(probs) > 0.8 and probs[0] < 0.2  # speech in the middle, silence at the start


# --- barge-in or backchannel -----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "ms", "verdict", "by"),
    [
        ("Uh-huh.", 300, "backchannel", "rules"),
        ("right", 250, "backchannel", "rules"),
        ("", 200, "backchannel", "rules"),
        ("Wait, stop. What about two hires instead?", 400, "barge_in", "rules"),
        ("What about Dubai", 300, "barge_in", "rules"),
        ("mm", 900, "barge_in", "duration"),
    ],
)
def test_turn_taking_rules(text: str, ms: float, verdict: str, by: str) -> None:
    ruled = turn_taking.by_rules(text, ms, barge_in_ms=600)
    assert ruled is not None and (ruled.verdict, ruled.by) == (verdict, by)


async def test_unclear_words_go_to_the_decision_model_and_unsure_means_barge_in() -> None:
    sure = DecisionService(FakeDecisionProvider(rules=lambda s, q, o: ("yes", 0.95)))
    unsure = DecisionService(FakeDecisionProvider(rules=lambda s, q, o: ("yes", 0.5)))
    assert (await turn_taking.decide("fair enough", 300, 600, sure)).verdict == "backchannel"
    assert (await turn_taking.decide("fair enough", 300, 600, unsure)).verdict == "barge_in"
    assert (await turn_taking.decide("fair enough", 300, 600, None)).by == "fallback"


# --- the session -----------------------------------------------------------------------------------------------------
async def test_push_to_talk_metric_question_is_acknowledged_then_answered(finance: Any) -> None:
    session, wire, stt, _tts, _ = make(finance, ["What is our runway?"])
    await session.start()
    await session.control({"type": "ptt_start"})
    await session.audio(wav_bytes("runway"))
    await session.control({"type": "ptt_end"})
    await _until(lambda: any(m.get("lane") == "answer" for m in wire.of("say")))
    await _until(lambda: session.metrics.turns and session.metrics.turns[-1].first_answer_audio_ms is not None)
    assert wire.of("transcript")[0]["text"] == "What is our runway?"
    says = wire.of("say")
    assert says[0] == {"type": "say", "lane": "conversation", "text": "Checking that now.", "run_id": None}
    assert any("runway" in m["text"].lower() and m["lane"] == "answer" for m in says)
    assert wire.audio and stt.heard[0] > IN_RATE  # the whole fixture reached the STT
    turn = session.metrics.turns[-1]
    assert turn.first_audio_lane == "conversation" and turn.first_audio_ms is not None
    assert turn.first_answer_audio_ms is not None and turn.first_answer_audio_ms >= turn.first_audio_ms
    await session.close()


async def test_duplex_finds_the_end_of_speech_by_itself(finance: Any) -> None:
    session, wire, *_ = make(finance, ["What is our runway?"], mode="duplex")
    await session.start()
    await stream(session, wav_bytes("runway"))
    await _until(lambda: bool(wire.of("transcript")))
    assert [m["speech"] for m in wire.of("vad")] == [True, False]
    await _until(lambda: any(m.get("lane") == "answer" for m in wire.of("say")))
    await session.close()


async def test_long_speech_while_speaking_is_a_barge_in(finance: Any) -> None:
    session, wire, _, tts, _ = make(finance, ["Wait, stop. What about two hires instead?"], mode="duplex")
    await session.start()
    session.speaking_until = session.clock() + 30  # FounderOS is mid-sentence
    await session._says.put(SimpleNamespace(lane="answer", text="queued", run_id=None, turn=None, epoch=session.epoch))  # type: ignore[arg-type]
    await stream(session, wav_bytes("stop_wait"))
    kinds = [m["type"] for m in wire.messages if m["type"] in ("pause", "interrupt", "resume")]
    assert kinds[:2] == ["pause", "interrupt"] and "resume" not in kinds
    barge = session.metrics.barge_ins[-1]
    assert barge.verdict == "barge_in" and barge.by == "duration"
    assert barge.paused_ms is not None and barge.stopped_ms is not None and barge.stopped_ms >= barge.paused_ms
    assert "queued" not in tts.spoken  # what was waiting to be said was dropped
    await session.control({"type": "playback_stopped", "flush_ms": 12.5})
    assert barge.client_flush_ms == 12.5
    await _until(lambda: bool(wire.of("transcript")))  # and the words became the next turn
    await session.close()


async def test_a_backchannel_while_speaking_resumes_the_speech(finance: Any) -> None:
    session, wire, *_ = make(finance, ["Uh-huh."], mode="duplex", barge_in_ms=3000)
    await session.start()
    session.speaking_until = session.clock() + 30
    await stream(session, wav_bytes("uh_huh"))
    await _until(lambda: bool(wire.of("resume")))
    assert not wire.of("interrupt") and not wire.of("turn")  # no new turn: the founder was only listening
    assert session.metrics.barge_ins[-1].verdict == "backchannel"
    await session.close()


async def test_push_to_talk_while_speaking_stops_at_once(finance: Any) -> None:
    session, wire, *_ = make(finance, ["What is our runway?"])
    await session.start()
    session.speaking_until = session.clock() + 30
    await session.control({"type": "ptt_start"})
    assert wire.of("interrupt") and session.metrics.barge_ins[-1].stopped_ms is not None
    await session.close()


async def test_the_conversation_lane_never_speaks_a_figure(finance: Any) -> None:
    session, _, _, tts, _ = make(finance, [])
    await session.start()
    await session._say("conversation", "Your runway is 10.65 months.", None, None)
    await session._say("answer", "Your runway is 10.65 months.", None, None)
    await _until(lambda: ON_SCREEN in tts.spoken and "Your runway is 10.65 months." in tts.spoken)
    # The lane's line was replaced; the checked answer may say its figure.
    assert tts.spoken.count("Your runway is 10.65 months.") == 1
    await session.close()


async def test_quiet_mode_silences_speech(finance: Any) -> None:
    session, wire, _, tts, manager = make(finance, ["What is our runway?"])
    await session.start()
    await asyncio.sleep(0.05)
    tts.spoken.clear()
    await session.control({"type": "quiet", "quiet": True})
    await session.control({"type": "text", "text": "What is our runway?"})
    await _until(lambda: bool(wire.of("turn")))
    run_id = wire.of("turn")[0]["outcome"]["run_id"]
    await manager.orchestrator.runs[run_id].task  # type: ignore[misc]
    await asyncio.sleep(0.1)
    assert tts.spoken == [] and not wire.of("say")
    await session.close()


async def test_a_turn_during_a_run_goes_through_the_classifier(finance: Any) -> None:
    provider = slow_provider()
    session, wire, *_ = make(finance, [], provider=provider)
    await session.start()
    await session.control({"type": "text", "text": "Should we expand the team this year?"})
    await _until(lambda: bool(wire.of("turn")))
    await session.control({"type": "text", "text": "What is our churn?"})
    await _until(lambda: len(wire.of("turn")) == 2)
    assert wire.of("turn")[1]["outcome"]["kind"] == "new_question"  # queued, not a second run
    provider.release.set()
    await session.close()


async def test_approve_by_voice(finance: Any) -> None:
    provider = slow_provider()
    session, _wire, _, tts, manager = make(finance, [], provider=provider, approval_policy="always")
    await session.start()
    await session.control({"type": "text", "text": "Should we expand the team this year?"})
    await _until(lambda: session.offers.approval_run is not None)
    await _until(lambda: any("Say approve" in s for s in tts.spoken))
    run = manager.orchestrator.runs[session.offers.approval_run or ""]
    await session.control({"type": "text", "text": "Approve"})
    await _until(lambda: run.approval.is_set())
    assert run.approved is True
    provider.release.set()
    await run.task  # type: ignore[misc]
    await session.close()


async def test_the_canvas_stream_and_the_voice_both_get_the_whole_answer(finance: Any) -> None:
    session, wire, *_ = make(finance, [])
    await session.start()
    await session.control({"type": "text", "text": "What is our runway?"})
    await _until(lambda: bool(wire.of("turn")))
    run = session.manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]]
    canvas = []
    while (piece := await run.deltas.get()) is not None:  # what /api/runs/{id}/stream reads
        canvas.append(piece)
    await _until(lambda: any(m.get("lane") == "answer" for m in wire.of("say")))
    await asyncio.sleep(0.05)
    spoken = [m["text"] for m in wire.of("say") if m["lane"] == "answer"]
    # The canvas has the whole answer with its exact figure; the voice says the outcome, rounded (founder decision B).
    assert "".join(canvas).startswith("Runway (actual burn) is 10.65 months")
    assert spoken[0] == "Your runway is about ten and a half months."
    await session.close()


async def test_a_reconnect_does_not_repeat_old_narration(finance: Any) -> None:
    first, wire, _, _, manager = make(finance, [])
    await first.start()
    await first.control({"type": "text", "text": "What is our runway?"})
    await _until(lambda: bool(wire.of("turn")))
    await manager.orchestrator.runs[wire.of("turn")[0]["outcome"]["run_id"]].task  # type: ignore[misc]
    await first.close()
    again = Wire()
    second = VoiceSession(manager, FakeSTT(), FakeTTS(), EnergyVAD(), again.send, session_id=first.session_id)
    await second.start()
    await asyncio.sleep(0.2)
    assert not again.of("say")
    await second.close()


# --- helpers ---------------------------------------------------------------------------------------------------------
def test_speech_text_and_chunks() -> None:
    assert for_speech("Runway is 10.65 months [metrics/runway] and churn 1.5 %.") == (
        "Runway is 10.65 months and churn 1.5 percent."
    )
    long = "The full model is $30,000.00 up front and $32,347.24 a month, reducing runway by 2.07 months; confirm it."
    chunks = speech_chunks(long)
    assert len(chunks) >= 2 and " ".join(chunks) == long
    assert speech_chunks("Checking that now.") == ["Checking that now."]


def test_short_lines_are_synthesised_once() -> None:
    inner = FakeTTS()
    cached = CachedTTS(inner)
    cached.synthesize("Checking that now.")
    cached.synthesize("Checking that now.")
    assert inner.spoken == ["Checking that now."]


def test_metrics_summary_has_p50s() -> None:
    metrics = VoiceMetrics()
    from app.voice.metrics import BargeIn, TurnMetric

    for ms in (800.0, 900.0, 1000.0):
        metrics.turns.append(TurnMetric(first_audio_ms=ms, first_audio_lane="conversation", stt_ms=200.0))
    metrics.barge_ins.append(BargeIn(paused_ms=60.0, stopped_ms=640.0))
    summary = metrics.summary()
    assert summary["p50_ms"]["first_audio"] == 900.0 and summary["p50_ms"]["barge_in_stop"] == 640.0


# --- the API ---------------------------------------------------------------------------------------------------------
@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings.model_copy(update={"auto_load_sample_data": True}))) as c:
        yield c


def test_voice_status_reports_engines_and_vram(client: TestClient) -> None:
    client.app.state.voice.load()  # type: ignore[attr-defined]
    body = client.get("/api/voice/status").json()
    assert body["ready"] is True and body["stt"]["name"] == "fake" and body["tts"]["name"] == "fake"
    assert set(body["vram_gb"]) >= {"total", "used_now", "before_voice", "after_voice", "added_by_voice"}
    assert client.get("/api/voice/metrics").json()["turns"] == 0


def test_websocket_push_to_talk_turn(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice?mode=ptt") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready" and ready["sample_rate_out"] == 24000
        ws.send_text(json.dumps({"type": "ptt_start"}))
        data = wav_bytes("runway")
        for i in range(0, len(data), 4096):  # as a browser sends it
            ws.send_bytes(data[i : i + 4096])
        ws.send_text(json.dumps({"type": "ptt_end"}))
        seen: list[str] = []
        audio = 0
        for _ in range(400):
            message = ws.receive()
            if message.get("bytes"):
                audio += 1
                continue
            data = json.loads(message["text"])
            seen.append(data["type"])
            if data["type"] == "say" and data["lane"] == "answer":
                break
        assert "transcript" in seen and "turn" in seen and audio > 0
    assert client.get("/api/voice/metrics").json()["turns"] == 1


def test_websocket_refuses_other_origins(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/voice", headers={"origin": "http://evil.example"}) as ws,
    ):
        ws.receive_json()
