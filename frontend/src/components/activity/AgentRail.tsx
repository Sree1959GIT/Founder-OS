import { Pill } from "@/components/common";
import { slotsInUse, useCatalog } from "@/hooks/useCatalog";
import { safeStep, seconds, STATUS_WORDS } from "@/lib/format";
import { teamOf, useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/utils";

const dot = (status: string) =>
  status === "done"
    ? "bg-ok"
    : status === "failed"
      ? "bg-danger"
      : status === "queued" || status === "cancelled"
        ? "bg-muted-foreground"
        : "bg-signal";

export function AgentRail() {
  const { currentRun: run } = useWorkspace();
  const catalog = useCatalog();
  const slots = slotsInUse(run);
  const agents = teamOf(run);
  return (
    <aside
      aria-label="Agents"
      className="hidden w-[300px] shrink-0 flex-col gap-3 border-l border-border bg-panel px-4 py-4 xl:sticky xl:top-0 xl:flex xl:h-[calc(100vh-61px)] xl:overflow-y-auto"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Agents</span>
        <a href="#/activity" className="text-xs">
          Open activity
        </a>
      </div>
      <p className="num text-xs text-muted-foreground">
        {slots.local}/{catalog?.max_local_agents ?? 2} local · {slots.cloud}/{catalog?.max_cloud_agents ?? 6} cloud
      </p>
      {run?.awaitingApproval ? (
        <a
          href="#/activity"
          className="rounded-lg border border-[#4A3A1C] bg-[#1A1610] p-2.5 text-[13px] text-signal-soft hover:no-underline"
        >
          The team needs your approval
        </a>
      ) : null}
      {agents.length === 0 && !run?.awaitingApproval ? (
        <p className="text-xs leading-relaxed text-muted-foreground">Agents working on your question appear here.</p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {agents.map((agent) => (
          <li key={agent.id} className="rounded-lg border border-border bg-card p-2.5">
            <div className="flex items-center gap-2">
              <span aria-hidden="true" className={cn("h-2 w-2 shrink-0 rounded-full", dot(agent.status))} />
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{agent.name}</span>
              <Pill tone={agent.is_cloud ? "amber" : "ok"}>{agent.is_cloud ? "Cloud" : "Local"}</Pill>
            </div>
            <p className="mt-1 truncate text-xs text-muted-foreground" title={agent.step ? safeStep(agent.step) : undefined}>
              {agent.step ? safeStep(agent.step) : "waiting to start"}
            </p>
            <p className="num mt-0.5 text-[11px] text-muted-foreground">
              {STATUS_WORDS[agent.status] ?? agent.status}
              {agent.elapsedMs ? ` · ${seconds(agent.elapsedMs)}` : ""}
            </p>
          </li>
        ))}
      </ul>
    </aside>
  );
}
