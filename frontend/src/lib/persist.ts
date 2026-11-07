/**
 * The conversation survives a reload (F5): turns, runs and their results are kept in this browser's storage and
 * restored on load. The backend keeps the runs too, so a run still working when the page went away is picked up again.
 *
 * Storage can be missing or full (a private window, blocked site data): then the page simply starts empty.
 */
import type { RunView, Turn, WorkspaceState } from "@/lib/workspace";

export const STORAGE_KEY = "founderos.workspace.v1";
const MAX_RUNS = 20;
const MAX_TURNS = 300;

interface Saved {
  sessionId: string | null;
  quiet: boolean;
  turns: Turn[];
  runs: Record<string, RunView>;
  currentRunId: string | null;
}

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** What is worth keeping: the last runs and the turns that refer to them. */
export function snapshot(state: WorkspaceState): Saved {
  const ids = Object.values(state.runs)
    .sort((a, b) => a.startedAt.localeCompare(b.startedAt))
    .slice(-MAX_RUNS)
    .map((r) => r.id);
  const keep = new Set(ids);
  const runs: Record<string, RunView> = {};
  ids.forEach((id) => {
    const run = state.runs[id];
    if (run) runs[id] = run;
  });
  const turns = state.turns.filter((t) => t.role !== "advisor" || keep.has(t.runId)).slice(-MAX_TURNS);
  return { sessionId: state.sessionId, quiet: state.quiet, turns, runs, currentRunId: state.currentRunId };
}

export function save(state: WorkspaceState): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(STORAGE_KEY, JSON.stringify(snapshot(state)));
  } catch {
    // full or blocked: the next reload starts empty, nothing else breaks
  }
}

export function load(initial: WorkspaceState): WorkspaceState {
  const store = storage();
  if (!store) return initial;
  try {
    const raw = store.getItem(STORAGE_KEY);
    if (!raw) return initial;
    const saved = JSON.parse(raw) as Partial<Saved>;
    if (!saved || typeof saved !== "object" || !Array.isArray(saved.turns) || typeof saved.runs !== "object") {
      return initial;
    }
    return {
      ...initial,
      sessionId: saved.sessionId ?? null,
      quiet: Boolean(saved.quiet),
      turns: saved.turns,
      runs: saved.runs ?? {},
      currentRunId: saved.currentRunId ?? null,
    };
  } catch {
    return initial;
  }
}

export function clearSaved(): void {
  try {
    storage()?.removeItem(STORAGE_KEY);
  } catch {
    // nothing to clear
  }
}

/** Runs that were still working when the page went away: their result is fetched from the backend. */
export function unfinished(state: WorkspaceState): string[] {
  return Object.values(state.runs)
    .filter((r) => r.status === "running")
    .map((r) => r.id);
}
