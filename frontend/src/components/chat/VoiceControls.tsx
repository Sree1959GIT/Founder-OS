import { Mic, MicOff } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  VoiceClient,
  latencyLine,
  type VoiceBargeIn,
  type VoiceMode,
  type VoiceState,
  type VoiceTurnMetric,
} from "@/lib/voice";
import { useWorkspace } from "@/lib/workspace";

const STATE_WORDS: Record<VoiceState, string> = {
  off: "Voice off",
  connecting: "Connecting",
  idle: "Hold the mic to talk",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  interrupted: "Interrupted",
  error: "Voice unavailable",
};

export function VoiceControls() {
  const { state, spoken } = useWorkspace();
  const client = useRef<VoiceClient | null>(null);
  const [voice, setVoice] = useState<VoiceState>("off");
  const [mode, setMode] = useState<VoiceMode>("ptt");
  const [level, setLevel] = useState(0);
  const [heard, setHeard] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [turn, setTurn] = useState<VoiceTurnMetric | null>(null);
  const [barge, setBarge] = useState<VoiceBargeIn | null>(null);
  const spokenRef = useRef(spoken);
  spokenRef.current = spoken;

  const connect = useCallback(async () => {
    setError(null);
    const c = new VoiceClient({
      onState: setVoice,
      onReady: () => undefined,
      onPartial: setHeard,
      onTranscript: setHeard,
      onTurn: (text, outcome) => {
        setHeard("");
        if (text.trim()) spokenRef.current(text, outcome);
      },
      onSay: () => undefined,
      onTurnMetric: setTurn,
      onBargeIn: setBarge,
      onLevel: setLevel,
      onError: setError,
    });
    client.current = c;
    await c.start(state.sessionId, mode);
  }, [state.sessionId, mode]);

  const disconnect = useCallback(() => {
    client.current?.stop();
    client.current = null;
  }, []);

  useEffect(() => () => client.current?.stop(), []);
  useEffect(() => client.current?.setQuiet(state.quiet), [state.quiet]);

  const on = voice !== "off" && voice !== "error";
  const switchMode = (next: VoiceMode) => {
    setMode(next);
    client.current?.setMode(next);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        {on ? (
          <Button
            type="button"
            variant={voice === "listening" ? "default" : "outline"}
            size="icon"
            aria-label={mode === "ptt" ? "Hold to talk" : "Hands-free listening is on"}
            title={mode === "ptt" ? "Hold to talk; release to send" : "Hands-free: just talk; speak over the answer to interrupt"}
            className="h-11 w-11 rounded-lg"
            onPointerDown={() => mode === "ptt" && client.current?.pttStart()}
            onPointerUp={() => mode === "ptt" && client.current?.pttEnd()}
            onPointerLeave={() => mode === "ptt" && client.current?.pttEnd()}
          >
            <Mic aria-hidden="true" />
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Turn voice on"
            title="Turn voice on (asks for the microphone)"
            className="h-11 w-11 rounded-lg"
            onClick={() => void connect()}
          >
            <MicOff aria-hidden="true" />
          </Button>
        )}
      </div>
      {on ? (
        <div className="flex flex-col gap-1 text-xs text-muted-foreground" data-testid="voice-status">
          <div className="flex items-center gap-2">
            <span aria-live="polite" className="font-medium text-foreground">
              {STATE_WORDS[voice]}
            </span>
            <span aria-hidden="true" className="h-1.5 w-16 overflow-hidden rounded bg-border">
              <span className="block h-full bg-primary" style={{ width: `${Math.min(100, Math.round(level * 400))}%` }} />
            </span>
            <select
              aria-label="Voice mode"
              value={mode}
              onChange={(e) => switchMode(e.target.value as VoiceMode)}
              className="rounded border border-border-strong bg-background px-1 py-0.5"
            >
              <option value="ptt">Hold to talk</option>
              <option value="duplex">Hands-free</option>
            </select>
            <button type="button" className="underline" onClick={disconnect}>
              Voice off
            </button>
          </div>
          {heard ? <span className="italic">“{heard}”</span> : null}
          {turn || barge ? <span title="Measured on the backend for the last turn">{latencyLine(turn, barge)}</span> : null}
        </div>
      ) : null}
      {error ? <span className="text-xs text-destructive">{error}</span> : null}
    </div>
  );
}
