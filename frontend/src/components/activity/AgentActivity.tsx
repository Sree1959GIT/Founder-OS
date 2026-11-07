import { ArrowLeft, Plus, RotateCcw, Square, TriangleAlert, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ErrorNote, EmptyNote, Pill, VerifiedBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { approveRun, cancelAgent, cancelRun, rerunAgent, type AgentInstance, type TeamEdit } from "@/lib/api";
import { agentCode, agentKind, seconds, stepWords, STATUS_PROGRESS, STATUS_WORDS } from "@/lib/format";
import { slotsInUse, useCatalog, type AgentCatalog } from "@/hooks/useCatalog";
import { teamOf, useWorkspace, type AgentView, type RunView } from "@/lib/workspace";
import { cn } from "@/lib/utils";

function WhereBadge({ isCloud, provider }: { isCloud: boolean; provider: string }) {
  return <Pill tone={isCloud ? "amber" : "ok"}>{isCloud ? `Cloud · ${provider}` : "Local"}</Pill>;
}

function statusTone(status: string): string {
  if (status === "done") return "text-ok";
  if (status === "failed") return "text-danger";
  if (status === "cancelled" || status === "queued") return "text-muted-foreground";
  return "text-signal-soft";
}

/** The team the Planner proposes: nothing runs until the founder has seen it. */
function Proposal({ run, catalog }: { run: RunView; catalog: AgentCatalog | null }) {
  const [briefs, setBriefs] = useState<Record<string, string>>({});
  const [removed, setRemoved] = useState<string[]>([]);
  const [added, setAdded] = useState<{ type: string; brief: string }[]>([]);
  const [adding, setAdding] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const team = run.proposedTeam.filter((a) => !removed.includes(a.id));
  const anyCloud =
    team.some((a) => a.is_cloud) || added.some((a) => catalog?.agents.find((c) => c.type === a.type)?.is_cloud);
  const onTeam = new Set(team.map((a) => a.type));
  const available = (catalog?.agents ?? []).filter((a) => a.spawnable && !onTeam.has(a.type));

  const answer = async (approved: boolean, localOnly = false) => {
    setBusy(true);
    setError(null);
    const changedBriefs = Object.fromEntries(
      Object.entries(briefs).filter(([id, text]) => text !== run.proposedTeam.find((a) => a.id === id)?.brief),
    );
    const edit: TeamEdit = {
      ...(Object.keys(changedBriefs).length ? { briefs: changedBriefs } : {}),
      ...(removed.length ? { remove: removed } : {}),
      ...(added.length ? { add: added.filter((a) => a.brief.trim()) } : {}),
      ...(localOnly ? { local_only: true } : {}),
    };
    try {
      await approveRun(run.id, approved, approved && Object.keys(edit).length ? edit : undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The approval did not go through");
      setBusy(false);
    }
  };

  return (
    <section className="rounded-2xl border border-[#4A3A1C] bg-[#1A1610] p-4" aria-label="Team approval" data-testid="team-approval">
      <div className="mb-3 flex items-start gap-2">
        <TriangleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-signal" />
        <div>
          <h2 className="text-[15px] font-semibold">Approval needed: the proposed team</h2>
          <p className="text-[13px] text-muted-foreground">
            {anyCloud
              ? "Approval needed: cloud agents only see summarised metrics, never raw rows."
              : "Everyone on this team runs on this PC."}{" "}
            Edit a brief, take an agent off, or add one.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {team.map((agent: AgentInstance) => (
          <article key={agent.id} className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
            <div className="flex items-center gap-2">
              <span className="num flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-background text-xs font-semibold">
                {agentCode(agent.type)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{agent.name}</p>
                <WhereBadge isCloud={agent.is_cloud} provider={agent.provider} />
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Take ${agent.name} off the team`}
                onClick={() => setRemoved([...removed, agent.id])}
              >
                <X aria-hidden="true" />
              </Button>
            </div>
            <label className="text-xs text-muted-foreground" htmlFor={`brief-${agent.id}`}>
              Brief
            </label>
            <textarea
              id={`brief-${agent.id}`}
              rows={3}
              value={briefs[agent.id] ?? agent.brief}
              onChange={(e) => setBriefs({ ...briefs, [agent.id]: e.target.value })}
              className="rounded-lg border border-border-strong bg-background p-2 text-[13px] text-foreground"
            />
          </article>
        ))}
        {added.map((agent, i) => (
          <article key={`${agent.type}-${i}`} className="flex flex-col gap-2 rounded-xl border border-dashed border-border-strong bg-card p-3">
            <div className="flex items-center gap-2">
              <span className="num flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-background text-xs font-semibold">
                {agentCode(agent.type)}
              </span>
              <p className="min-w-0 flex-1 truncate font-semibold">
                {catalog?.agents.find((c) => c.type === agent.type)?.title ?? agent.type}
              </p>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Remove this added agent"
                onClick={() => setAdded(added.filter((_, n) => n !== i))}
              >
                <X aria-hidden="true" />
              </Button>
            </div>
            <label className="text-xs text-muted-foreground" htmlFor={`added-${i}`}>
              Brief
            </label>
            <textarea
              id={`added-${i}`}
              rows={3}
              value={agent.brief}
              onChange={(e) => setAdded(added.map((a, n) => (n === i ? { ...a, brief: e.target.value } : a)))}
              className="rounded-lg border border-border-strong bg-background p-2 text-[13px] text-foreground"
            />
          </article>
        ))}
      </div>
      {error ? (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void answer(true)}
          className="h-11 rounded-lg bg-signal px-5 text-sm font-semibold text-[#1A1206] hover:bg-signal/90 disabled:opacity-50"
        >
          Approve and run
        </button>
        {available.length ? (
          <span className="flex items-center gap-1.5">
            <label htmlFor="add-agent" className="sr-only">
              Agent to add
            </label>
            <select
              id="add-agent"
              value={adding}
              onChange={(e) => setAdding(e.target.value)}
              className="h-11 rounded-lg border border-border-strong bg-card px-2 text-sm"
            >
              <option value="">Choose an agent</option>
              {available.map((a) => (
                <option key={a.type} value={a.type}>
                  {a.title}
                </option>
              ))}
            </select>
            <Button
              variant="outline"
              className="h-11"
              disabled={!adding}
              onClick={() => {
                setAdded([...added, { type: adding, brief: run.message }]);
                setAdding("");
              }}
            >
              <Plus aria-hidden="true" />
              Add agent
            </Button>
          </span>
        ) : null}
        {anyCloud ? (
          <Button variant="outline" className="h-11" disabled={busy} onClick={() => void answer(true, true)}>
            Run all locally instead
          </Button>
        ) : null}
        <Button variant="ghost" className="h-11" disabled={busy} onClick={() => void answer(false)}>
          Hold the team back
        </Button>
      </div>
    </section>
  );
}

function AgentCard({ run, agent }: { run: RunView; agent: AgentView }) {
  const { follow } = useWorkspace();
  const [editing, setEditing] = useState(false);
  const [brief, setBrief] = useState(agent.brief);
  const [error, setError] = useState<string | null>(null);
  const finished = ["done", "failed", "cancelled"].includes(agent.status);
  const progress = STATUS_PROGRESS[agent.status] ?? 35;

  const cancel = async () => {
    try {
      await cancelAgent(run.id, agent.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel");
    }
  };
  const rerun = async () => {
    setError(null);
    try {
      const outcome = await rerunAgent(run.id, agent.id, brief);
      setEditing(false);
      if (outcome.run_id !== run.id) follow(outcome.run_id, run.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not re-run");
    }
  };

  return (
    <article className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3.5" aria-label={agent.name} data-testid="agent-card">
      <div className="flex items-center gap-2.5">
        <span className="num flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg bg-background text-xs font-semibold">
          {agentCode(agent.type)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{agent.name}</p>
          <p className="truncate text-xs text-muted-foreground">{agentKind(agent.type)}</p>
        </div>
        <WhereBadge isCloud={agent.is_cloud} provider={agent.provider} />
      </div>
      <p className="text-[13px] leading-snug text-muted-foreground">
        <span className="text-foreground">Brief: </span>
        {agent.brief}
      </p>
      <p className="num min-h-[34px] rounded-lg bg-background px-2 py-1.5 text-[11.5px] leading-snug text-foreground">
        {stepWords(agent.step, agent.status)}
      </p>
      <div
        role="progressbar"
        aria-label={`${agent.name} step`}
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-1 overflow-hidden rounded-full bg-background"
      >
        <div
          className={cn("h-full rounded-full", agent.status === "failed" ? "bg-danger" : agent.status === "done" ? "bg-ok" : "bg-signal")}
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={cn("font-medium", statusTone(agent.status))}>{STATUS_WORDS[agent.status] ?? agent.status}</span>
        <VerifiedBadge verified={agent.verified} />
        <span className="flex-1" />
        <span className="num text-muted-foreground">
          {seconds(agent.elapsedMs)}
          {agent.tokens ? ` · ${agent.tokens.toLocaleString("en-US")} tok` : ""}
        </span>
      </div>
      {editing ? (
        <div className="flex flex-col gap-2">
          <label htmlFor={`rerun-${agent.id}`} className="text-xs text-muted-foreground">
            New brief
          </label>
          <textarea
            id={`rerun-${agent.id}`}
            rows={3}
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            className="rounded-lg border border-border-strong bg-background p-2 text-[13px]"
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={() => void rerun()}>
              Run again
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Keep as it is
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          {finished ? null : (
            <Button size="sm" variant="outline" onClick={() => void cancel()} aria-label={`Cancel ${agent.name}`}>
              <Square aria-hidden="true" />
              Cancel
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setEditing(true)} aria-label={`Re-run ${agent.name}`}>
            <RotateCcw aria-hidden="true" />
            Re-run
          </Button>
        </div>
      )}
      {error ? <ErrorNote>{error}</ErrorNote> : null}
    </article>
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

function Timeline({ run }: { run: RunView }) {
  const now = useNow(run.status === "running");
  const bars = useMemo(() => {
    const agents = teamOf(run);
    const start = Math.min(...agents.map((a) => Date.parse(a.startedAt ?? run.startedAt)));
    const ends = agents.map((a) => (a.endedAt ? Date.parse(a.endedAt) : now));
    const span = Math.max(1000, Math.max(...ends) - start);
    return agents.map((a) => ({
      agent: a,
      left: ((Date.parse(a.startedAt ?? run.startedAt) - start) / span) * 100,
      width: Math.max(1, (((a.endedAt ? Date.parse(a.endedAt) : now) - Date.parse(a.startedAt ?? run.startedAt)) / span) * 100),
    }));
  }, [run, now]);
  return (
    <ul className="flex flex-col gap-2" aria-label="Timeline">
      {bars.map(({ agent, left, width }) => (
        <li key={agent.id} className="grid grid-cols-[minmax(110px,200px)_1fr] items-center gap-3">
          <span className="truncate text-[13px]">{agent.name}</span>
          <span className="relative block h-5 rounded bg-background">
            <span
              className={cn(
                "absolute top-0 h-full rounded",
                agent.status === "failed" ? "bg-danger/70" : agent.status === "done" ? "bg-ok/60" : "bg-signal/70",
              )}
              style={{ left: `${left}%`, width: `${width}%` }}
              title={STATUS_WORDS[agent.status] ?? agent.status}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function AgentActivity() {
  const { currentRun: run } = useWorkspace();
  const catalog = useCatalog();
  const [mode, setMode] = useState<"cards" | "timeline">("cards");
  const slots = slotsInUse(run);
  const agents = teamOf(run);
  const cost = run?.result?.est_cost_usd ?? null;
  const done = agents.filter((a) => a.status === "done").length;

  return (
    <main className="flex min-w-0 flex-1 flex-col gap-4 px-6 py-5">
      <div className="flex flex-wrap items-center gap-3">
        <a href="#/" className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground">
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          Back to workspace
        </a>
        <h1 className="min-w-0 truncate text-[18px] font-semibold">
          Agent Activity{run ? <span className="font-normal text-muted-foreground"> · {run.message}</span> : null}
        </h1>
        <span className="flex-1" />
        <Pill>
          Local slots <span className="num">{slots.local}/{catalog?.max_local_agents ?? 2}</span>
        </Pill>
        <Pill>
          Cloud slots <span className="num">{slots.cloud}/{catalog?.max_cloud_agents ?? 6}</span>
        </Pill>
        <Pill title="An estimate from the provider's published prices">
          Run cost <span className="num">{cost === null ? "n/a" : `≈ $${cost.toFixed(2)}`}</span>
        </Pill>
      </div>

      {!run ? <EmptyNote>Ask the advisor something. The team that works on it appears here.</EmptyNote> : null}
      {run?.awaitingApproval ? <Proposal key={run.id} run={run} catalog={catalog} /> : null}

      {run && agents.length ? (
        <section aria-label="Running now" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-[15px] font-semibold">{run.status === "running" ? "Running now" : "This run"}</h2>
            <span className="num text-xs text-muted-foreground">
              {run.status === "running" ? `${done} of ${agents.length} done` : `Finished · ${done} of ${agents.length}`}
            </span>
            <span className="flex-1" />
            {run.status === "running" ? (
              <Button size="sm" variant="outline" onClick={() => void cancelRun(run.id).catch(() => undefined)}>
                <Square aria-hidden="true" />
                Stop the run
              </Button>
            ) : null}
            <div role="group" aria-label="View" className="flex rounded-lg border border-border-strong">
              {(["cards", "timeline"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={mode === m}
                  onClick={() => setMode(m)}
                  className={cn("h-9 px-3 text-xs capitalize", mode === m ? "bg-accent text-foreground" : "text-muted-foreground")}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
          {mode === "cards" ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {agents.map((agent) => (
                <AgentCard key={agent.id} run={run} agent={agent} />
              ))}
            </div>
          ) : (
            <Timeline run={run} />
          )}
        </section>
      ) : null}
    </main>
  );
}
