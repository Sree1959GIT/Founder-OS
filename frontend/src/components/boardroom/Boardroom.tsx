import { ArrowUpRight, Check, Radio, Undo2, X } from "lucide-react";
import { useState, type CSSProperties } from "react";

import { Face, memberOf } from "@/components/boardroom/faces";
import { MicButton } from "@/components/chat/VoiceControls";
import { Pill } from "@/components/common";
import { Button } from "@/components/ui/button";
import type { DecisionFrame } from "@/lib/api";
import { caption, evidenceLine, seatStatus, speakingId, useBoardroomRun, type SeatTone } from "@/lib/boardroom";
import { decisionTitle, money, prefillAsk, runTitle, signedMonths } from "@/lib/format";
import { proposedFrame, runsAfter } from "@/lib/proposal";
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
        ...agents.map((a) => ({
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
  const proposed = (run?.proposedTeam ?? []).map((a) => ({
    id: a.id,
    type: a.type,
    name: a.name,
    status: run?.awaitingApproval ? { text: "needs your OK", tone: "next" as SeatTone } : { text: "next", tone: "next" as SeatTone },
  }));
  return { speaking, seats: [host, ...proposed] };
}

function SeatView({ seat, speaking, size = 56 }: { seat: Seat; speaking: boolean; size?: number }) {
  return (
    <div className="flex w-[124px] flex-col items-center gap-1 text-center" data-testid="seat" title={seat.title}>
      <Face type={seat.type} size={size} speaking={speaking} dim={seat.status.tone === "idle" && seat.type !== "advisor"} />
      <span className="max-w-full truncate rounded-md bg-card/90 px-1.5 text-[12px] font-medium leading-5 text-foreground">{seat.name}</span>
      <span className={cn("rounded-md bg-card/90 px-1.5 text-[11px] leading-4", TONE_CLASS[seat.status.tone])} data-testid="seat-status">
        {seat.status.text}
      </span>
    </div>
  );
}

/** Desktop: the oval glass table with the question in the middle and the team around it. */
function Table({ question, seats, speaking }: { question: string; seats: Seat[]; speaking: string | null }) {
  const n = Math.max(seats.length, 1);
  return (
    <section aria-label="The boardroom table" className="relative hidden h-[400px] w-full md:block xl:h-[440px]" data-testid="boardroom-table">
      <div className="glass absolute inset-x-[13%] inset-y-[21%] flex items-center justify-center rounded-[50%] px-[9%] shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_30px_80px_-30px_rgba(0,0,0,0.8)]">
        <div className="rounded-2xl bg-card/85 px-5 py-3 text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">On the table</p>
          <h1 className="display line-clamp-3 text-[26px] leading-tight text-foreground xl:text-[32px]">{question}</h1>
        </div>
      </div>
      <ul className="contents" aria-label="Who is at the table">
        {seats.map((seat, i) => {
          const angle = (-90 + (i * 360) / n) * (Math.PI / 180);
          const style: CSSProperties = {
            left: `${50 + 45 * Math.cos(angle)}%`,
            top: `${50 + 41 * Math.sin(angle)}%`,
          };
          return (
            <li key={seat.id} className="absolute -translate-x-1/2 -translate-y-1/2" style={style}>
              <SeatView seat={seat} speaking={speaking === seat.id} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Phone: the question, a "Speaking now" card and a strip of the other faces. */
function PhoneStage({ question, seats, speaking, line }: { question: string; seats: Seat[]; speaking: string | null; line: string }) {
  const now = seats.find((s) => s.id === speaking) ?? seats[0];
  const others = seats.filter((s) => s !== now);
  return (
    <section aria-label="The boardroom" className="flex flex-col gap-3 md:hidden" data-testid="phone-stage">
      <h1 className="display rounded-2xl bg-card px-4 py-3 text-[26px] leading-tight">{question}</h1>
      {now ? (
        <div className="glass flex items-center gap-3 rounded-2xl p-3">
          <Face type={now.type} size={60} speaking={speaking === now.id} />
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
              <SeatView seat={seat} speaking={speaking === seat.id} size={48} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** The LIVE caption bar: what is being said, plus "Hold to talk" (desktop; the phone has its own bottom bar). */
function CaptionBar({ line, who }: { line: string; who: "you" | "advisor" }) {
  return (
    <div className="sticky bottom-3 z-20 hidden items-center gap-3 rounded-2xl border border-border-strong bg-card px-4 py-2.5 shadow-xl md:flex" data-testid="caption-bar">
      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-signal px-2 py-0.5 text-[11px] font-bold tracking-[0.1em] text-on-signal">
        <Radio aria-hidden="true" className="h-3 w-3" />
        LIVE
      </span>
      <p className="min-w-0 flex-1 truncate text-[14px] text-foreground" aria-live="polite" title={line}>
        {line ? (
          <>
            <span className="text-muted-foreground">{who === "you" ? "You: " : "Advisor: "}</span>
            {line}
          </>
        ) : (
          <span className="text-muted-foreground">The team's words appear here as they talk.</span>
        )}
      </p>
      <MicButton big label="Hold to talk" />
    </div>
  );
}

/** The centre of the Boardroom (table, or the phone stage) and its caption bar wrap the existing canvas cards. */
export function BoardroomStage({ children }: { children: React.ReactNode }) {
  const { state } = useWorkspace();
  const voice = useVoice();
  const { run, decision } = useBoardroomRun();
  const { seats, speaking } = seatsOf(run, voice.voice === "speaking");
  const shown = decision ?? run;
  const question = decision ? decisionTitle(decision.frame?.subject, runTitle(decision.message)) : runTitle(run?.message ?? "Your question");
  const said = caption(state.turns, voice.saying, voice.heard);
  return (
    <main className="relative order-1 flex min-w-0 flex-[999_1_560px] flex-col gap-4 px-4 py-4 md:order-none md:px-6" data-testid="boardroom">
      <Table question={question} seats={seats} speaking={speaking} />
      <PhoneStage question={question} seats={seats} speaking={speaking} line={said?.text ?? ""} />
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

export function OptionsPanel({ width, phone = false }: { width?: number; phone?: boolean }) {
  const { state, send } = useWorkspace();
  const { decision } = useBoardroomRun();
  const [aside, toggleAside] = useSetAside();
  const frame: DecisionFrame | null = decision?.frame ? proposedFrame(decision.frame, runsAfter(decision, Object.values(state.runs))) : null;
  const currency = frame?.currency || frame?.cost_model?.currency || "USD";
  const evidence = evidenceLine(decision);
  return (
    <aside
      aria-label={phone ? "Options so far (phone)" : "Options so far"}
      style={width !== undefined ? ({ "--options-w": `${width}px` } as CSSProperties) : undefined}
      className={
        phone
          ? "flex flex-col gap-3 rounded-2xl bg-card p-4 md:hidden"
          : "hidden w-[var(--options-w,340px)] shrink-0 flex-col gap-3 bg-card px-4 py-4 md:sticky md:top-0 md:flex md:h-[calc(100vh-61px)] md:overflow-y-auto"
      }
      data-testid={phone ? "options-phone" : "options-panel"}
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Options so far</h2>
        {evidence ? (
          <a href="#/activity" className="inline-flex items-center gap-1 text-xs" data-testid="evidence-link">
            {evidence}
            <ArrowUpRight aria-hidden="true" className="h-3 w-3" />
          </a>
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
                      <dd className="num text-[13px] text-foreground">{money(option.one_off, currency, 0)}</dd>
                    </div>
                    <div>
                      <dt>A month</dt>
                      <dd className="num text-[13px] text-foreground">{money(option.monthly, currency, 0)}</dd>
                    </div>
                    <div>
                      <dt>Runway</dt>
                      <dd className="num text-[13px] text-foreground">{signedMonths(option.runway_change_months)}</dd>
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
