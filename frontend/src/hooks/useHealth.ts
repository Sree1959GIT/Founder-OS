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
