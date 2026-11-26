import { GripHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent } from "react";

import { Pill } from "@/components/common";
import { agentBars, countAgents, isPosition, keepOnScreen, stageNodes, type NodeState, type Position } from "@/lib/agentGraph";
import { agentCode, runTitle, safeStep, seconds, stepWords, STATUS_PROGRESS, STATUS_WORDS } from "@/lib/format";
import { readJson, writeJson } from "@/lib/layout";
import { cn } from "@/lib/utils";
import { useWorkspace, type AgentView } from "@/lib/workspace";

export const WINDOW_KEY = "founderos.agentwindow.v1";
const WIDTH = 460;

const NODE_TONE: Record<NodeState, string> = {
  waiting: "border-border-strong text-muted-foreground",
  active: "border-signal text-signal-soft",
  done: "border-ok text-ok",
  failed: "border-danger text-danger",
};
const NODE_WORDS: Record<NodeState, string> = { waiting: "waiting", active: "working", done: "done", failed: "stopped" };

function ringColour(status: string): string {
  if (status === "done") return "stroke-ok";
  if (status === "failed" || status === "cancelled") return "stroke-danger";
  if (status === "queued") return "stroke-muted-foreground";
  return "stroke-signal";
}

/** A small ring that fills as the agent moves through its steps, with its two-letter code inside. */
function Ring({ agent }: { agent: AgentView }) {
  const value = agent.status === "done" ? 100 : (STATUS_PROGRESS[agent.status] ?? 35);
  const r = 15;
  const length = 2 * Math.PI * r;
  const working = !["done", "failed", "cancelled", "queued"].includes(agent.status);
  return (
    <svg viewBox="0 0 36 36" className="h-9 w-9 shrink-0" role="img" aria-label={`${STATUS_WORDS[agent.status] ?? agent.status}, ${value}%`}>
      <circle cx="18" cy="18" r={r} className="fill-none stroke-background" strokeWidth="3.5" />
      <circle
        cx="18"
        cy="18"
        r={r}
        className={cn("fill-none transition-[stroke-dashoffset] duration-500", ringColour(agent.status), working && "motion-safe:animate-pulse")}
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeDasharray={length}
        strokeDashoffset={length * (1 - value / 100)}
        transform="rotate(-90 18 18)"
      />
      <text x="18" y="21.5" textAnchor="middle" className="fill-foreground font-mono text-[9px] font-semibold">
        {agentCode(agent.type)}
      </text>
    </svg>
  );
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function startPosition(): Position {
  const w = typeof window !== "undefined" ? window.innerWidth : 1280;
  return { x: Math.max(16, w - WIDTH - 32), y: 80 };
}

/**
 * Founder decision G (M6): a window you can move, opened from the Advisor panel, with a simple picture of the team:
 * the run's four steps, then each agent's progress ring, its current step and a bar on the run's clock. Its place is
 * kept per viewer. Cancel and re-run stay on the Activity tab, which the window links to.
 */
export function AgentWindow({ onClose }: { onClose: () => void }) {
  const { currentRun: run } = useWorkspace();
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ dx: number; dy: number } | null>(null);
  const [pos, setPos] = useState<Position>(() => readJson(WINDOW_KEY, startPosition(), isPosition));
  const now = useNow(run?.status === "running");

  const viewport = () => ({ w: window.innerWidth, h: window.innerHeight });
  const size = () => ({ w: box.current?.offsetWidth ?? WIDTH, h: box.current?.offsetHeight ?? 300 });

  // A stored place from a bigger screen is pulled back into view, now and when the browser is resized.
  useEffect(() => {
    const fit = () => setPos((p) => keepOnScreen(p, size(), viewport()));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  useEffect(() => {
    if (!drag.current) writeJson(WINDOW_KEY, pos);
  }, [pos]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const down = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    drag.current = { dx: e.clientX - pos.x, dy: e.clientY - pos.y };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    setPos(keepOnScreen({ x: e.clientX - drag.current.dx, y: e.clientY - drag.current.dy }, size(), viewport()));
  };
  const up = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    drag.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    writeJson(WINDOW_KEY, pos);
  };

  const nodes = stageNodes(run);
  const counts = countAgents(run);
  const bars = run ? agentBars(run, now) : [];

  return (
    <div
      ref={box}
      role="dialog"
      aria-label="Agent window"
      data-testid="agent-window"
      style={{ left: pos.x, top: pos.y, width: WIDTH }}
      className="fixed z-50 flex max-h-[min(640px,calc(100vh-24px))] max-w-[calc(100vw-16px)] flex-col overflow-hidden rounded-xl border border-border-strong bg-panel shadow-2xl"
    >
      <div
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        className="flex cursor-move touch-none select-none items-center gap-2 border-b border-border bg-card px-3 py-2"
        title="Drag to move"
      >
        <GripHorizontal aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
        <span className="flex-1 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Agents</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close the agent window"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
        >
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-col gap-3 overflow-y-auto p-3">
        {run ? (
          <>
            <div>
              <p className="truncate text-[13px] font-medium" title={run.message}>
                {runTitle(run.message, 70)}
              </p>
              {run.progress ? <p className="text-xs text-muted-foreground">{run.progress}</p> : null}
            </div>

            <ol className="flex items-center" aria-label="Where the run is">
              {nodes.map((node, i) => (
                <li key={node.key} className="flex flex-1 items-center last:flex-none">
                  <span
                    className={cn("flex flex-col items-center gap-0.5 rounded-lg border px-2 py-1 text-[11px] leading-tight", NODE_TONE[node.state])}
                    data-state={node.state}
                  >
                    <span className="font-semibold">{node.label}</span>
                    <span className="text-[10px]">{NODE_WORDS[node.state]}</span>
                  </span>
                  {i < nodes.length - 1 ? (
                    <span
                      aria-hidden="true"
                      className={cn("mx-1 h-px flex-1", node.state === "done" ? "bg-ok" : "bg-border-strong")}
                    />
                  ) : null}
                </li>
              ))}
            </ol>

            <p className="num text-xs text-muted-foreground" data-testid="agent-counts">
              {counts.done} done · {counts.working} working · {counts.queued} waiting
              {counts.failed ? ` · ${counts.failed} stopped` : ""}
            </p>

            {run.awaitingApproval ? (
              <a
                href="#/activity"
                className="rounded-lg border border-attention-border bg-attention p-2.5 text-[13px] text-signal-soft hover:no-underline"
              >
                The team needs your approval
              </a>
            ) : null}

            <ul className="flex flex-col gap-2">
              {bars.map(({ agent, left, width }) => (
                <li key={agent.id} className="flex items-center gap-2.5 rounded-lg border border-border bg-card p-2" data-testid="agent-window-row">
                  <Ring agent={agent} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{agent.name}</span>
                      <Pill tone={agent.is_cloud ? "amber" : "ok"}>{agent.is_cloud ? "Cloud" : "Local"}</Pill>
                    </div>
                    <p className="truncate text-xs text-muted-foreground" title={agent.step ? safeStep(agent.step) : undefined}>
                      {stepWords(agent.step, agent.status)}
                      {agent.elapsedMs ? ` · ${seconds(agent.elapsedMs)}` : ""}
                    </p>
                    <span className="relative mt-1 block h-1.5 rounded bg-background" aria-hidden="true">
                      <span
                        className={cn(
                          "absolute top-0 h-full rounded",
                          agent.status === "failed" || agent.status === "cancelled"
                            ? "bg-danger/70"
                            : agent.status === "done"
                              ? "bg-ok/60"
                              : "bg-signal/70",
                        )}
                        style={{ left: `${left}%`, width: `${width}%` }}
                      />
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            {bars.length === 0 && run.status === "done" ? (
              <p className="text-xs text-muted-foreground">No agents on this one: it was answered directly.</p>
            ) : null}
          </>
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">Ask a question: the agents working on it appear here.</p>
        )}
        <a href="#/activity" className="self-start text-xs">
          Open activity (cancel, re-run, briefs)
        </a>
      </div>
    </div>
  );
}
