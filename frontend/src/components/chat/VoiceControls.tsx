import { Mic, MicOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { latencyLine, type VoiceMode } from "@/lib/voice";
import { STATE_WORDS, useVoice } from "@/lib/voiceContext";
import { cn } from "@/lib/utils";

/** The mic button: "Turn voice on" until voice is on, then press and hold to talk (push-to-talk mode). */
export function MicButton({ big = false, label }: { big?: boolean; label?: string }) {
  const v = useVoice();
  const size = big ? "h-14 min-w-[56px] px-5 text-base" : "h-11 w-11";
  if (!v.on) {
    return (
      <Button
        type="button"
        variant="outline"
        size={big ? "default" : "icon"}
        aria-label={label ? undefined : "Turn voice on"}
        title="Turn voice on (asks for the microphone)"
        className={cn(size, "gap-2 rounded-full")}
        onClick={() => void v.connect()}
      >
        <MicOff aria-hidden="true" />
        {label ? <span>{label === "Hold to talk" ? "Start voice" : label}</span> : null}
      </Button>
    );
  }
  const ptt = v.mode === "ptt";
  return (
    <Button
      type="button"
      variant={v.voice === "listening" ? "default" : "outline"}
      size={big ? "default" : "icon"}
      aria-label={label ? undefined : ptt ? "Hold to talk" : "Hands-free listening is on"}
      title={ptt ? "Hold to talk; release to send" : "Hands-free: just talk; speak over the answer to interrupt"}
      className={cn(size, "gap-2 rounded-full touch-none select-none")}
      onPointerDown={() => ptt && v.pttStart()}
      onPointerUp={() => ptt && v.pttEnd()}
      onPointerLeave={() => ptt && v.pttEnd()}
      onPointerCancel={() => ptt && v.pttEnd()}
    >
      <Mic aria-hidden="true" />
      {label ? <span>{ptt ? "Hold to talk" : "Listening"}</span> : null}
    </Button>
  );
}

export function VoiceControls() {
  const v = useVoice();
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <MicButton />
      </div>
      {v.on ? (
        <div className="flex flex-col gap-1 text-xs text-muted-foreground" data-testid="voice-status">
          <div className="flex flex-wrap items-center gap-2">
            <span aria-live="polite" className="font-medium text-foreground">
              {STATE_WORDS[v.voice]}
            </span>
            <span aria-hidden="true" className="h-1.5 w-16 overflow-hidden rounded bg-border">
              <span className="block h-full bg-primary" style={{ width: `${Math.min(100, Math.round(v.level * 400))}%` }} />
            </span>
            <select
              aria-label="Voice mode"
              value={v.mode}
              onChange={(e) => v.switchMode(e.target.value as VoiceMode)}
              className="h-8 rounded border border-border-strong bg-background px-1"
            >
              <option value="ptt">Hold to talk</option>
              <option value="duplex">Hands-free</option>
            </select>
            <button type="button" className="h-8 underline" onClick={v.disconnect}>
              Voice off
            </button>
          </div>
          {v.heard ? <span className="italic">“{v.heard}”</span> : null}
          {v.missed && !v.heard ? <span data-testid="voice-missed">Didn't catch that. Say it again.</span> : null}
          {v.unsure && !v.heard ? (
            <span data-testid="voice-unsure">Did you say “{v.unsure}”? Say yes, or say it again.</span>
          ) : null}
          {v.turn || v.barge ? <span title="Measured on the backend for the last turn">{latencyLine(v.turn, v.barge)}</span> : null}
        </div>
      ) : null}
      {v.error ? (
        <span className="text-xs text-destructive" role="alert">
          {v.error}
        </span>
      ) : null}
    </div>
  );
}

/** Founder F9: on pages without the Advisor panel, voice carries on, with its mic and live words in a small dock. */
export function VoiceDock() {
  const v = useVoice();
  if (!v.on && !v.error) return null;
  const line = v.heard ? `“${v.heard}”` : v.saying || STATE_WORDS[v.voice];
  return (
    <div
      className="print-hide fixed bottom-4 left-4 z-40 flex max-w-[min(420px,calc(100vw-32px))] items-center gap-3 rounded-full border border-border-strong bg-card py-1.5 pl-1.5 pr-4 shadow-lg"
      data-testid="voice-dock"
      role="region"
      aria-label="Voice"
    >
      <MicButton />
      <span className="min-w-0 truncate text-[13px] text-foreground" aria-live="polite">
        {v.error ?? line}
      </span>
    </div>
  );
}
