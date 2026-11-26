import type { DecisionFrame } from "@/lib/api";
import type { RunView } from "@/lib/workspace";

/** Founder F13: one proposal on screen. A later answer (with no frame of its own) whose memo proposes another of
 * this frame's options moves the "Proposed" mark there, so the card and the answer never disagree. */
export function proposedFrame(frame: DecisionFrame, later: RunView | null): DecisionFrame {
  const chosen = later?.frame ? "" : later?.result?.memo?.chosen ?? "";
  if (!chosen || chosen === frame.default_option || !frame.options.some((o) => o.name === chosen)) return frame;
  return { ...frame, default_option: chosen };
}
