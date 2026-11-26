import type { DecisionFrame } from "@/lib/api";
import type { RunView } from "@/lib/workspace";

const plain = (name: string) => name.trim().toLowerCase().split(/\s+/).join(" ");

/** Founder F13: one proposal on screen. A later answer (with no frame of its own) whose memo proposes another of
 * this frame's options moves the "Proposed" mark there, so the card and the answer never disagree.
 *
 * Founder F13b: `later` may be every run after the frame's own, newest first. The newest memo for one of this frame's
 * options wins, even when another question (a metric, "what did we decide?") was asked since; names match ignoring
 * case and spacing. */
export function proposedFrame(frame: DecisionFrame, later: RunView | RunView[] | null): DecisionFrame {
  const runs = Array.isArray(later) ? later : later ? [later] : [];
  for (const run of runs) {
    const chosen = run.frame ? "" : run.result?.memo?.chosen ?? "";
    const option = chosen ? frame.options.find((o) => plain(o.name) === plain(chosen)) : undefined;
    if (option) return option.name === frame.default_option ? frame : { ...frame, default_option: option.name };
  }
  return frame;
}

/** The runs started after `run`, newest first (for `proposedFrame`). */
export function runsAfter(run: RunView | null, runs: RunView[]): RunView[] {
  if (!run) return [];
  return runs
    .filter((r) => r.id !== run.id && r.startedAt.localeCompare(run.startedAt) >= 0)
    .sort((a, b) => b.startedAt.localeCompare(a.startedAt));
}
