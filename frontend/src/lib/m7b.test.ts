import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { AgentEvent } from "@/lib/api";
import { EVENT_TYPES, initialState, reducer, type WorkspaceState } from "@/lib/workspace";

/** M7b: founder F8d (the slow offer reaches the page) and F19 (a switch to Qwen is shown). Fakes only. */

let seq = 0;
const ev = (type: string, data: Record<string, unknown>, agent: string | null = null, run = "r1"): AgentEvent => ({
  seq: ++seq,
  type,
  run_id: run,
  agent_id: agent,
  at: "2026-11-26T10:00:00Z",
  data,
});

function started(): WorkspaceState {
  let s: WorkspaceState = reducer({ ...initialState, sessionId: "s1" }, { type: "run", runId: "r1", message: "Dubai?" });
  s = reducer(s, {
    type: "event",
    event: ev("agent.spawned", { id: "a1", type: "people_ops", name: "People & Ops", brief: "b", is_cloud: true, provider: "groq" }, "a1"),
  });
  return s;
}

describe("F8d: every event the backend sends is listened for", () => {
  it("lists each of the backend's event types (a missing one is dropped by the browser)", () => {
    const source = readFileSync(resolve(__dirname, "../../../backend/app/agents/events.py"), "utf-8");
    const block = source.slice(source.indexOf("EventType = Literal["), source.indexOf("]", source.indexOf("EventType = Literal[")));
    const backend = [...block.matchAll(/"([a-z_.]+)"/g)].map((m) => m[1]);
    expect(backend).toContain("slow.offered");
    for (const type of backend) expect(EVENT_TYPES, type).toContain(type);
  });

  it("shows the offer in the Advisor panel and on the agent's card", () => {
    let s = started();
    s = reducer(s, { type: "event", event: ev("agent.slow", { reason: "Groq has not answered in 5 s" }, "a1") });
    s = reducer(s, {
      type: "event",
      event: ev("slow.offered", { session_id: "s1", run: "r1", agent: "a1", text: "People & Ops is taking longer…", reason: "Groq…" }, null, "s1"),
    });
    expect(s.runs.r1?.agents.a1?.slowReason).toBe("Groq has not answered in 5 s");
    expect(s.turns.filter((t) => t.role === "slow")).toHaveLength(1);
  });
});

describe("F19: a switch to Qwen is shown on the card", () => {
  it("keeps the sentence and clears the slow offer", () => {
    let s = started();
    s = reducer(s, { type: "event", event: ev("agent.slow", { reason: "slow" }, "a1") });
    const text = "Groq hit its per-minute limit, so People & Ops finished on Qwen on our server.";
    s = reducer(s, { type: "event", event: ev("agent.fallback", { text, provider: "Groq", reason: "rate_limit" }, "a1") });
    expect(s.runs.r1?.agents.a1?.fallback).toBe(text);
    expect(s.runs.r1?.agents.a1?.slowReason).toBe("");
  });
});
