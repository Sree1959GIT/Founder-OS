"""One voice connection (PRD F5): microphone frames in, a short spoken turn back, barge-in handled.

The voice drives the existing conversation lane, never the agents directly:
- a finished utterance goes through `ConversationManager.turn`, so a mid-run turn is classified as before (queue,
  amendment, stop, backchannel, answer now);
- how the Advisor speaks (founder decision 2026-11-13, PRD §12, `app/voice/spoken.py`): one line on how the team is
  organised, one line a stage on what its agents produced, then a summary of the outcome with an offer of more. The
  on-screen answer is never read aloud, and every spoken number is rounded by code from the verified figure;
- a lane line with a figure in it is never spoken (the screen shows it);
- the founder has the floor: nothing new is played while they are speaking or while their words are being
  understood, and a pause made for older speech is never resumed over newer speech (founder review V7);
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
from app.agents.verifier import extract_figures
from app.conversation.classifier import is_filler
from app.conversation.manager import ConversationManager
from app.voice.audio import FRAME_MS, IN_RATE, OUT_RATE, FrameBuffer, float_to_pcm16, pcm16_to_float, rms
from app.voice.domain import corrected
from app.voice.metrics import BargeIn, TurnMetric, VoiceMetrics
from app.voice.spoken import Segment, metric_lead, summarise, team_line
from app.voice.stt import STT
from app.voice.tts import TTS, for_speech, speech_chunks
from app.voice.turn_taking import TurnVerdict, decide
from app.voice.vad import VAD, Endpointer

Sender = Callable[[dict[str, Any] | bytes], Awaitable[None]]

CHUNK_SAMPLES = OUT_RATE // 10  # 100 ms of audio per binary message
PREROLL_MS = 200  # audio kept from before speech was detected, so the first syllable reaches the STT
MAX_UTTERANCE_S = 30
CLOSE_WAIT_S = 5
FLOOR_WAIT_S = 12  # a room that never goes quiet (a television) must not silence FounderOS for good
ON_SCREEN = "I've put that on screen."
ACK_METRIC = "Checking that now."
ACK_TEAM = "On it."
MISSED = "Sorry, I didn't catch that."
QUEUE_OFFER = "Your next question is ready. Say ask it, or drop it."
QUEUED = "I'll keep that for when this run finishes."  # the lane's reply to a question asked mid-run
STILL_WORKING = "Still working on it."
SAY_AGAIN = "Okay. Say it again."
UNSURE = "I'm not sure I heard that right. If the words on screen are what you said, say yes. If not, say it again."
MAX_ONSET_AGE_S = 2.0  # speech is noticed about 0.1 s after it starts: an older "start" is a clock that went stale
ACKS = (
    ACK_METRIC,
    ACK_TEAM,
    ON_SCREEN,
    MISSED,
    QUEUE_OFFER,
    QUEUED,
    "Running it now.",
    "Dropped.",
    "Holding the team back.",
    STILL_WORKING,
    SAY_AGAIN,
    UNSURE,
)
_APPROVE = re.compile(
    r"^(yes|yeah|approve|approved|go|go ahead|run it|approve and run|do it)\b[\s.!,]*(please)?[.!]*$", re.I
)
_HOLD = re.compile(r"^(no|hold|hold it|hold (the team )?back|don't run it|reject)\b[\s.!,]*$", re.I)
_ASK_IT = re.compile(r"^(ask it( now)?|yes,? ask it|go ahead and ask)\b[\s.!,]*$", re.I)
_DROP_IT = re.compile(r"^(drop it|skip it|no,? drop it)\b[\s.!,]*$", re.I)
_RESTART = re.compile(r"^(restart|yes,? restart|restart (it|with my change))\b[\s.!,]*$", re.I)
_KEEP = re.compile(r"^(keep (it )?going|no,? keep going|carry on)\b[\s.!,]*$", re.I)
# Answers to "Want me to go through the risks?": yes takes the next part on offer, or the part that is named.
_MORE = re.compile(
    r"^(yes|yeah|yep|sure|ok|okay|please|please do|go on|go ahead|continue|carry on|more|tell me( more)?|"
    r"(yes,?\s+)?(go through|what are|tell me|give me|and)?\s*(the|them|those)?\s*"
    r"(risks?|other options|options|detail|details))"
    r"\b[\s.!,?]*(please)?[\s.!?]*$",
    re.I,
)
_NO_MORE = re.compile(
    r"^(no|nope|no thanks|no thank you|not now|that's (all|enough)|skip( it| that)?)\b[\s.!,]*$", re.I
)
_ANSWERED = {
    ("queue", True): "queue_asked",
    ("queue", False): "queue_dropped",
    ("amendment", True): "restarted",
    ("amendment", False): "kept",
}
# Answers to "Did you say: ...?"
_HEARD_RIGHT = re.compile(
    r"^(yes|yeah|yep|yup|correct|right|that's right|i did|exactly)\b[\s.!,]*(i did)?[\s.!]*$", re.I
)
_HEARD_WRONG = re.compile(r"^(no|nope|nah|wrong|that's wrong|i didn't|i did not)\b[\s.!,]*$", re.I)


@dataclass
class VoiceConfig:
    mode: str = "ptt"  # ptt | duplex
    vad_threshold: float = 0.5
    end_silence_ms: float = 400
    # Speech over FounderOS that lasts this long stops it without waiting for the words. Founder re-test R1: a
    # listening noise of up to about a second ("uh-huh", "right") is a backchannel, so it must be able to resume.
    barge_in_ms: float = 1000
    partial_interval_ms: float = 0  # 0: no partial transcripts
    decision_timeout_s: float = 0.4
    # While FounderOS is playing audio, a frame counts as speech only if it is at least this share of the founder's
    # own usual level (learnt from what they say while it is silent). What is left of its own voice after the
    # browser's echo cancelling is far quieter than the founder, so it no longer pauses itself or hears words in its
    # own echo. 0 turns the gate off.
    echo_gate: float = 0.3
    # Founder decision R4: after the opening turn the voice is silent while the team works, except for one short
    # line if the run is still going after this long. 0: never.
    still_working_s: float = 30.0
    # Founder re-test R6: a turn the recogniser is less sure of than this is read back before it is acted on
    # ("Did you say ...?"). 0: never ask.
    confirm_below: float = 0.0


@dataclass
class _Say:
    lane: str  # conversation | answer
    text: str
    run_id: str | None
    turn: TurnMetric | None
    epoch: int
    keep: bool = False  # a reply or an offer: not dropped as out-of-date narration when the answer begins


@dataclass
class _Offers:
    queue_id: str | None = None
    amendment_id: str | None = None
    approval_run: str | None = None
    voiced_runs: set[str] = field(default_factory=set)
    more: list[Segment] = field(default_factory=list)  # what the last summary left on offer, in order


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
        self._onset = 0.0  # when the speech that paused playback began
        self.interrupted_for_current = False
        self.offers = _Offers()
        self.current_turn: TurnMetric | None = None
        self._ends: dict[str, float] = {}  # turn id -> end of the founder's speech
        self._says: asyncio.Queue[_Say] = asyncio.Queue()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._partial_busy = False
        self._last_partial = 0.0
        self._closed = False
        # The founder's floor (founder review V7). `_speech_seq` numbers each stretch of their speech, so a verdict on
        # an older stretch never resumes playback over a newer one; `_floor` is clear while they speak and while
        # their words are being transcribed and answered, and the speaker waits for it.
        self._speech_seq = 0
        self._hearing = 0
        self._floor = asyncio.Event()
        self._floor.set()
        self._missed_last = False
        self._voice_level: float | None = None  # the founder's usual speech level, for the echo gate
        self._levels: list[float] = []  # voiced frames of the utterance being heard, while nothing is playing
        self._answering = 0
        self._answers_idle = asyncio.Event()
        self._answers_idle.set()
        self._unsure: str | None = None  # words read back to the founder ("Did you say ...?"), awaiting yes or no
        self._barge_seq = -1  # the stretch of speech the current barge-in record is about
        self._still_said: set[str] = set()  # runs that have had their one "still working" line
        self._offer_again: Segment | None = None  # the offer already repeated after a listening noise

    # ------------------------------------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._spawn(self._speaker())
        self._spawn(self._listen_to_lane())
        self._spawn(asyncio.to_thread(self._warm_acks))
        await self._set_state("listening" if self.config.mode == "duplex" else "idle")

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            # Bounded: a task that fails to stop must not keep the socket's handler (or a test) waiting for ever.
            _, stuck = await asyncio.wait(tasks, timeout=CLOSE_WAIT_S)
            if stuck:
                logger.warning("voice session closed with {} task(s) still running", len(stuck))

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

    def _update_floor(self) -> None:
        if self.endpointer.in_speech or self.ptt_active or self._hearing > 0:
            self._floor.clear()
        else:
            self._floor.set()

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
            self._speech_seq += 1
            self.utterance = []
            self._update_floor()
            await self._set_state("listening")
        elif kind == "ptt_end":
            if self.ptt_active:
                self.ptt_active = False
                samples = np.concatenate(self.utterance) if self.utterance else np.zeros(0, dtype=np.float32)
                self.utterance = []
                self._hear(samples, self.clock(), samples.size * 1000 / IN_RATE, paused=False)
        elif kind == "mode" and message.get("mode") in ("ptt", "duplex"):
            self.config.mode = str(message["mode"])
            self._reset_endpointer()
            self.ptt_active = False
            self.utterance = []
            self._update_floor()
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
        probability = self._gated(self.vad.probability(frame), frame, now)
        event = self.endpointer.push(probability)
        if not self.endpointer.in_speech and event is None:
            self.preroll.append(frame)
            return
        if event is not None and event.kind == "start":
            self.utterance = [*self.preroll, frame]
            self.preroll.clear()
            self.interrupted_for_current = False
            self._speech_seq += 1
            self._update_floor()
            if self.speaking():
                await self._pause(self._arrival(event.frame_index))
            await self._emit({"type": "vad", "speech": True})
            return
        if event is not None and event.kind == "end":
            self._learn_level()
            samples = np.concatenate(self.utterance) if self.utterance else np.zeros(0, dtype=np.float32)
            self.utterance = []
            end_t = self._arrival(event.frame_index)
            speech_ms = samples.size * 1000 / IN_RATE
            paused = self.paused_at is not None and not self.interrupted_for_current
            await self._emit({"type": "vad", "speech": False})
            self._hear(samples, end_t, speech_ms, paused=paused)
            return
        self.utterance.append(frame)
        if sum(u.size for u in self.utterance) > MAX_UTTERANCE_S * IN_RATE:
            self._reset_endpointer()
            self.utterance = []
            if self.paused_at is not None:  # nothing will come to resume it: never leave the audio paused
                await self._resume()
            self._update_floor()
            return
        long_enough = self.endpointer.speech_ms() >= self.config.barge_in_ms
        if self.paused_at is not None and not self.interrupted_for_current and long_enough:
            self.interrupted_for_current = True
            if self.barge is not None:
                self.barge.verdict, self.barge.by = "barge_in", "duration"
            await self._interrupt("barge-in")
        self._maybe_partial(now)

    def _gated(self, probability: float, frame: np.ndarray, now: float) -> float:
        """The echo gate. While audio is playing, sound much quieter than the founder's own voice is FounderOS
        hearing itself: not speech. While nothing is playing (and for a moment after, for the loudspeaker's tail),
        the founder's level is learnt from their own speech."""
        level = rms(frame)
        playing = self.paused_at is None and now < self.speaking_until
        if playing:
            quiet = self._voice_level is not None and level < self.config.echo_gate * self._voice_level
            return 0.0 if quiet and not self.endpointer.in_speech else probability
        if probability >= self.config.vad_threshold and self.paused_at is None and now > self.speaking_until + 0.3:
            self._levels.append(level)
        return probability

    def _learn_level(self) -> None:
        """After an utterance: the median level of its voiced frames, smoothed over utterances."""
        levels, self._levels = self._levels, []
        if len(levels) * FRAME_MS < 300:
            return
        heard = float(np.median(levels))
        self._voice_level = heard if self._voice_level is None else 0.7 * self._voice_level + 0.3 * heard

    def _reset_endpointer(self) -> None:
        """The endpointer numbers its frames from zero again, so the arrival times must start again with it.
        Founder re-test R2: they did not, and after a switch of mode or a 30 s stretch of sound every later
        barge-in read its onset from a frame minutes old ("paused_ms" of 35,000 to 168,000)."""
        self.endpointer.reset()
        self.arrivals.clear()
        self.arrival_offset = 0

    def _arrival(self, index: int) -> float:
        now = self.clock()
        position = index - self.arrival_offset
        if 0 <= position < len(self.arrivals):
            at = self.arrivals[position]
            # Belt and braces for the same fault: an onset cannot be older than the speech that was just noticed.
            return at if now - at <= MAX_ONSET_AGE_S else now
        return now

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
        self._barge_seq = self._speech_seq
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
            self.barge.stopped_ms = (self.clock() - self._onset) * 1000
            self.metrics.barge_ins.append(self.barge)
            await self._emit({"type": "metrics", "barge_in": self.barge.as_dict()})
        await self._emit({"type": "interrupt", "reason": reason})
        if was_speaking or reason == "barge-in":
            await self._set_state("interrupted")

    async def _resume(self, seq: int | None = None) -> None:
        # Newer speech began after the stretch this verdict is about: that speech owns the pause now. Resuming here
        # played the narration over the founder's question (founder review V7).
        if seq is not None and (seq != self._speech_seq or self.endpointer.in_speech):
            return
        if self.paused_at is not None:
            self.speaking_until += self.clock() - self.paused_at
            self.paused_at = None
        await self._emit({"type": "resume"})
        await self._set_state("speaking")

    # ------------------------------------------------------------------------------------------------ turns
    def _hear(self, samples: np.ndarray, end_t: float, speech_ms: float, *, paused: bool) -> None:
        """The founder stopped speaking: their words keep the floor until they are understood and answered."""
        self._hearing += 1
        self._update_floor()
        self._spawn(self._heard(samples, end_t, speech_ms, paused, self._speech_seq))

    async def _heard(self, samples: np.ndarray, end_t: float, speech_ms: float, paused: bool, seq: int) -> None:
        try:
            await self._utterance(samples, end_t, speech_ms, paused=paused, seq=seq)
        finally:
            self._hearing -= 1
            self._update_floor()

    async def _utterance(
        self, samples: np.ndarray, end_t: float, speech_ms: float, *, paused: bool, seq: int | None = None
    ) -> None:
        if samples.size < IN_RATE // 10:  # under 100 ms: a click
            if paused:
                await self._resume(seq)
            else:
                await self._set_state("listening" if self.config.mode == "duplex" else "idle")
            return
        await self._set_state("thinking")
        heard = await asyncio.to_thread(self.stt.transcribe, samples)
        heard.text = corrected(heard.text)  # a command's opening, repaired by code (founder re-test R6)
        await self._emit(
            {
                "type": "transcript",
                "text": heard.text,
                "final": True,
                "stt_ms": round(heard.ms, 1),
                "confidence": heard.confidence,
            }
        )
        if not paused and self.barge is not None and seq == self._barge_seq and not self.barge.text:
            self.barge.text = heard.text  # a barge-in decided by its length: its words, once they are known
        if paused:
            if self._answers_a_question(heard.text):
                # "Yes" said over the last words of "Stop the team? Say yes to stop." is an answer, not a listening
                # noise: it must reach the lane, not just resume the speech.
                verdict = TurnVerdict("barge_in", "rules")
            else:
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
                await self._resume(seq)
                return
            await self._interrupt("barge-in")
        if not heard.text.strip():
            # Real speech with no words made out: say so, once, instead of losing the turn in silence (V7).
            if speech_ms >= self.config.barge_in_ms and not self._missed_last:
                self._missed_last = True
                await self._emit({"type": "missed"})
                await self._say("conversation", MISSED, None, None, keep=True, first=True)
            await self._set_state("listening" if self.config.mode == "duplex" else "idle")
            return
        self._missed_last = False
        text = await self._sure_of(heard.text.strip(), heard.confidence)
        if text:
            await self._turn(text, end_t, heard.ms, speech_ms)
        else:
            await self._set_state("listening" if self.config.mode == "duplex" else "idle")

    def _answers_a_question(self, text: str) -> bool:
        """The founder is answering something FounderOS asked: its own read-back, the lane's yes/no question, an
        approval, or the offer at the end of a summary."""
        words = text.strip()
        if not words:
            return False
        if self._unsure is not None and (_HEARD_RIGHT.match(words) or _HEARD_WRONG.match(words)):
            return True
        if self.manager.has_question(self.session_id, words):
            return True
        if self.offers.approval_run and (_APPROVE.match(words) or _HOLD.match(words)):
            return True
        return bool(self.offers.more) and bool(_MORE.match(words) or _NO_MORE.match(words))

    async def _sure_of(self, text: str, confidence: float) -> str:
        """The words to act on, or nothing yet (founder re-test R6). A turn the recogniser was unsure of is read back
        first: yes takes it as heard, no drops it, and anything else is simply the founder saying it again."""
        pending, self._unsure = self._unsure, None
        if pending is not None:
            if _HEARD_RIGHT.match(text):
                return pending
            if _HEARD_WRONG.match(text):
                await self._say("conversation", SAY_AGAIN, None, None, keep=True, first=True)
                return ""
            return text
        if confidence >= self.config.confirm_below or not self._worth_asking(text):
            return text
        self._unsure = text
        await self._emit({"type": "unsure", "text": text, "confidence": confidence})
        line = UNSURE if extract_figures(text) else f"Did you say: {text.rstrip('.!? ')}? Say yes, or say it again."
        await self._say("conversation", line, None, None, keep=True, first=True)
        return ""

    def _worth_asking(self, text: str) -> bool:
        """Not a listening noise, and not a plain answer to something on offer: those cost nothing if misheard."""
        if is_filler(text) or len(text.split()) < 2 or self.manager.has_question(self.session_id, text):
            return False
        simple = (_APPROVE, _HOLD, _ASK_IT, _DROP_IT, _RESTART, _KEEP, _MORE, _NO_MORE)
        return not any(pattern.match(text) for pattern in simple)

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
        if outcome.answered:  # "yes" to an offer: recorded as what it did, like the offer's own words
            turn.kind = _ANSWERED[str(outcome.answered["what"]), bool(outcome.answered["accept"])]
        await self._emit({"type": "turn", "text": text, "outcome": outcome.model_dump(mode="json")})
        if outcome.kind == "stop":
            await self._interrupt("stop")  # first, so that "Stopping the team." is said and not dropped with the rest
        if outcome.run_id and (outcome.started_run or outcome.kind is None):
            self.offers.approval_run = None
            self.offers.more = []
            run = self.manager.orchestrator.runs.get(outcome.run_id)
            lookup = single_metric(run.message if run is not None else text)
            ack = outcome.reply or (ACK_METRIC if lookup else ACK_TEAM)
            await self._say("conversation", ack, None, turn, keep=True, first=True)
            self._answer(outcome.run_id, turn)
        elif outcome.reply:
            await self._say("conversation", outcome.reply, outcome.run_id, turn, keep=True, first=True)
        elif (
            outcome.kind == "backchannel"
            and self.offers.more
            and self._offer_again is not self.offers.more[0]
            and not self.manager.session(self.session_id).asked
            and self.manager.state(self.session_id)["running"] is False
        ):
            # Founder re-test R5: "uh-huh" over the summary cut it off before its offer. The offer is said again
            # (once), so the turn still ends with it.
            self._offer_again = self.offers.more[0]
            await self._say("answer", self.offers.more[0].offer, None, turn)
        if outcome.amendment_id:
            self.offers.amendment_id = outcome.amendment_id
        if outcome.answered:
            self.offers.amendment_id = self.offers.queue_id = None

    async def _voice_command(self, text: str, turn: TurnMetric) -> bool:
        """Spoken answers to what is on offer: approve the team, ask a queued question, restart with a change."""
        orchestrator = self.manager.orchestrator
        # The lane's own question comes first ("Stop the team? Say yes to stop.", "Restart with your change?", "Did
        # you mean two people?"): its yes or no goes to the lane, typed or spoken.
        if self.manager.has_question(self.session_id, text):
            return False
        run_id = self.offers.approval_run
        if run_id and (_APPROVE.match(text) or _HOLD.match(text)):
            approve = bool(_APPROVE.match(text))
            if orchestrator.approve(run_id, approved=approve):
                self.offers.approval_run = None
                turn.kind = "approved" if approve else "held"
                await self._say(
                    "conversation", "Running it now." if approve else "Holding the team back.", run_id, turn
                )
                if approve:
                    self._spawn(self._still_working(run_id))
                return True
        if self.offers.queue_id and (_ASK_IT.match(text) or _DROP_IT.match(text)):
            queue_id, self.offers.queue_id = self.offers.queue_id, None
            return await self._offer_answered("queue", queue_id, bool(_ASK_IT.match(text)), turn)
        if self.offers.amendment_id and (_RESTART.match(text) or _KEEP.match(text)):
            amendment_id, self.offers.amendment_id = self.offers.amendment_id, None
            return await self._offer_answered("amendment", amendment_id, bool(_RESTART.match(text)), turn)
        if self.offers.more and (_MORE.match(text) or _NO_MORE.match(text)):
            if _NO_MORE.match(text):
                self.offers.more = []
                turn.kind = "more_declined"
                await self._say("conversation", "Okay. The rest is on screen.", None, turn, keep=True)
                return True
            turn.kind = "more"
            await self._say_more(text, turn)
            return True
        return False

    async def _offer_answered(self, what: str, ref: str, accept: bool, turn: TurnMetric) -> bool:
        """An offer answered by voice goes the way its button does, and the screen is told (founder re-test R8: a
        restart accepted by voice ran, but the canvas was never told and kept showing the old answer)."""
        outcome = self.manager.answer_offer(self.session_id, what, ref, accept)
        if outcome is None:
            return False  # the offer has closed: the words are an ordinary turn
        turn.kind = _ANSWERED[what, accept]
        await self._emit({"type": "turn", "text": turn.text, "outcome": outcome.model_dump(mode="json")})
        await self._say("conversation", outcome.reply, None, turn, keep=True, first=True)
        if accept and outcome.run_id:
            self.offers.more = []
            self._answer(outcome.run_id, turn)
        return True

    async def _still_working(self, run_id: str | None) -> None:
        """Founder decision R4: silent while the team works, but for one short line if it takes long."""
        wait = self.config.still_working_s
        if not wait or run_id is None or run_id in self._still_said:
            return
        self._still_said.add(run_id)
        await asyncio.sleep(wait)
        run = self.manager.orchestrator.runs.get(run_id)
        session = self.manager.sessions.get(self.session_id)
        working = run is not None and run.task is not None and not run.task.done()
        if working and session is not None and session.run_id == run_id:
            await self._say("conversation", STILL_WORKING, run_id, None)

    async def _say_more(self, text: str, turn: TurnMetric) -> None:
        """The next part on offer, or the one the founder named ("go through the risks"); then the next offer."""
        named = next(
            (s for s in self.offers.more if s.key.rstrip("s") in text.lower() and s.key != "rest"), self.offers.more[0]
        )
        self.offers.more.remove(named)
        for line in named.lines:
            await self._say("answer", line, None, turn)
        closing = self.offers.more[0].offer if self.offers.more else "That's the summary. The rest is on screen."
        await self._say("answer", closing, None, turn)

    def _answer(self, run_id: str, turn: TurnMetric) -> None:
        self._answering += 1
        self._answers_idle.clear()
        self._spawn(self._answered(run_id, turn))

    async def _answered(self, run_id: str, turn: TurnMetric) -> None:
        try:
            await self._speak_answer(run_id, turn)
        finally:
            self._answering -= 1
            if self._answering <= 0:
                self._answers_idle.set()

    def _early_metric(self, run_id: str) -> str:
        """A one-metric lookup: its spoken line as soon as the routine has the figure, before the run wraps up."""
        run = self.manager.orchestrator.runs.get(run_id)
        plan = run.plan if run is not None else None
        if plan is None or len(plan.team) != 1 or not plan.team[0].fast_metric:
            return ""
        for event in self.manager.bus.history(run_id):
            card = event.data.get("artifact") if event.type == "agent.artifact" else None
            if card and card.get("kind") == "metric_card":
                data = card.get("data") or {}
                if "label" in data and "unit" in data:
                    return metric_lead(
                        str(data["label"]), data.get("value"), str(data["unit"]), str(data.get("metric", ""))
                    )
        return ""

    async def _speak_answer(self, run_id: str, turn: TurnMetric) -> None:
        """The outcome, said short (founder decision B and C): never the on-screen answer read aloud.

        A summary built by code from the run's result: the outcome, the one thing that matters, then an offer of
        more. A metric's own line is said as soon as its routine has the figure; the rest follows the finished run.
        """
        run = self.manager.orchestrator.runs.get(run_id)
        if run is None or run.task is None:
            return
        self.offers.voiced_runs.add(run_id)
        said_early = ""
        first = asyncio.ensure_future(run.deltas.tap().get())  # the canvas reads the queue itself; this is a copy
        try:
            await asyncio.wait({first, run.task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            first.cancel()
        if not run.task.done():
            said_early = self._early_metric(run_id)
            if said_early:
                await self._say("answer", said_early, run_id, turn)
        await asyncio.wait({run.task})
        result = run.result
        if run.task.cancelled() or run.task.exception() is not None or result is None or result.status != "done":
            return  # the lane says it was cancelled, failed or held back
        spoken = summarise(result)
        for line in spoken.lead:
            if line != said_early:
                await self._say("answer", line, run_id, turn)
        if run_id != self.manager.session(self.session_id).run_id:
            return  # the founder has moved on to another run: its summary owns the offers
        self.offers.more = spoken.more
        session = self.manager.sessions.get(self.session_id)
        waiting = session is not None and any(q.status in ("queued", "offered") for q in session.queue)
        if spoken.more and not waiting:  # one question at a time: a queued question's offer comes first
            await self._say("answer", spoken.more[0].offer, run_id, turn)

    async def _say(
        self,
        lane: str,
        text: str,
        run_id: str | None,
        turn: TurnMetric | None,
        *,
        keep: bool = False,
        first: bool = False,
    ) -> None:
        if self.quiet or not text.strip():
            return
        if lane == "conversation" and extract_figures(text):
            text = ON_SCREEN  # the conversation lane never speaks a number; the screen has the checked one
        waiting = _drain(self._says)
        if lane == "answer":
            # The outcome has begun: older narration still waiting to be spoken is out of date.
            waiting = [s for s in waiting if s.lane == "answer" or s.keep]
        item = _Say(lane, text, run_id, turn, self.epoch, keep or lane == "answer")
        # A reply to what the founder just said comes before narration that was waiting for them to finish.
        for s in [item, *waiting] if first else [*waiting, item]:
            self._says.put_nowait(s)

    async def _speaker(self) -> None:
        while not self._closed:
            item = await self._says.get()
            if not self._floor.is_set():
                # Never start a line while the founder is speaking or being understood. It goes back to the head of
                # the queue, so the reply to what they are saying can still be put in front of it.
                for s in [item, *_drain(self._says)]:
                    self._says.put_nowait(s)
                if await self._floor_free():
                    continue
                item = self._says.get_nowait()  # waited long enough: speak
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
                await self._floor_free()
                if item.epoch != self.epoch or self.quiet:
                    break  # interrupted while it was being made
                if not announced:
                    announced = True
                    await self._first_audio(item, started)
                await self._set_state("speaking")
                await self._play(audio, item.epoch)

    async def _floor_free(self) -> bool:
        """Waits until the founder has finished and been answered. False: still not free after `FLOOR_WAIT_S`."""
        if self._floor.is_set():
            return True
        # Not `asyncio.wait_for`: on Python 3.11 it swallows a cancellation that lands as the wait completes, and the
        # speaker then outlives `close()`.
        try:
            async with asyncio.timeout(FLOOR_WAIT_S):
                await self._floor.wait()
        except TimeoutError:
            return False
        return True

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
        # Only what happens from now on: a reconnect to an existing session must not say its old lines again.
        past = self.manager.bus.history()
        async for event in self.manager.bus.subscribe(since=past[-1].seq if past else 0):
            if event.data.get("session_id") != self.session_id and event.type != "team.proposed":
                continue
            if event.type == "team.proposed":
                session = self.manager.sessions.get(self.session_id)
                if session is not None and event.run_id == session.run_id and event.data.get("needs_approval"):
                    self.offers.approval_run = event.run_id
                continue
            if event.type == "queue.offered":
                self.offers.queue_id = event.data.get("queue_id")
                await self._answers_idle.wait()  # after the summary of the run that has just ended, not before it
                await self._say("conversation", QUEUE_OFFER, None, None, keep=True)
                continue
            text = self._spoken_line(event)
            if text:
                keep = event.type == "recap" or event.data.get("kind") in ("approval", "held", "team")
                await self._say("conversation", text, event.run_id, self.current_turn, keep=keep)
                if event.data.get("kind") == "team":
                    self._spawn(self._still_working(event.run_id))

    def _spoken_line(self, event: Any) -> str:
        """What the voice says for a lane event (founder decision R4, 2026-11-13): ONE opening turn on who is on the
        team, then nothing while they work (no line per agent or stage, no Verifier line, no figure, no assumption
        question: the screen has all of that), and a run that ended without an answer."""
        data = event.data
        if event.type == "recap":
            # A finished run's summary is spoken by `_speak_answer`, and a held-back team by its own line; a
            # cancelled or failed run has only this one.
            status = data.get("status", "done")
            if status == "rejected" or (status == "done" and event.run_id in self.offers.voiced_runs):
                return ""
            return str(data.get("text", ""))
        if event.type != "narration":
            return ""
        kind = data.get("kind")
        topic = str(data.get("topic") or "")
        if kind == "team":
            return team_line(list(data.get("team") or []), topic)
        if kind == "approval":
            team = team_line(list(data.get("team") or []), topic) or str(data.get("text", ""))
            return f"{team} This needs your approval. Say approve, or hold it."
        if kind == "held":
            return str(data.get("text", ""))
        return ""


def _drain(queue: asyncio.Queue[_Say]) -> list[_Say]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _log_failure(task: asyncio.Task[Any]) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.opt(exception=task.exception()).error("Voice task failed")
