import { describe, expect, it } from "vitest";

import type { AgentEvent, DecisionFrame } from "@/lib/api";
import { proposedFrame, runsAfter } from "@/lib/proposal";
import { initialState, reducer, type RunView } from "@/lib/workspace";

/** M7a fix round 4 (founder F13b, F17). Fakes only. */

const frame = {
  options: [{ name: "Travel-led pilot" }, { name: "Partner or distributor" }],
  default_option: "Travel-led pilot",
} as unknown as DecisionFrame;

const run = (id: string, startedAt: string, extra: Record<string, unknown> = {}) =>
  ({ id, startedAt, frame: null, result: null, ...extra }) as unknown as RunView;

describe("F13b: the frame card follows the newest memo", () => {
  it("keeps the newest memo's option even after another question, and ignores case", () => {
    const decision = run("r1", "2026-11-26T10:00:00Z", { frame });
    const memoRun = run("r2", "2026-11-26T10:05:00Z", { result: { memo: { chosen: "partner or Distributor" } } });
    const metric = run("r3", "2026-11-26T10:07:00Z", { result: { memo: null } }); // "What's our runway?" since
    const later = runsAfter(decision, [decision, memoRun, metric]);
    expect(later.map((r) => r.id)).toEqual(["r3", "r2"]);
    expect(proposedFrame(frame, later).default_option).toBe("Partner or distributor");
    expect(proposedFrame(frame, [])).toBe(frame);
    expect(runsAfter(null, [decision])).toEqual([]);
  });
});

let seq = 0;
const event = (type: string, data: Record<string, unknown>): AgentEvent => ({
  seq: ++seq,
  type,
  run_id: "s1",
  agent_id: null,
  at: "2026-11-26T10:00:00Z",
  data: { session_id: "s1", ...data },
});

describe("F17: one waiting line per agent, updated in place", () => {
  it("replaces a line with the same key instead of adding it again", () => {
    let state = reducer(initialState, { type: "session", id: "s1" });
    const waiting = { text: "People & Ops is waiting for a cloud model.", line_key: "r1:a1:waiting" };
    for (let i = 0; i < 4; i++) state = reducer(state, { type: "event", event: event("narration", waiting) });
    state = reducer(state, { type: "event", event: event("narration", { text: "Market Scout is done." }) });
    const lines = state.turns.map((t) => (t.role === "lane" ? t.text : ""));
    expect(lines).toEqual(["People & Ops is waiting for a cloud model.", "Market Scout is done."]);
  });
});
