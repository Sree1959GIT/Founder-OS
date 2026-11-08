import { BellOff, Bell, SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { AnswerCard } from "@/components/chat/AnswerCard";
import { VoiceControls } from "@/components/chat/VoiceControls";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { useWorkspace, type Turn } from "@/lib/workspace";

const STARTERS = ["What is our runway?", "Should we open a Dubai office?", "Why did burn change last month?"];

function Chip({ children, onClick, primary }: { children: string; onClick: () => void; primary?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        primary
          ? "h-9 rounded-full bg-signal px-3 text-xs font-semibold text-[#1A1206] hover:bg-signal/90"
          : "h-9 rounded-full border border-border-strong bg-card px-3 text-xs text-foreground hover:bg-accent"
      }
    >
      {children}
    </button>
  );
}

function LaneTurn({ turn }: { turn: Exclude<Turn, { role: "you" } | { role: "advisor" }> }) {
  const { amendment, queued } = useWorkspace();
  if (turn.role === "lane") {
    return (
      <p className="border-l-2 border-border-strong pl-2.5 text-[13px] leading-relaxed text-muted-foreground" data-testid="narration">
        {turn.text}
      </p>
    );
  }
  if (turn.role === "amendment") {
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-[#4A3A1C] bg-[#1A1610] p-3" data-testid="amendment">
        <p className="text-[13px] text-foreground">That changes the request. Restart with your change?</p>
        <p className="text-xs text-muted-foreground">{turn.text}</p>
        {turn.status === "offered" ? (
          <div className="flex flex-wrap gap-2">
            <Chip primary onClick={() => void amendment(turn.amendmentId, true)}>
              Restart with my change
            </Chip>
            <Chip onClick={() => void amendment(turn.amendmentId, false)}>Keep going</Chip>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">{turn.status === "accepted" ? "Restarted." : "Carried on as it was."}</p>
        )}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border-strong bg-card p-3" data-testid="queued">
      <p className="text-xs text-muted-foreground">
        {turn.status === "queued" ? "Queued for when this run finishes" : turn.status === "offered" ? "Your queued question" : "Queued question"}
      </p>
      <p className="text-[13px] text-foreground">{turn.text}</p>
      {turn.status === "offered" ? (
        <div className="flex flex-wrap gap-2">
          <Chip primary onClick={() => void queued(turn.queueId, true)}>
            Ask it now
          </Chip>
          <Chip onClick={() => void queued(turn.queueId, false)}>Drop it</Chip>
        </div>
      ) : null}
      {turn.status === "accepted" ? <p className="text-xs text-muted-foreground">Asked.</p> : null}
      {turn.status === "declined" ? <p className="text-xs text-muted-foreground">Dropped.</p> : null}
    </div>
  );
}

export function AdvisorPanel() {
  const { state, send, toggleQuiet } = useWorkspace();
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  // "Enter your figures" on the badge puts a start in this box.
  useEffect(() => {
    const onPrefill = (e: Event) => {
      setText((e as CustomEvent<string>).detail ?? "");
      input.current?.focus();
    };
    window.addEventListener("founderos:prefill", onPrefill);
    return () => window.removeEventListener("founderos:prefill", onPrefill);
  }, []);
  const lastAnswerLength = state.currentRunId ? (state.runs[state.currentRunId]?.answer.length ?? 0) : 0;

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [state.turns.length, lastAnswerLength]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const question = text.trim();
    if (!question) return;
    setText("");
    void send(question);
  };

  return (
    <aside
      aria-label="Executive Advisor"
      className="flex min-w-0 flex-[1_1_340px] flex-col border-r border-border bg-panel md:sticky md:top-0 md:h-[calc(100vh-61px)] md:max-w-[380px]"
    >
      <div className="flex items-center justify-between gap-2 px-5 pb-2 pt-4">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Executive Advisor</span>
        <button
          type="button"
          aria-pressed={state.quiet}
          onClick={() => void toggleQuiet()}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong bg-card px-2 text-xs text-muted-foreground hover:bg-accent"
          title="Quiet mode: the team works without narrating. Questions it needs answered still come through."
        >
          {state.quiet ? <BellOff aria-hidden="true" className="h-3.5 w-3.5" /> : <Bell aria-hidden="true" className="h-3.5 w-3.5" />}
          {state.quiet ? "Quiet on" : "Quiet off"}
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-2" aria-live="polite" aria-relevant="additions">
        {state.turns.length === 0 ? (
          <div className="flex flex-1 flex-col justify-center gap-3">
            <p className="leading-relaxed text-muted-foreground">
              The advisor questions your ideas and tests them against your real numbers.
            </p>
            <div className="flex flex-wrap gap-2">
              {STARTERS.map((s) => (
                <Chip key={s} onClick={() => void send(s)}>
                  {s}
                </Chip>
              ))}
            </div>
          </div>
        ) : null}
        {state.turns.map((turn) => {
          if (turn.role === "you") {
            return (
              <p
                key={turn.id}
                className="ml-6 self-end rounded-[12px_12px_4px_12px] bg-[#1F2A3A] px-3 py-2 text-[13.5px] leading-relaxed text-foreground"
              >
                {turn.text}
              </p>
            );
          }
          if (turn.role === "advisor") {
            const run = state.runs[turn.runId];
            return run ? <AnswerCard key={turn.id} run={run} /> : null;
          }
          return <LaneTurn key={turn.id} turn={turn} />;
        })}
        <div ref={end} />
      </div>

      {state.error ? (
        <div className="px-4 pb-2">
          <ErrorNote>{state.error}</ErrorNote>
        </div>
      ) : null}

      <form onSubmit={submit} className="m-4 mt-2 flex flex-wrap items-center gap-2 rounded-2xl border border-border-strong bg-card p-3">
        <label htmlFor="ask" className="sr-only">
          Ask the advisor
        </label>
        <input
          id="ask"
          ref={input}
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask the advisor"
          autoComplete="off"
          className="h-11 min-w-0 flex-1 rounded-lg border border-border-strong bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground"
        />
        <Button type="submit" size="icon" aria-label="Send" disabled={!text.trim()} className="h-11 w-11 rounded-lg">
          <SendHorizontal aria-hidden="true" />
        </Button>
        <VoiceControls />
      </form>
    </aside>
  );
}
