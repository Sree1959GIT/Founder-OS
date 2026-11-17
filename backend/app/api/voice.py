"""`/ws/voice` (PRD F5: PCM audio both ways, barge-in) and `/api/voice/*` (status, VRAM, latency metrics).

Protocol, one WebSocket per browser tab:
- client to server: binary frames of 16 kHz mono int16 PCM; JSON `{"type": "ptt_start" | "ptt_end" | "mode" |
  "quiet" | "playback_stopped" | "text"}`;
- server to client: binary frames of 24 kHz mono int16 PCM; JSON `ready`, `state`, `vad`, `partial`, `transcript`,
  `turn`, `say`, `pause`, `resume`, `interrupt`, `metrics`, `error`.
A browser may only connect from an allowed origin (CORS does not cover WebSockets).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from loguru import logger

from app.voice.service import VoiceService
from app.voice.session import VoiceSession

router = APIRouter(tags=["voice"])
MAX_FRAME_BYTES = 256 * 1024  # a browser sends about 4 KB at a time; a larger frame is dropped


def _service(app: Any) -> VoiceService:
    service: VoiceService = app.state.voice
    return service


@router.get("/api/voice/status")
async def status(request: Request) -> dict[str, Any]:
    """Which engines run where (GPU or CPU), why one fell back, and VRAM before and after the voice models."""
    return _service(request.app).status()


@router.get("/api/voice/metrics")
async def voice_metrics(request: Request) -> dict[str, Any]:
    """Per-turn latency (end of speech to first audio, to first answer audio) and barge-in stop times, with p50s."""
    return _service(request.app).metrics.summary()


@router.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket) -> None:
    app = websocket.app
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in app.state.base_settings.cors_origins:
        await websocket.close(code=1008, reason="origin not allowed")
        return
    await websocket.accept()
    service = _service(app)
    if not service.settings.voice_enabled:
        await websocket.send_json({"type": "error", "message": "voice is off (VOICE_ENABLED=false)"})
        await websocket.close(code=1000)
        return
    engines = await service.ensure_loaded()
    if engines.stt is None or engines.tts is None:
        await websocket.send_json({"type": "error", "message": "; ".join(engines.notes) or "voice engines missing"})
        await websocket.close(code=1011)
        return
    lock = asyncio.Lock()

    async def send(message: dict[str, Any] | bytes) -> None:
        async with lock:
            if isinstance(message, bytes):
                await websocket.send_bytes(message)
            else:
                await websocket.send_text(json.dumps(message))

    config = service.config()
    mode = websocket.query_params.get("mode")
    if mode in ("ptt", "duplex"):
        config.mode = mode
    session = VoiceSession(
        app.state.conversation,
        engines.stt,
        engines.tts,
        _fresh_vad(engines.vad),
        send,
        session_id=_session_id(websocket.query_params.get("session_id")),
        config=config,
        metrics=service.metrics,
    )
    await send(
        {
            "type": "ready",
            "session_id": session.session_id,
            "mode": config.mode,
            "sample_rate_in": 16000,
            "sample_rate_out": 24000,
            "status": service.status(),
        }
    )
    await session.start()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data is not None:
                if len(data) <= MAX_FRAME_BYTES:
                    await session.audio(data)
                continue
            text = message.get("text")
            if text:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    await session.control(parsed)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Voice socket failed")
    finally:
        await session.close()


def _session_id(raw: str | None) -> str | None:
    """The conversation to join: the same limits as `/api/conversation/turn` (64 characters, a plain id)."""
    if raw and len(raw) <= 64 and re.fullmatch(r"[A-Za-z0-9_-]+", raw):
        return raw
    return None


def _fresh_vad(shared: Any) -> Any:
    """Silero keeps state per stream: each connection gets its own copy of the small model."""
    try:
        return shared.__class__()
    except Exception:
        return shared
