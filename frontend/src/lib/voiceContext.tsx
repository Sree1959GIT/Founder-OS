/* eslint-disable react-refresh/only-export-components -- the hook and its provider belong together */
/**
 * Founder F9: voice (the Advisor's mic, its speech and its context) lives above the pages. The voice client is owned
 * here, at the app root, so going to Activity, Decisions or Settings never starts, stops or resets it. Pages only show
 * controls for it (`VoiceControls`, the Boardroom's caption bar, the dock on other pages).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { VoiceClient, type VoiceBargeIn, type VoiceMode, type VoiceState, type VoiceTurnMetric } from "@/lib/voice";
import { useWorkspace } from "@/lib/workspace";

export const STATE_WORDS: Record<VoiceState, string> = {
  off: "Voice off",
  connecting: "Connecting",
  idle: "Hold the mic to talk",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  interrupted: "Interrupted",
  error: "Voice unavailable",
};

export interface VoiceApi {
  voice: VoiceState;
  mode: VoiceMode;
  on: boolean;
  level: number;
  heard: string;
  /** What the Advisor is saying now (for the live caption). */
  saying: string;
  missed: boolean;
  unsure: string;
  error: string | null;
  turn: VoiceTurnMetric | null;
  barge: VoiceBargeIn | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  pttStart: () => void;
  pttEnd: () => void;
  switchMode: (mode: VoiceMode) => void;
  /** Founder F27: who the member is talking to (a face they tapped), or null. */
  talkingTo: { id: string; name: string } | null;
  /** Tap a face: voice on if needed, hands-free, talking to that agent. The same face again stops listening. */
  talkTo: (id: string, name: string) => Promise<void>;
  /** Stop the speech now (the Stop button under the speaking face, or Esc). Never stops the team. */
  hush: () => void;
  muted: boolean;
  toggleMute: () => void;
}

const Context = createContext<VoiceApi | null>(null);

/** A friendly line for a blocked microphone (the brief: HTTPS and permission are needed, on phones above all). */
export function micProblem(message: string, secure: boolean = window.isSecureContext): string {
  const aboutMic = /mic|getusermedia|mediadevices|notallowed|permission|audio input|undefined is not an object/i.test(message);
  if (!secure && aboutMic) {
    return "The microphone needs a secure (https) address. Open FounderOS on this PC, or use typing for now.";
  }
  if (/denied|notallowed|permission/i.test(message)) {
    return "The microphone is blocked. Allow it in the browser's site settings (the lock icon), then try again.";
  }
  if (/notfound|no.*(device|microphone)/i.test(message)) return "No microphone was found. Plug one in, or type instead.";
  return message;
}

/** A key pressed in a text box, a list or a button that Space would press is the member typing, not talking. */
export function typingIn(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A", "SUMMARY"].includes(target.tagName) || target.getAttribute("role") === "separator";
}

export function VoiceProvider({ children }: { children: ReactNode }) {
  const { state, spoken } = useWorkspace();
  const client = useRef<VoiceClient | null>(null);
  const [voice, setVoice] = useState<VoiceState>("off");
  const [mode, setMode] = useState<VoiceMode>("ptt");
  const [level, setLevel] = useState(0);
  const [heard, setHeard] = useState("");
  const [saying, setSaying] = useState("");
  const [missed, setMissed] = useState(false);
  const [unsure, setUnsure] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [turn, setTurn] = useState<VoiceTurnMetric | null>(null);
  const [barge, setBarge] = useState<VoiceBargeIn | null>(null);
  const [talkingTo, setTalkingTo] = useState<{ id: string; name: string } | null>(null);
  const [muted, setMuted] = useState(false);
  const talkingRef = useRef(talkingTo);
  talkingRef.current = talkingTo;
  const spokenRef = useRef(spoken);
  spokenRef.current = spoken;
  const sessionRef = useRef(state.sessionId);
  sessionRef.current = state.sessionId;
  const modeRef = useRef(mode);
  modeRef.current = mode;

  const connect = useCallback(async () => {
    if (client.current) return; // already on: a second tap never opens a second socket
    setError(null);
    const c = new VoiceClient({
      onState: setVoice,
      onReady: () => undefined,
      onPartial: setHeard,
      onTranscript: (text) => {
        setHeard(text);
        if (text.trim()) setMissed(false);
      },
      onMissed: () => {
        setHeard("");
        setMissed(true);
      },
      onUnsure: (text) => {
        setHeard("");
        setUnsure(text);
      },
      onTurn: (text, outcome) => {
        setHeard("");
        setMissed(false);
        setUnsure("");
        if (text.trim()) spokenRef.current(text, outcome);
      },
      onSay: (_lane, text) => setSaying(text),
      onTurnMetric: setTurn,
      onBargeIn: setBarge,
      onLevel: setLevel,
      onError: (message) => setError(micProblem(message)),
    });
    client.current = c;
    try {
      await c.start(sessionRef.current, modeRef.current);
    } catch (err) {
      client.current = null;
      setError(micProblem(err instanceof Error ? err.message : String(err)));
    }
  }, []);

  const disconnect = useCallback(() => {
    client.current?.stop();
    client.current = null;
    setVoice("off");
    setSaying("");
    setTalkingTo(null);
    setMuted(false);
  }, []);

  useEffect(() => () => client.current?.stop(), []);
  useEffect(() => client.current?.setQuiet(state.quiet), [state.quiet]);

  const switchMode = useCallback((next: VoiceMode) => {
    setMode(next);
    client.current?.setMode(next);
  }, []);
  const pttStart = useCallback(() => client.current?.pttStart(), []);
  const pttEnd = useCallback(() => client.current?.pttEnd(), []);
  const hush = useCallback(() => {
    client.current?.hush();
    setSaying("");
  }, []);
  const toggleMute = useCallback(() => {
    setMuted((m) => {
      client.current?.setMuted(!m);
      return !m;
    });
  }, []);
  const talkTo = useCallback(
    async (id: string, name: string) => {
      if (talkingRef.current?.id === id && client.current) {
        // The same face again: stop listening hands-free (voice stays on; Space still holds to talk).
        setTalkingTo(null);
        switchMode("ptt");
        return;
      }
      setTalkingTo({ id, name });
      if (client.current) {
        switchMode("duplex");
        return;
      }
      setMode("duplex");
      modeRef.current = "duplex";
      await connect();
      if (!client.current) setTalkingTo(null); // the mic or the socket failed: nobody is being talked to
    },
    [connect, switchMode],
  );

  // Founder F27 keys, anywhere but while typing: Space = hold to talk, Esc = stop speaking, M = mute the mic.
  const held = useRef(false);
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Escape" && client.current) {
        hush(); // Esc stops the speech wherever the focus is
        return;
      }
      if (typingIn(e.target)) return;
      if (e.code === "Space") {
        // Voice off: Space starts it only in the Boardroom (it never asks for the mic while reading a page).
        if (!client.current && !document.querySelector("[data-voice-keys]")) return;
        e.preventDefault();
        if (e.repeat || held.current) return;
        held.current = true;
        void (async () => {
          if (!client.current) await connect();
          if (modeRef.current !== "ptt") {
            switchMode("ptt");
            setTalkingTo(null); // holding to talk ends hands-free talking to a face
          }
          if (held.current) client.current?.pttStart();
        })();
      } else if ((e.key === "m" || e.key === "M") && client.current) {
        e.preventDefault();
        toggleMute();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || !held.current) return;
      held.current = false;
      client.current?.pttEnd();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [connect, hush, switchMode, toggleMute]);

  const value = useMemo<VoiceApi>(
    () => ({
      voice,
      mode,
      on: voice !== "off" && voice !== "error",
      level,
      heard,
      saying,
      missed,
      unsure,
      error,
      turn,
      barge,
      connect,
      disconnect,
      pttStart,
      pttEnd,
      switchMode,
      talkingTo,
      talkTo,
      hush,
      muted,
      toggleMute,
    }),
    [voice, mode, level, heard, saying, missed, unsure, error, turn, barge, connect, disconnect, pttStart, pttEnd, switchMode, talkingTo, talkTo, hush, muted, toggleMute],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useVoice(): VoiceApi {
  const value = useContext(Context);
  if (!value) throw new Error("useVoice outside VoiceProvider");
  return value;
}
