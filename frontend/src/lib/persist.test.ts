import { beforeEach, describe, expect, it } from "vitest";

import { load, save, STORAGE_KEY, unfinished } from "@/lib/persist";
import { initialState, reducer } from "@/lib/workspace";

describe("a reload keeps the conversation", () => {
  beforeEach(() => window.localStorage.clear());

  it("restores turns, runs, the session and the open decision after F5", () => {
    let state = reducer(initialState, { type: "session", id: "ses_1" });
    state = reducer(state, { type: "turn", turn: { id: "you-1", role: "you", text: "Should we open a Dubai office?" } });
    state = reducer(state, { type: "run", runId: "r1", message: "Should we open a Dubai office?" });
    state = reducer(state, { type: "turn", turn: { id: "advisor-r1", role: "advisor", runId: "r1" } });
    state = reducer(state, { type: "delta", runId: "r1", text: "Start with a travel-led pilot." });
    save(state);
    const restored = load(initialState);
    expect(restored.sessionId).toBe("ses_1");
    expect(restored.turns.map((t) => t.id)).toEqual(["you-1", "advisor-r1"]);
    expect(restored.runs.r1?.answer).toBe("Start with a travel-led pilot.");
    expect(restored.currentRunId).toBe("r1");
    expect(restored.sending).toBe(false);
    expect(unfinished(restored)).toEqual(["r1"]);
  });

  it("starts empty when storage holds nothing usable", () => {
    window.localStorage.setItem(STORAGE_KEY, "{not json");
    expect(load(initialState)).toBe(initialState);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ turns: "x" }));
    expect(load(initialState)).toBe(initialState);
  });
});
