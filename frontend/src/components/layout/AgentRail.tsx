export function AgentRail() {
  return (
    <aside
      aria-label="Agent activity"
      className="hidden w-[240px] shrink-0 flex-col gap-3 border-l border-border bg-panel px-4 py-4 xl:flex"
    >
      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Agents</span>
      <p className="text-xs leading-relaxed text-muted-foreground">
        Live agent cards appear here once the agent swarm lands in M3a.
      </p>
    </aside>
  );
}
