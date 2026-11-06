import { useEffect, useState } from "react";

import { teamOf, type RunView } from "@/lib/workspace";

export interface AgentCatalog {
  agents: { type: string; title: string; spawnable: boolean; job?: string }[];
  max_local_agents: number;
  max_cloud_agents: number;
}

const ACTIVE = new Set(["thinking", "querying_data", "searching_vault", "searching_web", "waiting_cloud", "verifying"]);

export function useCatalog(): AgentCatalog | null {
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  useEffect(() => {
    let alive = true;
    fetch("/api/agents")
      .then((r) => (r.ok ? (r.json() as Promise<AgentCatalog>) : null))
      .then((c) => {
        if (alive && c && Array.isArray(c.agents)) setCatalog(c);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return catalog;
}

export function slotsInUse(run: RunView | null): { local: number; cloud: number } {
  const counts = { local: 0, cloud: 0 };
  for (const agent of teamOf(run)) {
    if (ACTIVE.has(agent.status)) counts[agent.is_cloud ? "cloud" : "local"] += 1;
  }
  return counts;
}
