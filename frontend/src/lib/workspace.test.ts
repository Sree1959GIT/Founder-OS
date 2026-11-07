import { describe, expect, it } from "vitest";

import type { AgentEvent, ChatResult } from "@/lib/api";
import { initialState, reducer, teamOf, type WorkspaceState } from "@/lib/workspace";

let seq = 0;
const event = (type: string, data: Record<string, unknown> = {}, run_id = "r1", agent_id: string | null = null): AgentEvent => ({
  seq: ++seq,
  type,
  run_id,
  agent_id,
  at: "2026-11-06T12:00:00Z",
  data,
});

const agent = { id: "a1", type: "financial_analyst", name: "Financial Analyst", brief: "b", provider: "ollama", model: "m", is_cloud: false };

function play(start: WorkspaceState, ...events: AgentEvent[]): WorkspaceState {
  return events.reduce((state, e) => reducer(state, { type: "event", event: e }), start);
}

describe("workspace state", () => {
  it("keeps events that arrive before the POST has returned the run id", () => {
    const early = play(initialState, event("team.proposed", { needs_approval: true, team: [agent], intent: "decision" }));
    expect(early.runs).toEqual({});
    const state = reducer(early, { type: "run", runId: "r1", message: "Dubai?" });
    expect(state.runs.r1?.awaitingApproval).toBe(true);
    expect(state.held).toEqual([]);
  });

  it("ignores an event it has already seen when a reconnect replays history", () => {
    const start = reducer(initialState, { type: "run", runId: "r1", message: "m" });
    const spawned = event("agent.spawned", agent as unknown as Record<string, unknown>, "r1", "a1");
    const step = event("agent.step", { step: "first" }, "r1", "a1");
    const later = event("agent.step", { step: "second" }, "r1", "a1");
    const state = play(start, spawned, step, later, step);
    expect(state.runs.r1?.agents.a1?.step).toBe("second");
    expect(teamOf(state.runs.r1 ?? null)).toHaveLength(1);
  });

  it("shows lane events of this conversation only, including those from before the session id was known", () => {
    let state = play(
      initialState,
      event("narration", { session_id: "s1", text: "Mine" }, "s1"),
      event("narration", { session_id: "other", text: "Another window" }, "other"),
    );
    expect(state.turns).toEqual([]);
    state = reducer(state, { type: "session", id: "s1" });
    expect(state.turns.map((t) => (t.role === "lane" ? t.text : ""))).toEqual(["Mine"]);
  });

  it("turns a queued question into an offer, and an offer into its answer", () => {
    let state = reducer(initialState, { type: "session", id: "s1" });
    state = play(state, event("queue.added", { session_id: "s1", queue_id: "q1", text: "And hiring?" }, "s1"));
    state = play(state, event("queue.offered", { session_id: "s1", queue_id: "q1", text: "And hiring?" }, "s1"));
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]).toMatchObject({ role: "queued", status: "offered" });
    state = reducer(state, { type: "queue", id: "q1", status: "declined" });
    expect(state.turns[0]).toMatchObject({ status: "declined" });
  });

  it("moves the answer below the narration when its first words arrive, and takes verified only from the backend", () => {
    let state = reducer(initialState, { type: "run", runId: "r1", message: "m" });
    state = reducer(state, { type: "turn", turn: { id: "advisor-r1", role: "advisor", runId: "r1" } });
    state = reducer(state, { type: "turn", turn: { id: "n", role: "lane", text: "Working", kind: "narration" } });
    state = reducer(state, { type: "delta", runId: "r1", text: "Hello" });
    expect(state.turns.map((t) => t.id)).toEqual(["n", "advisor-r1"]);
    expect(state.runs.r1?.verified).toBeNull();
    const result = { answer: "Final", status: "done", verified: false, artifacts: [], message: "m", intent: "metric" } as unknown as ChatResult;
    state = reducer(state, { type: "result", runId: "r1", result });
    expect(state.runs.r1?.answer).toBe("Final");
    expect(state.runs.r1?.verified).toBe(false);
  });
});
