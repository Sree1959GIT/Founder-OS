import { ArrowUpRight, Check, Focus, Mic, MicOff, PanelRightClose, PanelRightOpen, PanelsLeftRight, Radio, Square, Undo2, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";

import { Face, memberOf } from "@/components/boardroom/faces";
import { MicButton } from "@/components/chat/VoiceControls";
import { Pill } from "@/components/common";
import { Button } from "@/components/ui/button";
import type { DecisionFrame } from "@/lib/api";
import { caption, evidenceLine, seatPositions, seatSize, seatStatus, speakingId, teamSeats, useBoardroomRun, type SeatTone } from "@/lib/boardroom";
import { money, prefillAsk, signedMonths, tableTopic } from "@/lib/format";
import { proposedFrame, runsAfter } from "@/lib/proposal";
import { latencyLine } from "@/lib/voice";
import { useVoice } from "@/lib/voiceContext";
import { teamOf, useWorkspace, type AgentView, type RunView } from "@/lib/workspace";
import { cn } from "@/lib/utils";

interface Seat {
  id: string;
  type: string;
  name: string;
  status: { text: string; tone: SeatTone };
  title?: string;
}

const TONE_CLASS: Record<SeatTone, string> = {
  done: "text-ok",
  working: "text-signal-soft",
  next: "text-muted-foreground",
  slow: "text-signal-soft",
  switched: "text-info",
  failed: "text-danger",
  idle: "text-muted-foreground",
};

function seatsOf(run: RunView | null, voiceSpeaking: boolean): { seats: Seat[]; speaking: string | null } {
  const agents: AgentView[] = teamOf(run);
  const speaking = speakingId(run, agents, voiceSpeaking);
  const host: Seat = {
    id: "advisor",
    type: "advisor",
    name: "Advisor",
    status: speaking === "advisor" ? { text: "speaking", tone: "working" } : { text: "host", tone: "idle" },
  };
  if (agents.length) {
    return {
      speaking,
      seats: [
        host,
        ...teamSeats(agents).map((a) => ({
          id: a.id,
          type: a.type,
          name: a.name,
          status: seatStatus(a),
          title: a.fallback || (a.slowReason ? `Slow: ${a.slowReason}` : undefined),
        })),
      ],
    };
  }
  // Before the team starts (planning, or waiting for the member's OK): the proposed team takes its seats.
  const proposed = teamSeats(run?.proposedTeam ?? []).map((a) => ({
    id: a.id,
    type: a.type,
    name: a.name,
    status: run?.awaitingApproval ? { text: "needs your OK", tone: "next" as SeatTone } : { text: "next", tone: "next" as SeatTone },
  }));
  return { speaking, seats: [host, ...proposed] };
}

/**
 * One seat (founder F25, F27): the face in its own colour is a button ("Talk to …"); under it a name tag filled with
 * the agent's colour, its status, and while its voice speaks a "Speaking" tag with a Stop button.
 */
function SeatView({ seat, speaking, voiceSpeaking, size = 56 }: { seat: Seat; speaking: boolean; voiceSpeaking: boolean; size?: number }) {
  const voice = useVoice();
  const color = memberOf(seat.type).color;
  const talking = voice.talkingTo?.id === seat.id;
  return (
    <div className="flex w-[124px] flex-col items-center gap-1 text-center" data-testid="seat" data-type={seat.type} title={seat.title}>
      <button
        type="button"
        aria-label={talking ? `Stop talking to ${seat.name}` : `Talk to ${seat.name}`}
        aria-pressed={talking}
        onClick={() => void voice.talkTo(seat.id, seat.name)}
        className="rounded-full p-1 transition-shadow hover:shadow-[0_0_0_3px_var(--seat)]"
        style={{ "--seat": color, boxShadow: talking ? `0 0 0 3px ${color}` : `0 0 0 2px ${color}66` } as CSSProperties}
        data-testid="seat-face"
      >
        <Face type={seat.type} size={size} speaking={speaking} glow={`${color}99`} />
      </button>
      <span
        className="max-w-full rounded-full px-2 text-[12px] font-semibold leading-5 text-ink [overflow-wrap:anywhere]"
        style={{ backgroundColor: color }}
        data-testid="seat-name"
      >
        {seat.name}
      </span>
      {voiceSpeaking ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-signal py-0.5 pl-2 pr-0.5 text-[11px] font-bold uppercase tracking-[0.08em] text-on-signal" data-testid="speaking-tag">
          Speaking
          <button
            type="button"
            onClick={voice.hush}
            aria-label={`Stop ${seat.name} speaking (Esc)`}
            title="Stop speaking (Esc). The team keeps working."
            className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-ink text-paper"
          >
            <Square aria-hidden="true" className="h-3 w-3 fill-current" />
          </button>
        </span>
      ) : (
        <span className={cn("rounded-md bg-card/90 px-1.5 text-[11px] leading-4", TONE_CLASS[seat.status.tone])} data-testid="seat-status">
          {seat.status.text}
        </span>
      )}
    </div>
  );
}

/** Desktop: the oval glass table with the topic in the middle and one seat per agent around it (founder F25). */
function Table({ question, seats, speaking, voiceSeat }: { question: string; seats: Seat[]; speaking: string | null; voiceSeat: string | null }) {
  const places = seatPositions(seats.length);
  const size = seatSize(seats.length);
  return (
    <section aria-label="The boardroom table" className="relative h-[440px] w-full xl:h-[470px]" data-testid="boardroom-table" data-seats={seats.length}>
      <div className="glass absolute inset-x-[17%] inset-y-[24%] flex items-center justify-center rounded-[50%] px-[7%] shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_30px_80px_-30px_rgba(0,0,0,0.8)]">
        <div className="max-w-full rounded-2xl bg-card/85 px-5 py-3 text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">On the table</p>
          <h1 className="display line-clamp-2 text-[24px] leading-tight text-foreground xl:text-[30px]" data-testid="table-topic">
            {question}
          </h1>
        </div>
      </div>
      <ul className="contents" aria-label="Who is at the table">
        {seats.map((seat, i) => {
          const place = places[i] ?? { left: 50, top: 50 };
          return (
            <li key={seat.id} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${place.left}%`, top: `${place.top}%` }}>
              <SeatView seat={seat} speaking={speaking === seat.id} voiceSpeaking={voiceSeat === seat.id} size={size} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Phone, or a narrow centre (founder F26): the topic, a "Speaking now" card and a strip of the other faces. */
function PhoneStage({ question, seats, speaking, voiceSeat, line }: { question: string; seats: Seat[]; speaking: string | null; voiceSeat: string | null; line: string }) {
  const now = seats.find((s) => s.id === speaking) ?? seats[0];
  const others = seats.filter((s) => s !== now);
  return (
    <section aria-label="The boardroom" className="flex flex-col gap-3" data-testid="phone-stage">
      <h1 className="display rounded-2xl bg-card px-4 py-3 text-[26px] leading-tight" data-testid="table-topic">
        {question}
      </h1>
      {now ? (
        <div className="glass flex items-center gap-3 rounded-2xl p-3">
          <SeatView seat={now} speaking={speaking === now.id} voiceSpeaking={voiceSeat === now.id} size={56} />
          <div className="min-w-0 flex-1 rounded-xl bg-card px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-signal-soft">{speaking ? "Speaking now" : "At the table"} · {now.name}</p>
            <p className="line-clamp-3 text-[14px] leading-snug text-foreground" aria-live="polite">
              {line || now.status.text}
            </p>
          </div>
        </div>
      ) : null}
      {others.length ? (
        <ul className="-mx-4 flex snap-x gap-1 overflow-x-auto px-4 pb-1" aria-label="Who is at the table">
          {others.map((seat) => (
            <li key={seat.id} className="snap-start">
              <SeatView seat={seat} speaking={speaking === seat.id} voiceSpeaking={voiceSeat === seat.id} size={48} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/**
 * The LIVE caption bar (founder F27): what is being said and who the member is talking to. Voice starts on the faces
 * (no "Start voice" button here); while voice is on, Mute (M) and Voice off. Neither stops the team.
 */
function CaptionBar({ line, who }: { line: string; who: "you" | "advisor" }) {
  const voice = useVoice();
  const notice = voice.error ?? (voice.missed && !voice.heard ? "Didn't catch that. Say it again." : voice.unsure && !voice.heard ? `Did you say “${voice.unsure}”? Say yes, or say it again.` : "");
  const lead = voice.talkingTo ? `Talking to ${voice.talkingTo.name}` : voice.on ? (voice.mode === "ptt" ? "Hold Space to talk" : "Listening") : "Tap a face to talk";
  return (
    <div className="sticky bottom-3 z-20 hidden flex-wrap items-center gap-x-3 gap-y-1.5 rounded-2xl border border-border-strong bg-card px-4 py-2.5 shadow-xl md:flex" data-testid="caption-bar">
      <span
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-signal px-2 py-0.5 text-[11px] font-bold tracking-[0.1em] text-on-signal"
        title={voice.turn || voice.barge ? `Last turn, measured on the backend: ${latencyLine(voice.turn, voice.barge)}` : undefined}
        data-testid="live-pill"
      >
        <Radio aria-hidden="true" className="h-3 w-3" />
        LIVE
      </span>
      <span className="shrink-0 text-[13px] font-semibold text-signal-soft" data-testid="talking-to">
        {lead}
      </span>
      <p className="min-w-[12rem] flex-1 text-[14px] text-foreground" aria-live="polite" title={line}>
        {notice ? (
          <span role={voice.error ? "alert" : undefined} className={voice.error ? "text-danger" : "text-muted-foreground"}>
            {notice}
          </span>
        ) : line ? (
          <span className="line-clamp-2">
            <span className="text-muted-foreground">{who === "you" ? "You: " : "Advisor: "}</span>
            {line}
          </span>
        ) : (
          <span className="text-muted-foreground">The team's words appear here as they talk.</span>
        )}
      </p>
      {voice.on ? (
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            type="button"
            variant="outline"
            className="h-11 gap-1.5 rounded-full"
            aria-pressed={voice.muted}
            title="Mute the microphone (M)"
            onClick={voice.toggleMute}
          >
            {voice.muted ? <MicOff aria-hidden="true" className="h-4 w-4" /> : <Mic aria-hidden="true" className="h-4 w-4" />}
            {voice.muted ? "Muted" : "Mute"}
          </Button>
          <Button type="button" variant="ghost" className="h-11 rounded-full" title="End the voice. The team keeps working." onClick={voice.disconnect}>
            Voice off
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** Below this width the centre shows the phone-style stage instead of the table (founder F26). */
export const TABLE_MIN = 640;

/** The centre's own width (ResizeObserver); 0 where it cannot be measured (tests), which counts as wide. */
function useOwnWidth(): [React.RefObject<HTMLElement>, number] {
  const ref = useRef<HTMLElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => setWidth(entries[0]?.contentRect.width ?? 0));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** The centre of the Boardroom (table, or the phone-style stage) and its caption bar wrap the existing canvas cards. */
export function BoardroomStage({ children, focus }: { children: React.ReactNode; focus?: { on: boolean; toggle: () => void } }) {
  const { state } = useWorkspace();
  const voice = useVoice();
  const { run, decision } = useBoardroomRun();
  const { seats, speaking } = seatsOf(run, voice.voice === "speaking");
  // The voice speaks as the Advisor: its "Speaking" tag and Stop button sit under the Advisor's face.
  const voiceSeat = voice.voice === "speaking" ? "advisor" : null;
  const shown = decision ?? run;
  // Founder F24: the current topic ("Dubai office"), updated with each new question; never "This decision".
  const question = tableTopic(
    decision ? { message: decision.message, subject: decision.frame?.subject } : null,
    run ? { message: run.message, isDecision: run === decision || Boolean(run.frame || run.decisionType) } : null,
  );
  const said = caption(state.turns, voice.saying, voice.heard);
  const [ref, width] = useOwnWidth();
  const compact = width > 0 && width < TABLE_MIN;
  return (
    <main
      ref={ref}
      className="relative order-1 flex min-w-0 flex-[999_1_0%] flex-col gap-4 px-4 py-4 md:order-none md:px-6"
      data-testid="boardroom"
      data-compact={compact ? "true" : undefined}
    >
      {focus ? (
        <div className="hidden justify-end md:flex">
          <Button type="button" variant="outline" size="sm" className="min-h-[44px] gap-1.5 rounded-full" aria-pressed={focus.on} onClick={focus.toggle} data-testid="focus-team">
            {focus.on ? <PanelsLeftRight aria-hidden="true" className="h-4 w-4" /> : <Focus aria-hidden="true" className="h-4 w-4" />}
            {focus.on ? "Show panels" : "Focus on the team"}
          </Button>
        </div>
      ) : null}
      {compact ? null : (
        <div className="hidden md:block">
          <Table question={question} seats={seats} speaking={speaking} voiceSeat={voiceSeat} />
        </div>
      )}
      <div className={compact ? "" : "md:hidden"}>
        <PhoneStage question={question} seats={seats} speaking={speaking} voiceSeat={voiceSeat} line={said?.text ?? ""} />
      </div>
      <OptionsPanel phone />
      {shown?.reversibility || shown?.result?.memo?.review_date ? (
        <div className="flex flex-wrap gap-2">
          {shown?.reversibility === "one_way" ? <Pill tone="amber">One-way door · full analysis</Pill> : null}
          {shown?.reversibility === "two_way" ? <Pill tone="info">Two-way door · light analysis</Pill> : null}
          {shown?.result?.memo?.review_date ? (
            <Pill>
              Review on <span className="num">{shown.result.memo.review_date}</span>
            </Pill>
          ) : null}
        </div>
      ) : null}
      {children}
      <CaptionBar line={said?.text ?? ""} who={said?.who ?? "advisor"} />
    </main>
  );
}

function useSetAside(): [Set<string>, (name: string) => void] {
  const [aside, setAside] = useState<Set<string>>(new Set());
  const toggle = (name: string) =>
    setAside((s) => {
      const next = new Set(s);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  return [aside, toggle];
}

/** "Go with X": the Advisor has the Memo Writer write it up (the member still decides in the memo). */
const acceptText = (option: string) => `Go with "${option}": write the decision memo.`;

export function OptionsPanel({
  width,
  phone = false,
  collapsed = false,
  onToggle,
}: {
  width?: number;
  phone?: boolean;
  /** Founder F26: the right panel folds to a narrow strip, like the Advisor panel. */
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  const { state, send } = useWorkspace();
  const { decision } = useBoardroomRun();
  const [aside, toggleAside] = useSetAside();
  const frame: DecisionFrame | null = decision?.frame ? proposedFrame(decision.frame, runsAfter(decision, Object.values(state.runs))) : null;
  const currency = frame?.currency || frame?.cost_model?.currency || "USD";
  const evidence = evidenceLine(decision);
  if (!phone && collapsed) {
    return (
      <aside aria-label="Options so far (folded)" className="hidden w-11 shrink-0 flex-col items-center gap-2 bg-card py-3 lg:sticky lg:top-0 lg:flex lg:h-[calc(100vh-61px)]" data-testid="options-folded">
        <Button type="button" variant="ghost" size="icon" className="h-11 w-11" aria-label="Show the options panel" title="Show the options" onClick={onToggle}>
          <PanelRightOpen aria-hidden="true" className="h-4 w-4" />
        </Button>
        <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground [writing-mode:vertical-rl]">Options</span>
      </aside>
    );
  }
  return (
    <aside
      aria-label={phone ? "Options so far (phone)" : "Options so far"}
      style={width !== undefined ? ({ "--options-w": `${width}px` } as CSSProperties) : undefined}
      className={
        phone
          ? "flex flex-col gap-3 rounded-2xl bg-card p-4 lg:hidden"
          : "hidden w-[var(--options-w,340px)] shrink-0 flex-col gap-3 bg-card px-4 py-4 lg:sticky lg:top-0 lg:flex lg:h-[calc(100vh-61px)] lg:overflow-y-auto"
      }
      data-testid={phone ? "options-phone" : "options-panel"}
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Options so far</h2>
        <span className="flex-1" />
        {evidence ? (
          <a href="#/activity" className="inline-flex items-center gap-1 text-xs" data-testid="evidence-link">
            {evidence}
            <ArrowUpRight aria-hidden="true" className="h-3 w-3" />
          </a>
        ) : null}
        {!phone && onToggle ? (
          <Button type="button" variant="ghost" size="icon" className="h-11 w-11 shrink-0" aria-label="Fold the options panel" title="Fold the options" onClick={onToggle}>
            <PanelRightClose aria-hidden="true" className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
      {decision?.awaitingApproval ? (
        <a href="#/activity" className="rounded-xl border border-attention-border bg-attention p-3 text-[13px] text-signal-soft hover:no-underline">
          The team needs your OK before it starts.
        </a>
      ) : null}
      {!frame || frame.options.length === 0 ? (
        <p className="text-[13px] leading-relaxed text-muted-foreground">
          The options appear here as the team works, each with its cost and what it does to your runway.
        </p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {frame.options.map((option) => {
            const leading = option.name === frame.default_option;
            const setAside = aside.has(option.name);
            return (
              <li
                key={option.name}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border p-3",
                  leading && !setAside ? "border-signal bg-attention" : "border-border bg-background",
                  setAside && "opacity-60",
                )}
                data-testid={leading ? "option-leading" : "option"}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("text-[14px] font-semibold", setAside && "line-through")}>{option.name}</span>
                  {leading ? <Pill tone="amber">Leading</Pill> : null}
                  {setAside ? <Pill>Set aside</Pill> : null}
                </div>
                {option.modelled ? (
                  <dl className="grid grid-cols-3 gap-1 text-[11px] text-muted-foreground">
                    <div>
                      <dt>One-off</dt>
                      <dd className="num text-[13px] text-foreground [overflow-wrap:anywhere]">{money(option.one_off, currency, 0)}</dd>
                    </div>
                    <div>
                      <dt>A month</dt>
                      <dd className="num text-[13px] text-foreground [overflow-wrap:anywhere]">{money(option.monthly, currency, 0)}</dd>
                    </div>
                    <div>
                      <dt>Runway</dt>
                      <dd className="num text-[13px] text-foreground [overflow-wrap:anywhere]">{signedMonths(option.runway_change_months)}</dd>
                    </div>
                  </dl>
                ) : (
                  <p className="text-xs text-muted-foreground">Cost not modelled yet</p>
                )}
                {option.trade_off ? <p className="text-xs leading-relaxed text-muted-foreground">{option.trade_off}</p> : null}
                <div className="flex flex-wrap gap-1.5">
                  <Button
                    type="button"
                    size="sm"
                    variant={leading ? "default" : "outline"}
                    className="min-h-[44px] gap-1 rounded-full"
                    disabled={setAside || state.sending}
                    onClick={() => void send(acceptText(option.name))}
                  >
                    <Check aria-hidden="true" className="h-3.5 w-3.5" />
                    Accept
                  </Button>
                  <Button type="button" size="sm" variant="outline" className="min-h-[44px] rounded-full" onClick={() => prefillAsk(`Tell me more about "${option.name}": `)}>
                    Ask more
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="min-h-[44px] gap-1 rounded-full"
                    aria-pressed={setAside}
                    onClick={() => toggleAside(option.name)}
                  >
                    {setAside ? <Undo2 aria-hidden="true" className="h-3.5 w-3.5" /> : <X aria-hidden="true" className="h-3.5 w-3.5" />}
                    {setAside ? "Undo" : "Reject"}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}

/** Phone: a sticky bottom bar with "Accept…" for the leading option and a big "Hold to talk". */
export function PhoneBar() {
  const { state, send } = useWorkspace();
  const { decision } = useBoardroomRun();
  const leading = decision?.frame ? proposedFrame(decision.frame, runsAfter(decision, Object.values(state.runs))).default_option : "";
  return (
    <div className="print-hide fixed inset-x-0 bottom-0 z-40 flex items-center gap-2 border-t border-border-strong bg-card px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 md:hidden" data-testid="phone-bar">
      {leading ? (
        <Button type="button" className="h-14 min-w-0 flex-1 rounded-full text-[15px] font-semibold" disabled={state.sending} onClick={() => void send(acceptText(leading))}>
          <span className="truncate">Accept {leading}…</span>
        </Button>
      ) : (
        <span className="min-w-0 flex-1 text-[13px] text-muted-foreground">{memberOf("advisor").role}</span>
      )}
      <MicButton big label="Hold to talk" />
    </div>
  );
}
