"""Scripted end-to-end voice and text scenarios on this PC (M5 founder re-test RZ, 2026-11-15).

    python scripts/voice_scenarios.py                       every scenario, typed and spoken
    python scripts/voice_scenarios.py --only S4 S5 --typed  some scenarios, one channel
    python scripts/voice_scenarios.py --report out.md       where the markdown report goes

It starts the real backend on a free port with a fresh data folder (the Northwind sample data, approval at Never,
the real Ollama, faster-whisper and Kokoro; the voice models are read from data/models). Each step is either typed,
through `/api/conversation/turn` as the UI's text box does, or spoken: the founder's exact phrase is synthesised with
the installed Kokoro (a different voice from FounderOS's) and played into `/ws/voice` in real time, hands-free.
For every step it records what was heard, what FounderOS said, the change cards, the runs started or cancelled,
the final figures and the badge, checks the expected outcome and writes a PASS/FAIL report.

Without Ollama or the voice models it says why and exits 0 (so CI, which has neither, skips it cleanly).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

OFFER = "That changes the decision. Restart with your change?"
REMINDER = "Your change to three hires isn't in this answer yet. Say yes to restart with it."
GREETING = "Hello. What would you like to look at?"
DUBAI = "Should we start a Dubai office?"
CHANGE = "Assume three hires."
FOUNDER_VOICE = "am_michael"  # FounderOS speaks af_heart: the founder's phrases use another voice


# --- the backend ----------------------------------------------------------------------------------------------------
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def ollama_up(url: str = "http://127.0.0.1:11434") -> bool:
    try:
        return httpx.get(f"{url}/api/tags", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


class Backend:
    def __init__(self, data_dir: Path, log: Path) -> None:
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.data_dir, self.log = data_dir, log
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        env = dict(os.environ)
        env.update(
            DATA_DIR=str(self.data_dir),
            VOICE_MODELS_DIR=str(ROOT / "data" / "models"),
            TEAM_APPROVAL="never",
            PYTHONUTF8="1",
        )
        python = ROOT / ".venv" / "Scripts" / "python.exe"
        exe = str(python if python.is_file() else sys.executable)
        args = [exe, "-m", "uvicorn", "--factory", "app.main:create_app", "--host", "127.0.0.1"]
        self.proc = subprocess.Popen(
            [*args, "--port", str(self.port)],
            cwd=ROOT / "backend",
            env=env,
            stdout=self.log.open("wb"),
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 180
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"backend exited, see {self.log}")
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(f"{self.base}/api/health", timeout=5).status_code == 200:
                    break
            time.sleep(1)
        else:
            raise RuntimeError("backend did not start in 180 s")
        httpx.post(f"{self.base}/api/data/load-sample", timeout=120).raise_for_status()

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(15)
            if self.proc.poll() is None:
                self.proc.kill()


# --- events ---------------------------------------------------------------------------------------------------------
class Events:
    """Every event on `/api/events`, as the Activity panel sees them."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.items: list[dict[str, Any]] = []
        self.task: asyncio.Task[None] | None = None

    async def _read(self) -> None:
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream("GET", f"{self.base}/api/events") as response,
        ):
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    with contextlib.suppress(json.JSONDecodeError):
                        self.items.append(json.loads(line[5:]))

    def start(self) -> None:
        self.task = asyncio.create_task(self._read())

    def mark(self) -> int:
        return len(self.items)

    def since(self, mark: int, **match: Any) -> list[dict[str, Any]]:
        out = []
        for e in self.items[mark:]:
            if all((e.get(k) if k in ("type", "run_id") else e.get("data", {}).get(k)) == v for k, v in match.items()):
                out.append(e)
        return out

    def working(self, run_id: str) -> list[str]:
        """The names of the agents of this run that have started and not ended."""
        names: dict[str, str] = {}
        ended: set[str] = set()
        for e in self.items:
            if e.get("run_id") != run_id or not e.get("agent_id"):
                continue
            if e["type"] == "agent.spawned":
                names[e["agent_id"]] = str(e["data"].get("name") or e["data"].get("type"))
            elif e["type"] == "agent.done" or (
                e["type"] == "agent.status" and e["data"].get("status") in ("cancelled", "failed")
            ):
                ended.add(e["agent_id"])
        return [n for a, n in names.items() if a not in ended]

    def finished(self, run_id: str) -> dict[str, Any] | None:
        return next((e for e in self.items if e["type"] == "run.finished" and e.get("run_id") == run_id), None)


# --- channels: typed and spoken -------------------------------------------------------------------------------------
@dataclass
class Step:
    said: str
    heard: str = ""
    lines: list[str] = field(default_factory=list)  # what FounderOS said (spoken) or showed in the lane (typed)
    run_started: str | None = None
    cards: int = 0
    notes: list[str] = field(default_factory=list)
    checks: list[tuple[str, bool]] = field(default_factory=list)

    def check(self, what: str, ok: bool) -> bool:
        self.checks.append((what, bool(ok)))
        return bool(ok)


class Channel:
    kind = ""

    def __init__(self, base: str, events: Events) -> None:
        self.base, self.events = base, events
        self.session_id = ""
        self.http = httpx.AsyncClient(base_url=base, timeout=120)

    async def open(self) -> None: ...

    async def close(self) -> None:
        await self.http.aclose()

    async def state(self) -> dict[str, Any]:
        if not self.session_id:
            return {}
        r = await self.http.get(f"/api/conversation/{self.session_id}")
        return r.json() if r.status_code == 200 else {}

    async def say(self, text: str, *, settle: float = 4.0) -> Step: ...

    async def lines_since(self, mark: int) -> list[str]:
        """The lane's lines for this session since `mark` (typed: what the panel shows)."""
        out = []
        for e in self.events.items[mark:]:
            d = e.get("data", {})
            lane = e["type"] in ("narration", "recap", "reply", "amendment.offered")
            if d.get("session_id") == self.session_id and lane:
                out.append(f"[{e['type']}] {d.get('text') or d.get('reply') or ''}")
        return out

    async def wait_finished(self, run_id: str, timeout: float = 600) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            done = self.events.finished(run_id)
            if done is not None:
                return done
            await asyncio.sleep(0.5)
        return None

    async def wait_quiet(self) -> None:
        """Spoken only: until FounderOS has finished talking."""

    async def after_answer(self, run_id: str) -> None:
        """Spoken only: until the run's summary has been said (it starts a few seconds after the run ends)."""


class Typed(Channel):
    kind = "typed"

    async def say(self, text: str, *, settle: float = 4.0) -> Step:
        step = Step(said=text, heard=text)
        before = (await self.state()).get("run_id")
        mark = self.events.mark()
        r = await self.http.post("/api/conversation/turn", json={"session_id": self.session_id or None, "text": text})
        r.raise_for_status()
        out = r.json()
        self.session_id = out["session_id"]
        if out.get("reply"):
            step.lines.append(f"[reply] {out['reply']}")
        await asyncio.sleep(settle)
        step.lines += await self.lines_since(mark)
        after = (await self.state()).get("run_id")
        if out.get("started_run") or (after and after != before):
            step.run_started = out.get("run_id") or after
        step.cards = len(self.events.since(mark, type="amendment.offered", session_id=self.session_id))
        return step


class Spoken(Channel):
    kind = "spoken"

    def __init__(self, base: str, events: Events, tts: Any) -> None:
        super().__init__(base, events)
        self.tts = tts
        self.ws: Any = None
        self.inbox: list[dict[str, Any]] = []
        self.audio_until = 0.0
        self.reader: asyncio.Task[None] | None = None
        self.change_mark = 0

    async def open(self) -> None:
        import websockets

        url = self.base.replace("http", "ws", 1) + "/ws/voice?mode=duplex"
        self.ws = await websockets.connect(url, max_size=None)
        ready = json.loads(await self.ws.recv())
        if ready.get("type") != "ready":
            raise RuntimeError(f"voice socket: {ready}")
        self.session_id = ready["session_id"]
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        with contextlib.suppress(Exception):
            async for raw in self.ws:
                now = time.time()
                if isinstance(raw, bytes):
                    # 24 kHz int16: this much audio plays from now (or from the end of what is queued)
                    self.audio_until = max(self.audio_until, now) + len(raw) / 48000
                    continue
                message = json.loads(raw)
                message["_t"] = now
                self.inbox.append(message)
                if message.get("type") == "interrupt":
                    self.audio_until = now

    async def close(self) -> None:
        if self.reader is not None:
            self.reader.cancel()
        if self.ws is not None:
            with contextlib.suppress(Exception):
                await self.ws.close()
        await super().close()

    async def wait_quiet(self, extra: float = 0.8, timeout: float = 120) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if time.time() > self.audio_until + extra:
                return
            await asyncio.sleep(0.2)

    def _pcm(self, text: str) -> bytes:
        from app.voice.audio import IN_RATE, OUT_RATE, float_to_pcm16, resample

        samples = self.tts.synthesize(text)
        return float_to_pcm16(resample(samples, OUT_RATE, IN_RATE))

    async def _play(self, data: bytes) -> None:
        from app.voice.audio import FRAME, IN_RATE

        step = FRAME * 2
        frames = [data[i : i + step] for i in range(0, len(data), step)] + [bytes(step)] * 40
        started = time.perf_counter()
        for n, frame in enumerate(frames):
            await self.ws.send(frame)
            delay = started + (n + 1) * FRAME / IN_RATE - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)

    async def say(self, text: str, *, settle: float = 4.0, over_voice: bool = False) -> Step:
        step = Step(said=text)
        if not over_voice:
            await self.wait_quiet()
        before = (await self.state()).get("run_id")
        mark, inbox_mark = self.events.mark(), len(self.inbox)
        await self._play(self._pcm(text))
        await asyncio.sleep(settle)
        await self.wait_quiet(timeout=30)
        for m in self.inbox[inbox_mark:]:
            if m.get("type") == "transcript":
                step.heard = (step.heard + " | " if step.heard else "") + str(m.get("text"))
            elif m.get("type") == "say":
                step.lines.append(f"[{m.get('lane')}] {m.get('text')}")
            elif m.get("type") in ("turn", "error"):
                step.notes.append(json.dumps({k: v for k, v in m.items() if k != "_t"})[:300])
        after = (await self.state()).get("run_id")
        if after and after != before:
            step.run_started = after
        step.cards = len(self.events.since(mark, type="amendment.offered", session_id=self.session_id))
        return step

    async def after_answer(self, run_id: str, timeout: float = 40) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            said = [m for m in self.inbox if m.get("type") == "say" and m.get("lane") == "answer"]
            if any(m.get("run_id") == run_id for m in said):
                break
            await asyncio.sleep(0.5)
        await self.wait_quiet(extra=2.5)

    def timeline(self, inbox_mark: int) -> str:
        """What the socket said since `inbox_mark`, with seconds from the first message: state, vad, say, interrupt."""
        items = self.inbox[inbox_mark:]
        t0 = items[0]["_t"] if items else 0.0
        keep = ("state", "vad", "say", "interrupt", "pause", "resume", "echo", "unsure", "missed")
        parts = []
        for m in items:
            if m.get("type") in keep:
                what = m.get("state") or m.get("speech") or (m.get("text") or "")[:40] or m.get("reason") or ""
                parts.append(f"{m['_t'] - t0:.1f}s {m['type']}={what}")
        return "; ".join(parts)

    def said_since(self, inbox_mark: int) -> list[str]:
        return [str(m.get("text")) for m in self.inbox[inbox_mark:] if m.get("type") == "say"]


# --- scenarios ------------------------------------------------------------------------------------------------------
@dataclass
class Result:
    scenario: str
    channel: str
    steps: list[Step] = field(default_factory=list)
    error: str = ""

    @property
    def passed(self) -> bool:
        return not self.error and all(ok for s in self.steps for _, ok in s.checks)


def _has(lines: list[str], text: str) -> int:
    return sum(text.lower() in line.lower() for line in lines)


async def _until_only_devil(ch: Channel, run_id: str, timeout: float = 400) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        working = ch.events.working(run_id)
        if working and all("devil" in w.lower() for w in working):
            return True
        if ch.events.finished(run_id):
            return False
        await asyncio.sleep(0.25)
    return False


async def _dubai_with_change(ch: Channel, r: Result) -> tuple[str | None, Step | None]:
    """S1: the Dubai question, and the change said when only the Devil's Advocate is still working."""
    s = await ch.say(DUBAI, settle=2)
    r.steps.append(s)
    if not s.check("a team started", s.run_started):
        return None, None
    run_id = s.run_started
    assert run_id is not None
    alone = await _until_only_devil(ch, run_id)
    s.check("the Devil's Advocate was the last agent working", alone)
    mark = ch.events.mark()
    if isinstance(ch, Spoken):
        ch.change_mark = len(ch.inbox)
    c = (
        await ch.say(CHANGE, settle=3, over_voice=True)  # type: ignore[call-arg]
        if isinstance(ch, Spoken)
        else await ch.say(CHANGE, settle=3)
    )
    r.steps.append(c)
    offered = ch.events.since(mark, type="amendment.offered", session_id=ch.session_id)
    done_before = ch.events.finished(run_id)
    offered_seq = offered[0]["seq"] if offered else None
    early = offered_seq is not None and (done_before is None or offered_seq < done_before["seq"])
    c.check("the offer came before the run finished", early)
    c.check(f'FounderOS said "{OFFER}"', _has(c.lines, OFFER) >= 1)
    c.check('no "Did you say" read-back', _has(c.lines, "did you say") == 0)
    c.check("no new run started", c.run_started is None)
    c.check("one card", c.cards == 1)
    return run_id, c


async def s1_s2(ch: Channel, r: Result) -> None:
    run_id, change = await _dubai_with_change(ch, r)
    if run_id is None or change is None:
        return
    inbox_mark = len(ch.inbox) if isinstance(ch, Spoken) else 0
    mark = ch.events.mark()
    finished = await ch.wait_finished(run_id)
    await ch.wait_quiet()
    await asyncio.sleep(3)
    await ch.wait_quiet()
    wait = Step(said="(says nothing until the answer is over)")
    r.steps.append(wait)
    wait.check("the first run finished", finished is not None)
    if isinstance(ch, Spoken):
        deadline = time.time() + 45  # the summary and its reminder, however slowly they come
        while time.time() < deadline and _has(ch.said_since(inbox_mark), REMINDER) == 0:
            await asyncio.sleep(0.5)
        await ch.wait_quiet()
        wait.notes.append("timeline from the change: " + ch.timeline(ch.change_mark))
        said = ch.said_since(inbox_mark)
        wait.lines = said
        wait.check("the reminder was said exactly once", _has(said, REMINDER) == 1)
    else:
        wait.lines = await ch.lines_since(mark)
    state = await ch.state()
    open_cards = [a for a in state.get("amendments", []) if a.get("status") == "offered"]
    wait.check("the change is still on offer (one open card)", len(open_cards) == 1)
    wait.check("one card in all", len(ch.events.since(0, type="amendment.offered", session_id=ch.session_id)) == 1)
    yes = await ch.say("yes", settle=3)
    r.steps.append(yes)
    if not yes.check("yes restarted the run", yes.run_started):
        return
    assert yes.run_started is not None
    await ch.wait_finished(yes.run_started)
    await ch.wait_quiet()
    run = (await ch.http.get(f"/api/runs/{yes.run_started}")).json()
    result = run.get("result") or {}
    blob = json.dumps(result)
    yes.notes.append(f"answer: {(result.get('answer') or '')[:400]}")
    impact = result.get("decision_impact") or {}
    yes.notes.append(f"decision_impact: {json.dumps(impact)[:600]}")
    verification = result.get("verification") or {}
    yes.notes.append(f"badge: {verification.get('state')}; reasons: {verification.get('reasons')}")
    yes.check("$43,770.86 a month", "43,770.86" in blob or "43770.86" in blob)
    yes.check("runway falls by 2.58 months (11.23 to 8.65)", "2.58" in blob)
    r.notes = verification  # type: ignore[attr-defined]


async def s3(ch: Channel, r: Result) -> None:
    run_id, _ = await _dubai_with_change(ch, r)
    if run_id is None:
        return
    await ch.wait_finished(run_id)
    await ch.after_answer(run_id)
    for sound in ("mm", "hmm", "uh-huh"):
        s = await ch.say(sound, settle=3)
        r.steps.append(s)
        state = await ch.state()
        s.check("no run started", s.run_started is None)
        s.check("nothing said", not [ln for ln in s.lines if ln.strip()])
        s.check("the card is still open", any(a.get("status") == "offered" for a in state.get("amendments", [])))
    ok = await ch.say("okay", settle=3)
    r.steps.append(ok)
    ok.check("okay restarted with the change", ok.run_started)
    ok.check('"Restarting with your change."', _has(ok.lines, "restarting with your change") >= 1)
    if ok.run_started:
        await ch.http.post(f"/api/runs/{ok.run_started}/cancel")


async def s4(ch: Channel, r: Result) -> None:
    s = await ch.say("Okay, I will leave it as it is.", settle=4)
    r.steps.append(s)
    s.check("no team started", s.run_started is None)
    s.check('"Did you say: …? Say yes to look into it, or say it again."', _has(s.lines, "did you say") >= 1)
    n = await ch.say("no", settle=3)
    r.steps.append(n)
    n.check('"Okay. Say it again."', _has(n.lines, "say it again") >= 1)
    n.check("no team started", n.run_started is None)


async def s5(ch: Channel, r: Result) -> None:
    s = await ch.say("Hello? Yes?", settle=4)
    r.steps.append(s)
    s.check(f'"{GREETING}"', _has(s.lines, GREETING) >= 1)
    s.check("no team started", s.run_started is None)
    y = await ch.say("yes", settle=4)
    r.steps.append(y)
    y.check("nothing happens (no run, nothing said)", y.run_started is None and not y.lines)


async def s6(ch: Channel, r: Result) -> None:
    s = await ch.say(DUBAI, settle=2)
    r.steps.append(s)
    if not s.check("a team started", s.run_started):
        return
    assert s.run_started is not None
    await ch.wait_finished(s.run_started)
    await ch.after_answer(s.run_started)
    a = await ch.say("Re-run the analyst", settle=2)
    r.steps.append(a)
    if a.check("a re-run started", a.run_started):
        assert a.run_started is not None
        await ch.wait_finished(a.run_started)
        await ch.after_answer(a.run_started)
        ran = _reran(ch, a.run_started)
        a.notes.append(f"agents that worked again: {ran}")
        a.check("only the Financial Analyst ran", ran == ["Financial Analyst"])
        lane = [e["data"].get("text", "") for e in ch.events.since(0, type="narration", run_id=a.run_started)]
        a.notes.append(f"lane lines: {lane}")
        repeated = [t for t in lane if t.startswith(("Team:", "While the team works")) or " done; " in t]
        a.check("no team line, inputs question or stage line for a one-agent re-run", not repeated)
    lb = await ch.say("Re-run the librarain", settle=3)
    r.steps.append(lb)
    if "librarian" in lb.heard.lower():
        # The recogniser wrote the name right (its vocabulary has the agents' names): an exact re-run is correct.
        lb.notes.append("heard the name exactly, so this is a plain re-run of the Librarian")
        lb.check("a re-run of only the Librarian started", lb.run_started)
        if lb.run_started:
            await ch.wait_finished(lb.run_started)
            await ch.after_answer(lb.run_started)
            ran = _reran(ch, lb.run_started)
            lb.notes.append(f"agents that worked again: {ran}")
            run = (await ch.http.get(f"/api/runs/{lb.run_started}")).json()
            lb.notes.append(f"answer: {((run.get('result') or {}).get('answer') or '')[:500]}")
            lb.check("only the Librarian ran", ran == ["Librarian"])
    else:
        lb.check('"Did you mean re-run the Librarian?"', _has(lb.lines, "did you mean re-run the librarian") >= 1)
        lb.check("no run started", lb.run_started is None)


async def s7(ch: Channel, r: Result) -> None:
    s = await ch.say(DUBAI, settle=2)
    r.steps.append(s)
    if not s.check("a team started", s.run_started):
        return
    assert s.run_started is not None
    await asyncio.sleep(6)
    st = await ch.say("stop", settle=3, **({"over_voice": True} if isinstance(ch, Spoken) else {}))
    r.steps.append(st)
    if isinstance(ch, Spoken):
        y = await ch.say("yes", settle=3, over_voice=True)
        r.steps.append(y)
    else:
        y = st
    done = await ch.wait_finished(s.run_started, timeout=30)
    y.check("the run was cancelled", done is not None and done["data"].get("status") == "cancelled")
    await asyncio.sleep(3)
    after = Step(said="(silence after the stop)")
    if isinstance(ch, Spoken):
        mark = len(ch.inbox)
        await asyncio.sleep(5)
        after.lines = ch.said_since(mark)
        after.check("silent afterwards (at most the stop line)", len(after.lines) <= 1)
    r.steps.append(after)


def _reran(ch: Channel, run_id: str) -> list[str]:
    """The agents of a run that worked again, not those whose findings were kept from the run before."""
    steps = ch.events.since(0, type="agent.step", run_id=run_id)
    kept = {e["agent_id"] for e in steps if "kept" in str(e["data"].get("step"))}
    spawned = ch.events.since(0, type="agent.spawned", run_id=run_id)
    return [str(e["data"].get("name")) for e in spawned if e["agent_id"] not in kept]


SCENARIOS = {"S1+S2": s1_s2, "S3": s3, "S4": s4, "S5": s5, "S6": s6, "S7": s7}


# --- report ---------------------------------------------------------------------------------------------------------
def report(results: list[Result], path: Path, started: float) -> str:
    rows = ["| Scenario | Typed | Spoken |", "|---|---|---|"]
    names = list(dict.fromkeys(r.scenario for r in results))
    for name in names:
        cells = []
        for kind in ("typed", "spoken"):
            r = next((x for x in results if x.scenario == name and x.channel == kind), None)
            cells.append("-" if r is None else ("PASS" if r.passed else "FAIL"))
        rows.append(f"| {name} | {cells[0]} | {cells[1]} |")
    out = [f"# Voice scenarios, {time.strftime('%Y-%m-%d %H:%M')} ({time.time() - started:.0f} s)", "", *rows, ""]
    for r in results:
        out.append(f"## {r.scenario} ({r.channel}): {'PASS' if r.passed else 'FAIL'}")
        if r.error:
            out.append(f"- ERROR: {r.error}")
        for s in r.steps:
            out.append(f"- **Said:** {s.said!r}; **heard:** {s.heard!r}; run: {s.run_started}; cards: {s.cards}")
            for line in s.lines:
                out.append(f"  - {line}")
            for note in s.notes:
                out.append(f"  - _{note}_")
            for what, ok in s.checks:
                out.append(f"  - {'PASS' if ok else '**FAIL**'}: {what}")
        out.append("")
    text = "\n".join(out)
    path.write_text(text, encoding="utf-8")
    return "\n".join(rows)


async def run_all(base: str, names: list[str], kinds: list[str], tts: Any) -> list[Result]:
    events = Events(base)
    events.start()
    await asyncio.sleep(1)
    results = []
    for name in names:
        for kind in kinds:
            ch: Channel = Spoken(base, events, tts) if kind == "spoken" else Typed(base, events)
            r = Result(name, kind)
            print(f"{name} ({kind}) ...", flush=True)
            try:
                await ch.open()
                await asyncio.wait_for(SCENARIOS[name](ch, r), timeout=900)
            except Exception as exc:  # the report says what broke, and the next scenario still runs
                r.error = f"{type(exc).__name__}: {exc}"
            finally:
                state = await ch.state()
                if state.get("running") and state.get("run_id"):
                    await ch.http.post(f"/api/runs/{state['run_id']}/cancel")
                await ch.close()
            print(f"  {'PASS' if r.passed else 'FAIL'} {r.error}", flush=True)
            results.append(r)
    if events.task is not None:
        events.task.cancel()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", help="scenario names, e.g. S1+S2 S4")
    parser.add_argument("--typed", action="store_true", help="typed steps only")
    parser.add_argument("--spoken", action="store_true", help="spoken steps only")
    parser.add_argument("--report", type=Path, default=Path(tempfile.gettempdir()) / "voice_scenarios.md")
    parser.add_argument("--backend", help="use a backend that is already running (its data, its settings)")
    args = parser.parse_args()
    models = ROOT / "data" / "models"
    if not ollama_up():
        print("SKIP: Ollama is not running on this machine.")
        return 0
    if not (models / "kokoro").is_dir():
        print(f"SKIP: no voice models in {models} (python scripts/download_voice_models.py).")
        return 0
    kinds = ["typed"] if args.typed else ["spoken"] if args.spoken else ["typed", "spoken"]
    names = [n for n in SCENARIOS if not args.only or n in args.only]
    tts = None
    if "spoken" in kinds:
        from app.voice.tts import KokoroTTS

        folder = models / "kokoro"
        model = next(iter(sorted(folder.glob("*.onnx"))))
        tts = KokoroTTS(model, folder / "voices-v1.0.bin", voice=FOUNDER_VOICE)
    started = time.time()
    work = Path(tempfile.mkdtemp(prefix="founderos_scenarios_"))
    backend = None
    if args.backend:
        base = args.backend.rstrip("/")
    else:
        backend = Backend(work / "data", work / "backend.log")
        print(f"Starting the backend on {backend.base} (log: {backend.log}) ...", flush=True)
        backend.start()
        base = backend.base
    try:
        results = asyncio.run(run_all(base, names, kinds, tts))
    finally:
        if backend is not None:
            backend.stop()
    table = report(results, args.report, started)
    print(table)
    print(f"Report: {args.report}")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
