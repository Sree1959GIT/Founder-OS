import { BellOff, Bell, PanelLeftClose, PanelLeftOpen, SendHorizontal, Workflow } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";

import { AnswerCard } from "@/components/chat/AnswerCard";
import { VoiceControls } from "@/components/chat/VoiceControls";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { briefAnswer } from "@/lib/format";
import { cn } from "@/lib/utils";
import { teamOf, useWorkspace, type Turn } from "@/lib/workspace";

const STARTERS = ["What is our runway?", "Should we open a Dubai office?", "Why did burn change last month?"];

function Chip({ children, onClick, primary }: { children: string; onClick: () => void; primary?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        primary
          ? "h-9 rounded-full bg-signal px-3 text-xs font-semibold text-on-signal hover:bg-signal/90"
          : "h-9 rounded-full border border-border-strong bg-card px-3 text-xs text-foreground hover:bg-accent"
      }
    >
      {children}
    </button>
  );
}

function LaneTurn({ turn }: { turn: Exclude<Turn, { role: "you" } | { role: "advisor" }> }) {
  const { amendment, queued, slow } = useWorkspace();
  if (turn.role === "lane") {
    // Founder F23: a lane line is 3 sentences or fewer too; a longer one folds the rest.
    const { brief, more } = briefAnswer(turn.text);
    return (
      <div className="border-l-2 border-border-strong pl-2.5 text-[13px] leading-relaxed text-muted-foreground" data-testid="narration">
        <p>{more ? brief : turn.text}</p>
        {more ? (
          <details>
            <summary className="cursor-pointer">More</summary>
            <p className="mt-1 whitespace-pre-line">{turn.text}</p>
          </details>
        ) : null}
      </div>
    );
  }
  if (turn.role === "slow") {
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-attention-border bg-attention p-3" data-testid="slow-cloud" role="status">
        <p className="text-[13px] text-foreground">{turn.text}</p>
        {turn.status === "offered" ? (
          <div className="flex flex-wrap gap-2">
            <Chip primary onClick={() => void slow(turn.id, true)}>
              Continue on Qwen on our server
            </Chip>
            <Chip onClick={() => void slow(turn.id, false)}>Keep waiting</Chip>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            {turn.status === "local" ? `Moved to Qwen on our server: ${turn.reason}.` : "Still waiting for the cloud model."}
          </p>
        )}
      </div>
    );
  }
  if (turn.role === "amendment") {
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-attention-border bg-attention p-3" data-testid="amendment">
        <p className="text-[13px] text-foreground">{turn.offer ?? "That changes the decision. Restart with your change?"}</p>
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

interface PanelProps {
  /** Width on screens where the panels sit side by side (founder decision F). */
  width?: number;
  collapsed?: boolean;
  onToggle?: () => void;
  /** Opens the pop-up agent window (founder decision G). */
  onAgents?: () => void;
  agentsOpen?: boolean;
}

function AgentsButton({ onAgents, agentsOpen, compact }: { onAgents: () => void; agentsOpen: boolean; compact?: boolean }) {
  const { currentRun } = useWorkspace();
  const working = teamOf(currentRun).filter((a) => !["done", "failed", "cancelled"].includes(a.status)).length;
  return (
    <button
      type="button"
      aria-pressed={agentsOpen}
      aria-label={compact ? "Agent window" : undefined}
      onClick={onAgents}
      className="relative inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong bg-card px-2 text-xs text-muted-foreground hover:bg-accent"
      title="Open the agent window: what each agent is doing, in a window you can move."
    >
      <Workflow aria-hidden="true" className="h-3.5 w-3.5" />
      {compact ? null : "Agents"}
      {working > 0 ? (
        <span className="num rounded-full bg-signal px-1.5 text-[10px] font-semibold leading-4 text-on-signal" aria-label={`${working} working`}>
          {working}
        </span>
      ) : null}
    </button>
  );
}

export function AdvisorPanel({ width, collapsed = false, onToggle, onAgents, agentsOpen = false }: PanelProps = {}) {
  const { state, send, toggleQuiet, restoredTurns } = useWorkspace();
  const renderTurn = (turn: Turn) => {
    if (turn.role === "you") {
      return (
        <p
          key={turn.id}
          className="ml-6 self-end rounded-[12px_12px_4px_12px] bg-bubble px-3 py-2 text-[13.5px] leading-relaxed text-foreground"
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
  };
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
  // Founder RL2: one line on where the current run is. A stopped or failed run shows no stage.
  const current = state.currentRunId ? state.runs[state.currentRunId] : undefined;
  const progress = current && (current.status === "running" || current.status === "done") ? (current.progress ?? "") : "";

  // Scrolls the conversation only, never the page (M7b phone: the page jumped to the answer, away from the table).
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = list.current;
    if (el && el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight;
  }, [state.turns.length, lastAnswerLength, progress]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const question = text.trim();
    if (!question) return;
    setText("");
    void send(question);
  };

  const sized = width !== undefined;
  return (
    <>
    {collapsed ? (
      <aside
        aria-label="Executive Advisor (folded)"
        className="flex w-full shrink-0 items-center gap-2 border-b border-border bg-panel p-2 md:sticky md:top-0 md:h-[calc(100vh-61px)] md:w-11 md:flex-col md:border-b-0 md:border-r"
      >
        <button
          type="button"
          onClick={onToggle}
          aria-label="Show the Advisor panel"
          title="Show the Advisor panel"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border-strong bg-card text-muted-foreground hover:bg-accent"
        >
          <PanelLeftOpen aria-hidden="true" className="h-4 w-4" />
        </button>
        {onAgents ? <AgentsButton onAgents={onAgents} agentsOpen={agentsOpen} compact /> : null}
      </aside>
    ) : null}
    <aside
      aria-label="Executive Advisor"
      hidden={collapsed}
      style={sized ? ({ "--advisor-w": `${width}px` } as CSSProperties) : undefined}
      className={cn(
        "min-w-0 flex-[1_1_340px] flex-col bg-panel md:sticky md:top-0 md:h-[calc(100vh-61px)]",
        collapsed ? "hidden" : "flex",
        sized ? "md:w-[var(--advisor-w)] md:max-w-none md:flex-none" : "border-r border-border md:max-w-[380px]",
      )}
    >
      <div className="flex items-center justify-between gap-2 px-5 pb-2 pt-4">
        <span className="flex min-w-0 items-center gap-1.5">
          {onToggle ? (
            <button
              type="button"
              onClick={onToggle}
              aria-label="Fold the Advisor panel"
              title="Fold the Advisor panel (the conversation and voice carry on)"
              className="-ml-1.5 inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
            >
              <PanelLeftClose aria-hidden="true" className="h-4 w-4" />
            </button>
          ) : null}
          <span className="truncate text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Executive Advisor</span>
        </span>
        <span className="flex items-center gap-1.5">
        {onAgents ? <AgentsButton onAgents={onAgents} agentsOpen={agentsOpen} /> : null}
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
        </span>
      </div>

      <div ref={list} className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-2" aria-live="polite" aria-relevant="additions">
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
        {restoredTurns > 0 ? (
          // Founder F22: what was said in an earlier visit stays folded; the Advisor never recites it unasked.
          <details className="rounded-xl border border-border bg-card px-3 py-2 text-[13px]" data-testid="earlier-turns">
            <summary className="cursor-pointer text-muted-foreground">Earlier in this conversation ({restoredTurns})</summary>
            <div className="mt-2 flex flex-col gap-3">{state.turns.slice(0, restoredTurns).map(renderTurn)}</div>
          </details>
        ) : null}
        {state.turns.slice(restoredTurns).map(renderTurn)}
        {progress ? (
          <p className="text-xs text-muted-foreground" data-testid="run-progress" aria-live="polite">
            {progress}
          </p>
        ) : null}
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
    </>
  );
}
