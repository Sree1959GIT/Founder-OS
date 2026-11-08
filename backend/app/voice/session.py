"""One voice connection (PRD F5): microphone frames in, the two lanes spoken back, barge-in handled.

The voice drives the existing conversation lane, never the agents directly:
- a finished utterance goes through `ConversationManager.turn`, so a mid-run turn is classified as before (queue,
  amendment, stop, backchannel, answer now);
- the conversation lane's narration, status and assumption questions are spoken, but a lane line with a figure in it
  is never spoken (the screen shows it): the voice says no unverified number;
- the inference lane's answer is spoken sentence by sentence as the Advisor's sentence gate lets each one out;
- quiet mode silences all speech; transcripts and the canvas carry on.

Transport-agnostic: the WebSocket endpoint feeds `audio()` and `control()`, and `send` carries JSON dicts and
24 kHz int16 PCM bytes back. Tests drive it with WAV fixtures and fake STT/TTS.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger

from app.agents.runtime import single_metric
from app.agents.verifier import extract_figures, split_sentences
from app.conversation.manager import ConversationError, ConversationManager
from app.voice.audio import FRAME_MS, IN_RATE, OUT_RATE, FrameBuffer, float_to_pcm16, pcm16_to_float
from app.voice.metrics import BargeIn, TurnMetric, VoiceMetrics
from app.voice.stt import STT
from app.voice.tts import TTS, for_speech, speech_chunks
from app.voice.turn_taking import decide
from app.voice.vad import VAD, Endpointer

Sender = Callable[[dict[str, Any] | bytes], Awaitable[None]]

CHUNK_SAMPLES = OUT_RATE // 10  # 100 ms of audio per binary message
PREROLL_MS = 200  # audio kept from before speech was detected, so the first syllable reaches the STT
MAX_UTTERANCE_S = 30
ON_SCREEN = "I've put that on screen."
ACK_METRIC = "Checking that now."
ACK_TEAM = "On it. I'll tell you how the team is doing as it works."
ACKS = (ACK_METRIC, ACK_TEAM, ON_SCREEN, "Okay, I'll stop.", "Running it now.", "Dropped.", "Holding the team back.")
_APPROVE = re.compile(
    r"^(yes|yeah|approve|approved|go|go ahead|run it|approve and run|do it)\b[\s.!,]*(please)?[.!]*$", re.I
)
_HOLD = re.compile(r"^(no|hold|hold it|hold (the team )?back|don't run it|reject)\b[\s.!,]*$", re.I)
_ASK_IT = re.compile(r"^(ask it( now)?|yes,? ask it|go ahead and ask)\b[\s.!,]*$", re.I)
_DROP_IT = re.compile(r"^(drop it|skip it|no,? drop it)\b[\s.!,]*$", re.I)
_RESTART = re.compile(r"^(restart|yes,? restart|restart (it|with my change))\b[\s.!,]*$", re.I)
_KEEP = re.compile(r"^(keep (it )?going|no,? keep going|carry on)\b[\s.!,]*$", re.I)


@dataclass
class VoiceConfig:
    mode: str = "ptt"  # ptt | duplex
    vad_threshold: float = 0.5
    end_silence_ms: float = 400
    barge_in_ms: float = 600
    partial_interval_ms: float = 0  # 0: no partial transcripts
    decision_timeout_s: float = 0.4


@dataclass
class _Say:
    lane: str  # conversation | answer
    text: str
    run_id: str | None
    turn: TurnMetric | None
    epoch: int


@dataclass
class _Offers:
    queue_id: str | None = None
    amendment_id: str | None = None
    approval_run: str | None = None
    voiced_runs: set[str] = field(default_factory=set)


class VoiceSession:
    def __init__(
        self,
        manager: ConversationManager,
        stt: STT,
        tts: TTS,
        vad: VAD,
        send: Sender,
        *,
        session_id: str | None = None,
        config: VoiceConfig | None = None,
        metrics: VoiceMetrics | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.manager = manager
        self.stt, self.tts, self.vad = stt, tts, vad
        self.send = send
        self.config = config or VoiceConfig()
        self.metrics = metrics or VoiceMetrics()
        self.clock = clock
        self.session_id = manager.session(session_id).id
        self.endpointer = Endpointer(self.config.vad_threshold, silence_ms=self.config.end_silence_ms)
        self.frames = FrameBuffer()
        self.preroll: deque[np.ndarray] = deque(maxlen=max(1, round(PREROLL_MS / FRAME_MS)))
        self.arrivals: deque[float] = deque(maxlen=4096)  # arrival time per frame index (index - offset)
        self.arrival_offset = 0
        self.utterance: list[np.ndarray] = []
        self.ptt_active = False
        self.state = "idle"
        self.epoch = 0  # bumped on every interrupt: audio of an older epoch is dropped
        self.speaking_until = 0.0
        self.paused_at: float | None = None
        self.barge: BargeIn | None = None
        self.interrupted_for_current = False
        self.offers = _Offers()
        self.current_turn: TurnMetric | None = None
        self._ends: dict[str, float] = {}  # turn id -> end of the founder's speech
        self._says: asyncio.Queue[_Say] = asyncio.Queue()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._partial_busy = False
        self._last_partial = 0.0
        self._closed = False

    # ------------------------------------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._spawn(self._speaker())
        self._spawn(self._listen_to_lane())
        self._spawn(asyncio.to_thread(self._warm_acks))
        await self._set_state("listening" if self.config.mode == "duplex" else "idle")

    async def close(self) -> None:
        self._closed = True
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    def _spawn(self, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(_log_failure)
        return task

    def _warm_acks(self) -> None:
        for line in ACKS:
            with contextlib.suppress(Exception):
                self.tts.synthesize(line)

    async def _emit(self, message: dict[str, Any] | bytes) -> None:
        if self._closed:
            return
        try:
            await self.send(message)
        except Exception:  # the socket closed under us: the session ends with it
            self._closed = True

    async def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            await self._emit({"type": "state", "state": state})

    def speaking(self) -> bool:
        return self.paused_at is not None or self.clock() < self.speaking_until

    @property
    def quiet(self) -> bool:
        session = self.manager.sessions.get(self.session_id)
        return bool(session and session.quiet)

    # ------------------------------------------------------------------------------------------------ input
    async def control(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "ptt_start":
            if self.speaking():
                await self._barge_in_now("push-to-talk")
            self.ptt_active = True
            self.utterance = []
            await self._set_state("listening")
        elif kind == "ptt_end":
            if self.ptt_active:
                self.ptt_active = False
                samples = np.concatenate(self.utterance) if self.utterance else np.zeros(0, dtype=np.float32)
                self.utterance = []
                self._spawn(self._utterance(samples, self.clock(), samples.size * 1000 / IN_RATE, paused=False))
        elif kind == "mode" and message.get("mode") in ("ptt", "duplex"):
            self.config.mode = str(message["mode"])
            self.endpointer.reset()
            self.utterance = []
            await self._set_state("listening" if self.config.mode == "duplex" else "idle")
        elif kind == "quiet":
            self.manager.set_quiet(self.session_id, bool(message.get("quiet")))
            if self.quiet:
                await self._interrupt("quiet")
        elif kind == "playback_stopped" and self.barge is not None:
            flushed = message.get("flush_ms")
            if isinstance(flushed, int | float):
                self.barge.client_flush_ms = float(flushed)
        elif kind == "text" and str(message.get("text", "")).strip():
            self._spawn(self._turn(str(message["text"]).strip(), self.clock(), None))

    async def audio(self, data: bytes) -> None:
        now = self.clock()
        if self.config.mode == "ptt":
            if self.ptt_active:
                self.utterance.append(pcm16_to_float(data))
                if sum(u.size for u in self.utterance) > MAX_UTTERANCE_S * IN_RATE:
                    await self.control({"type": "ptt_end"})
            return
        for frame in self.frames.push(data):
            await self._frame(frame, now)

    async def _frame(self, frame: np.ndarray, now: float) -> None:
        if len(self.arrivals) == self.arrivals.maxlen:
            self.arrival_offset += 1
        self.arrivals.append(now)
        probability = self.vad.probability(frame)
        event = self.endpointer.push(probability)
        if not self.endpointer.in_speech and event is None:
            self.preroll.append(frame)
            return
        if event is not None and event.kind == "start":
            self.utterance = [*self.preroll, frame]
            self.preroll.clear()
            self.interrupted_for_current = False
            if self.speaking():
                await self._pause(self._arrival(event.frame_index))
            await self._emit({"type": "vad", "speech": True})
            return
        if event is not None and event.kind == "end":
            samples = np.concatenate(self.utterance) if self.utterance else np.zeros(0, dtype=np.float32)
            self.utterance = []
            end_t = self._arrival(event.frame_index)
            speech_ms = samples.size * 1000 / IN_RATE
            paused = self.paused_at is not None and not self.interrupted_for_current
            await self._emit({"type": "vad", "speech": False})
            self._spawn(self._utterance(samples, end_t, speech_ms, paused=paused))
            return
        self.utterance.append(frame)
        if sum(u.size for u in self.utterance) > MAX_UTTERANCE_S * IN_RATE:
            self.endpointer.reset()
            self.utterance = []
            return
        long_enough = self.endpointer.speech_ms() >= self.config.barge_in_ms
        if self.paused_at is not None and not self.interrupted_for_current and long_enough:
            self.interrupted_for_current = True
            if self.barge is not None:
                self.barge.verdict, self.barge.by = "barge_in", "duration"
            await self._interrupt("barge-in")
        self._maybe_partial(now)

    def _arrival(self, index: int) -> float:
        position = index - self.arrival_offset
        if 0 <= position < len(self.arrivals):
            return self.arrivals[position]
        return self.clock()

    def _maybe_partial(self, now: float) -> None:
        interval = self.config.partial_interval_ms
        if not interval or self._partial_busy or (now - self._last_partial) * 1000 < interval or not self.utterance:
            return
        self._partial_busy, self._last_partial = True, now
        samples = np.concatenate(self.utterance)

        async def run() -> None:
            try:
                heard = await asyncio.to_thread(self.stt.transcribe, samples)
                if heard.text and self.endpointer.in_speech:
                    await self._emit({"type": "partial", "text": heard.text})
            finally:
                self._partial_busy = False

        self._spawn(run())

    # ------------------------------------------------------------------------------------------------ barge-in
    async def _pause(self, onset: float) -> None:
        self.paused_at = self.clock()
        self.barge = BargeIn(session_id=self.session_id)
        self.barge.paused_ms = (self.paused_at - onset) * 1000
        self._onset = onset
        await self._emit({"type": "pause"})

    async def _barge_in_now(self, by: str) -> None:
        self.barge = BargeIn(session_id=self.session_id, verdict="barge_in", by=by)
        self._onset = self.clock()
        self.barge.paused_ms = 0.0
        await self._interrupt("barge-in")

    async def _interrupt(self, reason: str) -> None:
        """Stop speaking now: drop queued lines, drop audio being made, tell the client to flush its buffer."""
        self.epoch += 1
        while not self._says.empty():
            self._says.get_nowait()
        was_speaking = self.speaking()
        self.speaking_until = 0.0
        self.paused_at = None
        if self.barge is not None and self.barge.stopped_ms is None and reason == "barge-in":
            self.barge.stopped_ms = (self.clock() - getattr(self, "_onset", self.clock())) * 1000
            self.metrics.barge_ins.append(self.barge)
            await self._emit({"type": "metrics", "barge_in": self.barge.as_dict()})
        await self._emit({"type": "interrupt", "reason": reason})
        if was_speaking or reason == "barge-in":
            await self._set_state("interrupted")

    async def _resume(self) -> None:
        if self.paused_at is not None:
            self.speaking_until += self.clock() - self.paused_at
            self.paused_at = None
        await self._emit({"type": "resume"})
        await self._set_state("speaking")

    # ------------------------------------------------------------------------------------------------ turns
    async def _utterance(self, samples: np.ndarray, end_t: float, speech_ms: float, *, paused: bool) -> None:
        if samples.size < IN_RATE // 10:  # under 100 ms: a click
            if paused:
                await self._resume()
            else:
                await self._set_state("listening" if self.config.mode == "duplex" else "idle")
            return
        await self._set_state("thinking")
        heard = await asyncio.to_thread(self.stt.transcribe, samples)
        await self._emit({"type": "transcript", "text": heard.text, "final": True, "stt_ms": round(heard.ms, 1)})
        if paused:
            verdict = await decide(
                heard.text,
                speech_ms,
                self.config.barge_in_ms,
                self.manager.orchestrator.decisions,
                self.config.decision_timeout_s,
            )
            if self.barge is not None:
                self.barge.verdict, self.barge.by, self.barge.text = verdict.verdict, verdict.by, heard.text
            if verdict.verdict == "backchannel":
                if self.barge is not None:
                    self.metrics.barge_ins.append(self.barge)
                await self._resume()
                return
            await self._interrupt("barge-in")
        if not heard.text.strip():
            await self._set_state("listening" if self.config.mode == "duplex" else "idle")
            return
        await self._turn(heard.text.strip(), end_t, heard.ms, speech_ms)

    async def _turn(self, text: str, end_t: float, stt_ms: float | None, speech_ms: float = 0.0) -> None:
        turn = TurnMetric(session_id=self.session_id, mode=self.config.mode, text=text, speech_ms=speech_ms)
        turn.stt_ms = stt_ms
        self.metrics.turns.append(turn)
        self.current_turn = turn
        self._ends[turn.id] = end_t
        if len(self._ends) > 200:
            self._ends.pop(next(iter(self._ends)))
        if await self._voice_command(text, turn):
            return
        outcome = await self.manager.turn(self.session_id, text)
        turn.turn_ms = (self.clock() - end_t) * 1000
        turn.kind = outcome.kind or "run"
        await self._emit({"type": "turn", "outcome": outcome.model_dump(mode="json")})
        if outcome.kind is None and outcome.run_id:
            self.offers.approval_run = None
            await self._say("conversation", ACK_METRIC if single_metric(text) else ACK_TEAM, None, turn)
            self._spawn(self._speak_answer(outcome.run_id, turn))
        elif outcome.reply:
            await self._say("conversation", outcome.reply, outcome.run_id, turn)
        if outcome.amendment_id:
            self.offers.amendment_id = outcome.amendment_id
        if outcome.kind == "stop":
            await self._interrupt("stop")

    async def _voice_command(self, text: str, turn: TurnMetric) -> bool:
        """Spoken answers to what is on offer: approve the team, ask a queued question, restart with a change."""
        orchestrator = self.manager.orchestrator
        run_id = self.offers.approval_run
        if run_id and (_APPROVE.match(text) or _HOLD.match(text)):
            approve = bool(_APPROVE.match(text))
            if orchestrator.approve(run_id, approved=approve):
                self.offers.approval_run = None
                turn.kind = "approved" if approve else "held"
                await self._say(
                    "conversation", "Running it now." if approve else "Holding the team back.", run_id, turn
                )
                return True
        if self.offers.queue_id and (_ASK_IT.match(text) or _DROP_IT.match(text)):
            accept = bool(_ASK_IT.match(text))
            try:
                answer = self.manager.answer_queue(self.session_id, self.offers.queue_id, accept)
            except ConversationError:
                self.offers.queue_id = None
                return False
            self.offers.queue_id = None
            turn.kind = "queue_asked" if accept else "queue_dropped"
            new_run = answer.get("run_id") if accept else None
            await self._say("conversation", "Running it now." if accept else "Dropped.", new_run, turn)
            if new_run:
                self._spawn(self._speak_answer(str(new_run), turn))
            return True
        if self.offers.amendment_id and (_RESTART.match(text) or _KEEP.match(text)):
            accept = bool(_RESTART.match(text))
            try:
                answer = self.manager.answer_amendment(self.session_id, self.offers.amendment_id, accept)
            except ConversationError:
                self.offers.amendment_id = None
                return False
            self.offers.amendment_id = None
            turn.kind = "restarted" if accept else "kept"
            new_run = answer.get("run_id") if accept else None
            await self._say("conversation", "Running it now." if accept else "Okay, the team carries on.", None, turn)
            if new_run:
                self._spawn(self._speak_answer(str(new_run), turn))
            return True
        return False

    async def _speak_answer(self, run_id: str, turn: TurnMetric) -> None:
        """The inference lane: the Advisor's checked sentences, spoken as each one is let out."""
        run = self.manager.orchestrator.runs.get(run_id)
        if run is None:
            return
        self.offers.voiced_runs.add(run_id)
        buffer = ""
        said = run.deltas.tap()  # the canvas reads the queue itself; the voice its own copy
        while True:
            delta = await said.get()
            if delta is None:
                break
            buffer += delta
            pieces = split_sentences(buffer)
            if len(pieces) > 1:
                done, buffer = pieces[:-1], pieces[-1]
                for sentence in done:
                    if sentence.strip():
                        await self._say("answer", sentence.strip(), run_id, turn)
        if buffer.strip():
            await self._say("answer", buffer.strip(), run_id, turn)

    async def _say(self, lane: str, text: str, run_id: str | None, turn: TurnMetric | None) -> None:
        if self.quiet or not text.strip():
            return
        if lane == "conversation" and extract_figures(text):
            text = ON_SCREEN  # the conversation lane never speaks a number; the screen has the checked one
        if lane == "answer":
            # The answer has begun: older narration still waiting to be spoken is out of date.
            kept = [s for s in _drain(self._says) if s.lane == "answer"]
            for s in kept:
                self._says.put_nowait(s)
        await self._says.put(_Say(lane, text, run_id, turn, self.epoch))

    async def _speaker(self) -> None:
        while True:
            item = await self._says.get()
            if item.epoch != self.epoch or self.quiet:
                continue
            spoken = for_speech(item.text)
            if not spoken:
                continue
            announced = False
            for chunk in speech_chunks(spoken):
                started = self.clock()
                try:
                    audio = await asyncio.to_thread(self.tts.synthesize, chunk)
                except Exception as exc:
                    logger.warning("TTS failed: {}", exc)
                    await self._emit({"type": "error", "message": f"speech failed: {exc}"})
                    break
                if item.epoch != self.epoch or self.quiet:
                    break  # interrupted while it was being made
                if not announced:
                    announced = True
                    await self._first_audio(item, started)
                await self._set_state("speaking")
                await self._play(audio, item.epoch)

    async def _first_audio(self, item: _Say, started: float) -> None:
        now = self.clock()
        turn = item.turn
        if turn is not None:
            end_t = self._ends.get(turn.id, now)
            if turn.first_audio_ms is None:
                turn.first_audio_ms = (now - end_t) * 1000
                turn.first_audio_lane = item.lane
                turn.tts_first_ms = (now - started) * 1000
            if item.lane == "answer" and turn.first_answer_audio_ms is None:
                turn.first_answer_audio_ms = (now - end_t) * 1000
            await self._emit({"type": "metrics", "turn": turn.as_dict()})
        await self._emit({"type": "say", "lane": item.lane, "text": item.text, "run_id": item.run_id})

    async def _play(self, audio: np.ndarray, epoch: int) -> None:
        now = self.clock()
        pcm = float_to_pcm16(audio)
        step = CHUNK_SAMPLES * 2
        for i in range(0, len(pcm), step):
            if epoch != self.epoch:
                return
            await self._emit(pcm[i : i + step])
        self.speaking_until = max(self.speaking_until, now) + audio.size / OUT_RATE
        self._spawn(self._idle_after(self.speaking_until, epoch))

    async def _idle_after(self, until: float, epoch: int) -> None:
        await asyncio.sleep(max(0.0, until - self.clock()))
        if (
            epoch == self.epoch
            and self.paused_at is None
            and self.clock() >= self.speaking_until
            and self._says.empty()
        ):
            await self._set_state("listening" if self.config.mode == "duplex" else "idle")

    # ------------------------------------------------------------------------------------------------ lane events
    async def _listen_to_lane(self) -> None:
        """Narration, status and offers for this session, from the same bus the canvas reads."""
        async for event in self.manager.bus.subscribe():
            if event.data.get("session_id") != self.session_id and event.type != "team.proposed":
                continue
            if event.type == "team.proposed":
                if event.run_id == self.manager.sessions[self.session_id].run_id and event.data.get("needs_approval"):
                    self.offers.approval_run = event.run_id
                continue
            if event.type == "queue.offered":
                self.offers.queue_id = event.data.get("queue_id")
                await self._say("conversation", "Your next question is ready. Say ask it, or drop it.", None, None)
                continue
            if event.type == "recap" and event.run_id in self.offers.voiced_runs:
                continue  # the answer itself was spoken
            if event.type in ("narration", "recap"):
                text = str(event.data.get("text", ""))
                if "approval" in text:
                    text += " Say approve, or hold it."
                await self._say("conversation", text, event.run_id, self.current_turn)


def _drain(queue: asyncio.Queue[_Say]) -> list[_Say]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _log_failure(task: asyncio.Task[Any]) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.opt(exception=task.exception()).error("Voice task failed")
