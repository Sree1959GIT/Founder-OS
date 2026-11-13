/**
 * The browser end of `/ws/voice` (PRD F5): microphone to 16 kHz mono int16 PCM through an AudioWorklet, and the
 * backend's 24 kHz int16 PCM played back gap-free. `pause` suspends playback at once, `interrupt` flushes it and
 * reports how long the flush took. Voice never blocks the canvas: everything here is optional and fails quietly.
 */
import type { TurnOutcome } from "@/lib/api";

export type VoiceMode = "ptt" | "duplex";
export type VoiceState = "off" | "connecting" | "idle" | "listening" | "thinking" | "speaking" | "interrupted" | "error";

export interface VoiceTurnMetric {
  id: string;
  text: string;
  stt_ms: number | null;
  turn_ms: number | null;
  first_audio_ms: number | null;
  first_audio_lane: string;
  first_answer_audio_ms: number | null;
  tts_first_ms: number | null;
}

export interface VoiceBargeIn {
  paused_ms: number | null;
  stopped_ms: number | null;
  client_flush_ms: number | null;
  verdict: string;
  by: string;
}

export interface VoiceHandlers {
  onState: (state: VoiceState) => void;
  onReady: (sessionId: string, status: Record<string, unknown>) => void;
  onPartial: (text: string) => void;
  onTranscript: (text: string) => void;
  /** Speech was heard but no words were made out: the founder is told, so a turn is never lost in silence. */
  onMissed: () => void;
  /** The recogniser was unsure of these words: they are read back ("Did you say ...?") before anything is done. */
  onUnsure: (text: string) => void;
  onTurn: (text: string, outcome: TurnOutcome) => void;
  onSay: (lane: string, text: string) => void;
  onTurnMetric: (metric: VoiceTurnMetric) => void;
  onBargeIn: (metric: VoiceBargeIn) => void;
  onLevel: (level: number) => void;
  onError: (message: string) => void;
}

const IN_RATE = 16000;
const OUT_RATE = 24000;

// Runs on the audio thread: downsample to 16 kHz, post 512-sample int16 frames (32 ms) and a level for the meter.
const WORKLET = `
class Capture extends AudioWorkletProcessor {
  constructor() { super(); this.ratio = sampleRate / ${IN_RATE}; this.acc = []; this.pos = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let sum = 0;
    for (let i = 0; i < ch.length; i++) sum += ch[i] * ch[i];
    while (this.pos < ch.length) { this.acc.push(ch[Math.floor(this.pos)]); this.pos += this.ratio; }
    this.pos -= ch.length;
    if (this.acc.length >= 512) {
      const frame = new Int16Array(this.acc.length);
      for (let i = 0; i < this.acc.length; i++) frame[i] = Math.max(-1, Math.min(1, this.acc[i])) * 32767;
      this.port.postMessage({ pcm: frame.buffer, level: Math.sqrt(sum / ch.length) }, [frame.buffer]);
      this.acc = [];
    }
    return true;
  }
}
registerProcessor("founderos-capture", Capture);
`;

export function voiceUrl(sessionId: string | null, mode: VoiceMode, location: Location = window.location): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const query = new URLSearchParams({ mode, ...(sessionId ? { session_id: sessionId } : {}) });
  return `${scheme}://${location.host}/ws/voice?${query.toString()}`;
}

export function pcm16ToFloat(buffer: ArrayBuffer): Float32Array {
  const ints = new Int16Array(buffer);
  const out = new Float32Array(ints.length);
  for (let i = 0; i < ints.length; i++) out[i] = (ints[i] ?? 0) / 32768;
  return out;
}

export class VoiceClient {
  private socket: WebSocket | null = null;
  private mic: MediaStream | null = null;
  private captureCtx: AudioContext | null = null;
  private playCtx: AudioContext | null = null;
  private sources = new Set<AudioBufferSourceNode>();
  private nextTime = 0;
  private holding = false;
  private lastTranscript = "";
  mode: VoiceMode = "ptt";

  constructor(private readonly on: VoiceHandlers) {}

  async start(sessionId: string | null, mode: VoiceMode): Promise<void> {
    this.mode = mode;
    this.on.onState("connecting");
    try {
      this.mic = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      this.fail("Microphone not available: allow it in the browser and try again.");
      return;
    }
    this.captureCtx = new AudioContext();
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await this.captureCtx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const node = new AudioWorkletNode(this.captureCtx, "founderos-capture");
    node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => {
      this.on.onLevel(e.data.level);
      const open = this.socket?.readyState === WebSocket.OPEN;
      if (open && (this.mode === "duplex" || this.holding)) this.socket?.send(e.data.pcm);
    };
    this.captureCtx.createMediaStreamSource(this.mic).connect(node);
    this.playCtx = new AudioContext({ sampleRate: OUT_RATE });
    const socket = new WebSocket(voiceUrl(sessionId, mode));
    socket.binaryType = "arraybuffer";
    socket.onmessage = (e: MessageEvent<ArrayBuffer | string>) => {
      if (typeof e.data === "string") this.message(JSON.parse(e.data) as Record<string, unknown>);
      else this.play(e.data);
    };
    socket.onerror = () => this.fail("Voice connection failed: is the backend running?");
    socket.onclose = () => this.on.onState("off");
    this.socket = socket;
  }

  stop(): void {
    this.flush();
    this.socket?.close();
    this.mic?.getTracks().forEach((t) => t.stop());
    void this.captureCtx?.close();
    void this.playCtx?.close();
    this.socket = null;
    this.mic = null;
    this.captureCtx = null;
    this.playCtx = null;
    this.on.onState("off");
  }

  setMode(mode: VoiceMode): void {
    this.mode = mode;
    this.control({ type: "mode", mode });
  }

  pttStart(): void {
    this.holding = true;
    this.flush(); // the founder pressed to speak: stop talking over them at once
    this.control({ type: "ptt_start" });
  }

  pttEnd(): void {
    if (!this.holding) return;
    this.holding = false;
    this.control({ type: "ptt_end" });
  }

  setQuiet(quiet: boolean): void {
    if (quiet) this.flush();
    this.control({ type: "quiet", quiet });
  }

  private control(message: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(message));
  }

  private fail(message: string): void {
    this.on.onError(message);
    this.on.onState("error");
  }

  private message(m: Record<string, unknown>): void {
    switch (m.type) {
      case "ready":
        this.on.onReady(String(m.session_id), (m.status as Record<string, unknown>) ?? {});
        break;
      case "state":
        this.on.onState(m.state as VoiceState);
        break;
      case "partial":
        this.on.onPartial(String(m.text ?? ""));
        break;
      case "transcript":
        this.lastTranscript = String(m.text ?? "");
        this.on.onTranscript(this.lastTranscript);
        break;
      case "missed":
        this.on.onMissed();
        break;
      case "unsure":
        this.on.onUnsure(String(m.text ?? ""));
        break;
      case "turn":
        // `text` is the turn as it was acted on: after "Did you say ...?" and a "yes", the words confirmed.
        this.on.onTurn(typeof m.text === "string" ? m.text : this.lastTranscript, m.outcome as TurnOutcome);
        break;
      case "say":
        this.on.onSay(String(m.lane), String(m.text));
        break;
      case "pause":
        void this.playCtx?.suspend();
        break;
      case "resume":
        void this.playCtx?.resume();
        break;
      case "interrupt": {
        const flushMs = this.flush();
        this.control({ type: "playback_stopped", flush_ms: flushMs });
        break;
      }
      case "metrics":
        if (m.turn) this.on.onTurnMetric(m.turn as VoiceTurnMetric);
        if (m.barge_in) this.on.onBargeIn(m.barge_in as VoiceBargeIn);
        break;
      case "error":
        this.on.onError(String(m.message ?? "voice error"));
        break;
      default:
        break;
    }
  }

  private play(buffer: ArrayBuffer): void {
    const ctx = this.playCtx;
    if (!ctx) return;
    const samples = pcm16ToFloat(buffer);
    if (samples.length === 0) return;
    const audio = ctx.createBuffer(1, samples.length, OUT_RATE);
    audio.copyToChannel(samples, 0);
    const source = ctx.createBufferSource();
    source.buffer = audio;
    source.connect(ctx.destination);
    const at = Math.max(ctx.currentTime + 0.02, this.nextTime);
    source.start(at);
    this.nextTime = at + audio.duration;
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
  }

  /** Silence now. Returns how long it took, in ms (reported to the backend as the client's flush time). */
  private flush(): number {
    const started = performance.now();
    this.sources.forEach((s) => {
      try {
        s.stop();
      } catch {
        // already stopped
      }
    });
    this.sources.clear();
    this.nextTime = 0;
    if (this.playCtx?.state === "suspended") void this.playCtx.resume();
    return Math.round((performance.now() - started) * 10) / 10;
  }
}

export const ms = (value: number | null | undefined): string => (value == null ? "–" : `${Math.round(value)} ms`);

/** The latency overlay (PRD F5): the last turn and the last barge-in, as the backend measured them. */
export function latencyLine(turn: VoiceTurnMetric | null, barge: VoiceBargeIn | null): string {
  const parts: string[] = [];
  if (turn) {
    parts.push(`first words ${ms(turn.first_audio_ms)}`, `answer ${ms(turn.first_answer_audio_ms)}`, `STT ${ms(turn.stt_ms)}`);
  }
  if (barge) parts.push(`barge-in stop ${ms(barge.stopped_ms)}${barge.verdict === "backchannel" ? " (backchannel)" : ""}`);
  return parts.join(" · ");
}
