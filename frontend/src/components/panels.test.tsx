/** Founder decisions F (panels) and G (agent window), M6. */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { agentBars, countAgents, keepOnScreen, stageNodes } from "@/lib/agentGraph";
import {
  DEFAULT_LAYOUT,
  LAYOUT_KEY,
  LEFT,
  loadLayout,
  maxWidth,
  parseLayout,
  resize,
  RIGHT,
  saveLayout,
  shownWidths,
} from "@/lib/layout";
import type { AgentView, RunView } from "@/lib/workspace";

const holder: { run: RunView | null } = { run: null };

vi.mock("@/lib/workspace", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/workspace")>();
  return {
    ...actual,
    useWorkspace: () => ({
      currentRun: holder.run,
      state: { turns: [], runs: {}, currentRunId: null, quiet: false, error: null, sessionId: null },
      send: vi.fn(),
      toggleQuiet: vi.fn(),
      amendment: vi.fn(),
      queued: vi.fn(),
    }),
  };
});
// The voice client needs a microphone and a socket; here it only has to stay mounted.

const { AgentWindow, WINDOW_KEY } = await import("@/components/activity/AgentWindow");
const { AdvisorPanel } = await import("@/components/chat/AdvisorPanel");
const { ResizeHandle } = await import("@/components/layout/ResizeHandle");

const agent = (id: string, over: Partial<AgentView>): AgentView => ({
  id,
  type: "financial_analyst",
  name: id,
  brief: "b",
  provider: "ollama",
  model: "qwen3:8b",
  is_cloud: false,
  status: "queued",
  step: "",
  startedAt: null,
  endedAt: null,
  elapsedMs: null,
  verified: null,
  tokens: null,
  costUsd: null,
  provided: "",
  artifactIds: [],
  checks: 0,
  ...over,
});

const makeRun = (over: Partial<RunView>): RunView => ({
  id: "r",
  message: "Should we open a Dubai office?",
  startedAt: "2026-11-18T10:00:00Z",
  status: "running",
  intent: null,
  decisionType: null,
  reversibility: null,
  needsApproval: false,
  awaitingApproval: false,
  proposedTeam: [],
  questions: [],
  frame: null,
  agents: {},
  order: [],
  artifacts: [],
  answer: "",
  result: null,
  verified: null,
  lastSeq: 0,
  progress: "",
  ...over,
});

const teamRun = (statuses: string[], over: Partial<RunView> = {}): RunView => {
  const agents: Record<string, AgentView> = {};
  statuses.forEach((status, i) => {
    const id = `a${i}`;
    agents[id] = agent(id, {
      status,
      startedAt: status === "queued" ? null : `2026-11-18T10:00:0${i}Z`,
      endedAt: status === "done" ? `2026-11-18T10:00:1${i}Z` : null,
    });
  });
  return makeRun({ agents, order: Object.keys(agents), ...over });
};

beforeEach(() => {
  window.localStorage.clear();
  holder.run = null;
});

describe("F: panel sizes", () => {
  it("keeps each panel inside its limits and leaves the canvas room", () => {
    expect(resize(DEFAULT_LAYOUT, "left", 5000, 0).left).toBe(LEFT.max);
    expect(resize(DEFAULT_LAYOUT, "left", 10, 0).left).toBe(LEFT.min);
    expect(resize(DEFAULT_LAYOUT, "right", 10, 0).right).toBe(RIGHT.min);
    // Founder F26: 1280 wide: the left may grow to 1280 - 320 (right) - 560 (centre) = 400
    expect(maxWidth("left", DEFAULT_LAYOUT, 1280)).toBe(400);
    expect(resize(DEFAULT_LAYOUT, "left", 700, 1280).left).toBe(400);
    // with the right folded the left may take more
    expect(maxWidth("left", { ...DEFAULT_LAYOUT, rightCollapsed: true }, 1280)).toBe(1280 - 44 - 560);
    // with the left folded the right may take more
    expect(maxWidth("right", { ...DEFAULT_LAYOUT, leftCollapsed: true }, 1100)).toBe(1100 - 44 - 560);
    expect(maxWidth("right", { ...DEFAULT_LAYOUT, leftCollapsed: true }, 1600)).toBe(RIGHT.max);
  });

  it("a width saved on a big screen is drawn narrower on a small one, and kept", () => {
    const wide = { left: 720, right: 560, leftCollapsed: false, rightCollapsed: false };
    // 900: the Options panel is not beside the centre (below lg), so the Advisor may take 900 - 560 = 340
    expect(shownWidths(wide, 900)).toEqual({ left: 340, right: 560 });
    // 1024: both panels at their minimum; the centre (still narrower than the table) shows the phone-style stage
    expect(shownWidths(wide, 1024)).toEqual({ left: 280, right: 240 });
    // 1440 with both panels: the centre keeps 560
    const shown = shownWidths(wide, 1440);
    expect(shown.left + shown.right + 560).toBeLessThanOrEqual(1440);
    expect(shownWidths(wide, 2560)).toEqual({ left: 720, right: 560 });
  });

  it("dragging the left panel wider unfolds it", () => {
    expect(resize({ ...DEFAULT_LAYOUT, leftCollapsed: true }, "left", 400, 0).leftCollapsed).toBe(false);
  });

  it("remembers sizes per viewer, and ignores a broken stored value", () => {
    saveLayout({ left: 500, right: 260, leftCollapsed: true, rightCollapsed: true });
    expect(loadLayout()).toEqual({ left: 500, right: 260, leftCollapsed: true, rightCollapsed: true });
    window.localStorage.setItem(LAYOUT_KEY, "{not json");
    expect(loadLayout()).toEqual(DEFAULT_LAYOUT);
    expect(parseLayout(JSON.stringify({ left: 99999, right: "wide" }))).toEqual({ left: LEFT.max, right: RIGHT.initial, leftCollapsed: false, rightCollapsed: false });
  });

  it("the handle moves with the arrow keys and Home resets it", () => {
    const onResize = vi.fn();
    const onReset = vi.fn();
    render(<ResizeHandle side="right" label="Agents panel width" width={300} min={240} max={560} onResize={onResize} onReset={onReset} />);
    const handle = screen.getByRole("separator", { name: "Agents panel width" });
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(onResize).toHaveBeenLastCalledWith(316); // the right panel grows to the left
    fireEvent.keyDown(handle, { key: "Home" });
    expect(onReset).toHaveBeenCalled();
  });

  it("folding the Advisor panel works, and the panel is for typing only (founder F27: voice is on the faces)", () => {
    const onToggle = vi.fn();
    const { rerender } = render(<AdvisorPanel width={380} collapsed={false} onToggle={onToggle} onAgents={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: "Ask the advisor" })).toBeInTheDocument();
    expect(screen.queryByTestId("voice-controls")).not.toBeInTheDocument();
    expect(screen.queryByText("Start voice")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fold the Advisor panel" }));
    expect(onToggle).toHaveBeenCalled();
    rerender(<AdvisorPanel width={380} collapsed onToggle={onToggle} onAgents={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Show the Advisor panel" })).toBeInTheDocument();
  });
});

describe("G: the agent window", () => {
  it("draws where the run is", () => {
    expect(stageNodes(null).every((n) => n.state === "waiting")).toBe(true);
    expect(stageNodes(makeRun({})).map((n) => n.state)).toEqual(["active", "waiting", "waiting", "waiting"]);
    expect(stageNodes(teamRun(["done", "thinking"])).map((n) => n.state)).toEqual(["done", "active", "waiting", "waiting"]);
    expect(stageNodes(teamRun(["done", "done"])).map((n) => n.state)).toEqual(["done", "done", "active", "waiting"]);
    expect(stageNodes(teamRun(["done", "done"], { answer: "Your runway" })).map((n) => n.state)).toEqual([
      "done",
      "done",
      "done",
      "active",
    ]);
    expect(stageNodes(teamRun(["done"], { status: "done" })).every((n) => n.state === "done")).toBe(true);
    expect(stageNodes(teamRun(["thinking"], { status: "cancelled" }))[1]?.state).toBe("failed");
  });

  it("counts agents and puts them on one clock", () => {
    const run = teamRun(["done", "thinking", "queued", "failed"]);
    expect(countAgents(run)).toEqual({ done: 1, working: 1, queued: 1, failed: 1 });
    const bars = agentBars(run, Date.parse("2026-11-18T10:00:20Z"));
    expect(bars).toHaveLength(4);
    expect(bars[0]?.left).toBe(0);
    expect(bars[2]?.width).toBe(0); // queued: not started, no bar
    bars.forEach((b) => expect(b.left + b.width).toBeLessThanOrEqual(100.0001));
  });

  it("is never placed off screen", () => {
    expect(keepOnScreen({ x: 5000, y: -40 }, { w: 460, h: 300 }, { w: 1280, h: 800 })).toEqual({ x: 1136, y: 0 });
    expect(keepOnScreen({ x: -900, y: 5000 }, { w: 460, h: 300 }, { w: 1280, h: 800 })).toEqual({ x: 0, y: 752 });
  });

  it("shows each agent's status and step, closes on Escape, and keeps its place", () => {
    holder.run = teamRun(["done", "querying_data"], { progress: "Step 2 of 3: a1 working…" });
    const onClose = vi.fn();
    window.localStorage.setItem(WINDOW_KEY, JSON.stringify({ x: 40, y: 60 }));
    render(<AgentWindow onClose={onClose} />);
    const dialog = screen.getByRole("dialog", { name: "Agent window" });
    expect(dialog.style.left).toBe("40px");
    expect(dialog.style.top).toBe("60px");
    expect(screen.getAllByTestId("agent-window-row")).toHaveLength(2);
    expect(screen.getByText("Step 2 of 3: a1 working…")).toBeInTheDocument();
    expect(screen.getByTestId("agent-counts")).toHaveTextContent("1 done · 1 working · 0 waiting");
    expect(screen.getByText("finished")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("says what to do when nothing is running", () => {
    render(<AgentWindow onClose={vi.fn()} />);
    expect(screen.getByText(/the agents working on it appear here/)).toBeInTheDocument();
  });
});
