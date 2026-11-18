/**
 * What the pop-up agent window draws (founder decision G), worked out from the run the workspace already holds: where
 * the run is (plan, team, verify, answer), how many agents are in each state, and one bar per agent on a shared clock.
 * No figure from an agent's work is shown here: the window shows status and steps only, as the Activity tab does.
 */
import { teamOf, type AgentView, type RunView } from "@/lib/workspace";

export type NodeState = "waiting" | "active" | "done" | "failed";

export interface StageNode {
  key: "plan" | "team" | "verify" | "answer";
  label: string;
  state: NodeState;
}

const FINISHED = new Set(["done", "failed", "cancelled"]);

export function isFinished(agent: AgentView): boolean {
  return FINISHED.has(agent.status);
}

export interface Counts {
  done: number;
  working: number;
  queued: number;
  failed: number;
}

export function countAgents(run: RunView | null): Counts {
  const counts: Counts = { done: 0, working: 0, queued: 0, failed: 0 };
  for (const agent of teamOf(run)) {
    if (agent.status === "done") counts.done += 1;
    else if (agent.status === "failed" || agent.status === "cancelled") counts.failed += 1;
    else if (agent.status === "queued") counts.queued += 1;
    else counts.working += 1;
  }
  return counts;
}

/** The four steps of a run, each waiting, working, done or failed. */
export function stageNodes(run: RunView | null): StageNode[] {
  const nodes: StageNode[] = [
    { key: "plan", label: "Plan", state: "waiting" },
    { key: "team", label: "Team", state: "waiting" },
    { key: "verify", label: "Verify", state: "waiting" },
    { key: "answer", label: "Answer", state: "waiting" },
  ];
  if (!run) return nodes;
  const [plan, team, verify, answer] = nodes as [StageNode, StageNode, StageNode, StageNode];
  const agents = teamOf(run);
  const stopped = run.status === "failed" || run.status === "cancelled" || run.status === "rejected";
  const planned = agents.length > 0 || run.proposedTeam.length > 0;
  plan.state = planned ? "done" : stopped ? "failed" : "active";
  if (run.status === "done") {
    plan.state = "done";
    team.state = agents.length > 0 ? "done" : "waiting";
    verify.state = "done";
    answer.state = "done";
    return nodes;
  }
  if (!planned) return nodes;
  const allFinished = agents.length > 0 && agents.every(isFinished);
  const writing = run.answer.length > 0;
  if (stopped) {
    team.state = "failed";
    return nodes;
  }
  if (run.awaitingApproval || !allFinished) {
    team.state = "active";
    return nodes;
  }
  team.state = "done";
  if (writing) {
    verify.state = "done";
    answer.state = "active";
  } else {
    // every agent has finished and no answer text yet: the Verifier is checking the findings
    verify.state = "active";
  }
  return nodes;
}

export interface AgentBar {
  agent: AgentView;
  /** Percent of the run's span from its start to this agent's start. */
  left: number;
  width: number;
}

/** One bar per agent on a shared clock: the Activity tab's timeline, also used by the agent window. */
export function agentBars(run: RunView, now: number): AgentBar[] {
  const agents = teamOf(run);
  if (agents.length === 0) return [];
  const startOf = (a: AgentView) => Date.parse(a.startedAt ?? run.startedAt);
  const endOf = (a: AgentView) => (a.endedAt ? Date.parse(a.endedAt) : a.startedAt ? now : startOf(a));
  const start = Math.min(...agents.map(startOf));
  const span = Math.max(1000, Math.max(...agents.map(endOf)) - start);
  return agents.map((agent) => ({
    agent,
    left: Math.max(0, ((startOf(agent) - start) / span) * 100),
    width: agent.startedAt ? Math.max(1, ((endOf(agent) - startOf(agent)) / span) * 100) : 0,
  }));
}

export interface Position {
  x: number;
  y: number;
}

export function isPosition(v: unknown): v is Position {
  return (
    typeof v === "object" &&
    v !== null &&
    typeof (v as Position).x === "number" &&
    typeof (v as Position).y === "number" &&
    Number.isFinite((v as Position).x) &&
    Number.isFinite((v as Position).y)
  );
}

/** Keeps at least the window's title bar on screen, whatever the stored place or the size of the browser now. */
export function keepOnScreen(pos: Position, size: { w: number; h: number }, viewport: { w: number; h: number }): Position {
  const grip = 48;
  const maxX = Math.max(0, viewport.w - Math.min(size.w, grip * 3));
  const maxY = Math.max(0, viewport.h - grip);
  return {
    x: Math.round(Math.min(maxX, Math.max(Math.min(0, viewport.w - size.w), pos.x))),
    y: Math.round(Math.min(maxY, Math.max(0, pos.y))),
  };
}
