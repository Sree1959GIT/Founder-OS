import { useEffect, useState } from "react";

import { fetchHealth, type HealthResponse } from "@/lib/api";

export type HealthState =
  | { kind: "loading" }
  | { kind: "ready"; data: HealthResponse }
  | { kind: "offline"; message: string };

export const HEALTH_POLL_MS = 15_000;

/** Polls `/api/health`. Never throws: an unreachable backend becomes the `offline` state. */
export function useHealth(pollMs: number = HEALTH_POLL_MS): HealthState {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    let controller = new AbortController();
    let cancelled = false;

    const load = async () => {
      controller.abort();
      controller = new AbortController();
      try {
        const data = await fetchHealth(controller.signal);
        if (!cancelled) setState({ kind: "ready", data });
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setState({ kind: "offline", message: err instanceof Error ? err.message : "Backend not reachable" });
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      controller.abort();
    };
  }, [pollMs]);

  return state;
}

export type SystemWord = "ok" | "slow" | "offline" | "checking";

/**
 * Founder F21: members see one plain status. A required service that is not answering, or anything degraded, is
 * "Slow right now"; an optional service that is off (cloud, GPU) or not reachable (search index) is not a problem.
 */
export function systemWord(health: HealthState): SystemWord {
  if (health.kind === "loading") return "checking";
  if (health.kind === "offline") return "offline";
  const deps = health.data.dependencies;
  const bad = deps.some((d) => d.state === "degraded" || (d.required && d.state !== "ok"));
  return bad ? "slow" : "ok";
}

