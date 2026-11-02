import type { DependencyState, DependencyStatus } from "@/lib/api";
import type { HealthState } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = { ollama: "Ollama", qdrant: "Qdrant", cloud: "Cloud", gpu: "GPU", storage: "Storage" };

// Status is never shown by colour alone: every dot has a text label and a state word.
const STATE_TEXT: Record<DependencyState, string> = {
  ok: "ok",
  degraded: "degraded",
  unavailable: "down",
  not_configured: "off",
};

const DOT: Record<DependencyState, string> = {
  ok: "bg-ok",
  degraded: "bg-signal",
  unavailable: "bg-danger",
  not_configured: "bg-muted-foreground/60",
};

function dependencyLabel(dep: DependencyStatus): string {
  const base = LABELS[dep.name] ?? dep.name;
  if (dep.name === "gpu" && dep.state === "ok") {
    const used = dep.info["vram_used_gb"];
    const total = dep.info["vram_total_gb"];
    if (typeof used === "number" && typeof total === "number") return `${base} ${used}/${total} GB`;
  }
  return base;
}

export function HealthBadge({ health }: { health: HealthState }) {
  if (health.kind === "loading") {
    return (
      <div role="status" className="text-xs text-muted-foreground">
        Checking services...
      </div>
    );
  }
  if (health.kind === "offline") {
    return (
      <div role="status" className="flex items-center gap-2 text-xs text-danger" title={health.message}>
        <span aria-hidden="true" className="h-2 w-2 rounded-full bg-danger" />
        Backend offline
      </div>
    );
  }
  return (
    <ul role="status" aria-label="Service health" className="flex flex-wrap items-center gap-3 text-xs">
      {health.data.dependencies.map((dep) => (
        <li
          key={dep.name}
          className="flex items-center gap-1.5 text-muted-foreground"
          title={dep.detail}
          data-state={dep.state}
        >
          <span aria-hidden="true" className={cn("h-2 w-2 rounded-full", DOT[dep.state])} />
          <span className={cn(dep.name === "gpu" && dep.state === "ok" && "num")}>{dependencyLabel(dep)}</span>
          <span className="sr-only">: {STATE_TEXT[dep.state]}.</span>
          {dep.state !== "ok" && <span aria-hidden="true">({STATE_TEXT[dep.state]})</span>}
        </li>
      ))}
    </ul>
  );
}
