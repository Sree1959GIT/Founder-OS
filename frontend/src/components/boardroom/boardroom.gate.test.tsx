import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BoardroomStage } from "@/components/boardroom/Boardroom";
import { memberOf } from "@/components/boardroom/faces";
import { MAX_TEAM_SEATS, seatPositions, seatSize, teamSeats } from "@/lib/boardroom";
import { typingIn } from "@/lib/voiceContext";
import type { RunView } from "@/lib/workspace";

/** M7b founder gate: F25 (the table adapts to the team), F26 (Focus on the team), F27 (voice on the faces). */

const TYPES = ["financial_analyst", "market_scout", "librarian", "people_ops", "devils_advocate"];
const agents = Object.fromEntries(
  [...TYPES, "financial_analyst"].map((type, i) => [
    `a${i}`,
    { id: `a${i}`, type, name: memberOf(type).name, status: "thinking", is_cloud: false, provider: "ollama", startedAt: `2026-11-27T10:0${i}:00Z` },
  ]),
);
const run = {
  id: "r1",
  message: "Should we open a Dubai office?",
  status: "running",
  order: Object.keys(agents),
  agents,
  proposedTeam: [],
  answer: "",
  turns: [],
} as unknown as RunView;

const voice = {
  voice: "speaking",
  on: true,
  mode: "duplex",
  talkingTo: { id: "market_scout", name: "Market Scout" } as { id: string; name: string } | null,
  talkTo: vi.fn(),
  hush: vi.fn(),
  muted: false,
  toggleMute: vi.fn(),
  disconnect: vi.fn(),
  saying: "Open through a partner first.",
  heard: "",
  missed: false,
  unsure: "",
  error: null,
  turn: null,
  barge: null,
};

vi.mock("@/lib/voiceContext", async (orig) => ({
  ...(await orig<typeof import("@/lib/voiceContext")>()),
  useVoice: () => voice,
}));
vi.mock("@/lib/workspace", async (orig) => ({
  ...(await orig<typeof import("@/lib/workspace")>()),
  useWorkspace: () => ({ state: { turns: [], runs: { r1: run }, sending: false }, send: vi.fn(), currentRun: run, decisionRun: null }),
}));

beforeEach(() => {
  voice.talkTo.mockClear();
  voice.hush.mockClear();
});

describe("F25 the table adapts to the team", () => {
  it("one seat per agent type the planner chose (a re-run keeps one seat), at most 8", () => {
    const team = [...TYPES, "financial_analyst"].map((type, i) => ({ id: `x${i}`, type }));
    expect(teamSeats(team).map((a) => a.type)).toEqual(TYPES);
    expect(teamSeats(team).find((a) => a.type === "financial_analyst")?.id).toBe("x5"); // the newest card
    const many = Array.from({ length: 12 }, (_, i) => ({ id: `m${i}`, type: `t${i}` }));
    expect(teamSeats(many)).toHaveLength(MAX_TEAM_SEATS);
  });

  it("spaces the seats evenly from the top and shrinks faces for a big team", () => {
    expect(seatPositions(4)).toEqual([
      { left: 50, top: 9 },
      { left: 95, top: 50 },
      { left: 50, top: 91 },
      { left: 5, top: 50 },
    ]);
    expect(seatSize(3)).toBeGreaterThan(seatSize(9));
  });

  it("draws the host plus one seat per agent, each with a name tag in its own colour", () => {
    render(<BoardroomStage>{null}</BoardroomStage>);
    const table = screen.getByTestId("boardroom-table");
    expect(table).toHaveAttribute("data-seats", String(1 + TYPES.length)); // no empty seats, no duplicate
    const tags = within(table).getAllByTestId("seat-name");
    expect(tags.map((t) => t.textContent)).toEqual(["Advisor", ...TYPES.map((t) => memberOf(t).name)]);
    tags.forEach((tag, i) => {
      const type = i === 0 ? "advisor" : (TYPES[i - 1] ?? "");
      expect(tag.style.backgroundColor).not.toBe("");
      expect(memberOf(type).color).toMatch(/^#/);
    });
  });
});

describe("F27 voice lives on the faces", () => {
  it("a tap on a face talks to that agent, and the LIVE bar says who", () => {
    render(<BoardroomStage>{null}</BoardroomStage>);
    const table = screen.getByTestId("boardroom-table");
    fireEvent.click(within(table).getByRole("button", { name: "Talk to Librarian" }));
    expect(voice.talkTo).toHaveBeenCalledWith("librarian", "Librarian");
    expect(within(table).getByRole("button", { name: "Stop talking to Market Scout" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("talking-to")).toHaveTextContent("Talking to Market Scout");
    expect(screen.queryByText("Start voice")).not.toBeInTheDocument();
  });

  it("the speaking face has a Speaking tag whose Stop button only hushes the voice", () => {
    render(<BoardroomStage>{null}</BoardroomStage>);
    const table = screen.getByTestId("boardroom-table");
    const tag = within(table).getByTestId("speaking-tag");
    expect(tag.closest("[data-testid=seat]")).toHaveAttribute("data-type", "advisor");
    fireEvent.click(within(tag).getByRole("button", { name: /Stop Advisor speaking/ }));
    expect(voice.hush).toHaveBeenCalledTimes(1);
    expect(voice.disconnect).not.toHaveBeenCalled();
  });

  it("keys never fire while the member types or presses a button", () => {
    const input = document.createElement("input");
    const button = document.createElement("button");
    const div = document.createElement("div");
    expect(typingIn(input)).toBe(true);
    expect(typingIn(button)).toBe(true);
    expect(typingIn(div)).toBe(false);
  });
});

describe("F27 the voice's messages on the phone", () => {
  it("shows who the member talks to, and a blocked mic, in the phone stage", () => {
    render(<BoardroomStage>{null}</BoardroomStage>);
    expect(screen.getAllByTestId("phone-voice-notice")[0]).toHaveTextContent("Talking to Market Scout");
  });
});

describe("F26 Focus on the team", () => {
  it("folds both panels, and shows them again", () => {
    const toggle = vi.fn();
    const { rerender } = render(<BoardroomStage focus={{ on: false, toggle }}>{null}</BoardroomStage>);
    fireEvent.click(screen.getByRole("button", { name: "Focus on the team" }));
    expect(toggle).toHaveBeenCalled();
    rerender(<BoardroomStage focus={{ on: true, toggle }}>{null}</BoardroomStage>);
    expect(screen.getByRole("button", { name: "Show panels" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("F26 both panels fold and are remembered", () => {
  it("Focus folds both and the choice is kept per viewer", async () => {
    const { renderHook, act } = await import("@testing-library/react");
    const { usePanelLayout, loadLayout } = await import("@/lib/layout");
    window.localStorage.clear();
    const { result } = renderHook(() => usePanelLayout());
    act(() => result.current.toggleRight());
    expect(result.current.layout.rightCollapsed).toBe(true);
    act(() => result.current.toggleFocus());
    expect(result.current.focused).toBe(true);
    expect(loadLayout()).toMatchObject({ leftCollapsed: true, rightCollapsed: true });
    act(() => result.current.toggleFocus());
    expect(result.current.layout).toMatchObject({ leftCollapsed: false, rightCollapsed: false });
  });
});
