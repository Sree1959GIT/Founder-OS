import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Figure } from "@/components/common";
import { BriefAnswer } from "@/components/chat/AnswerCard";
import { briefAnswer, figureSize, tableTopic, topicOf } from "@/lib/format";

/** M7b founder gate (2026-11-26/27): regression tests for F20–F27. Fakes only. */

describe("F20 a figure is never cut off", () => {
  it("shows the whole figure, with no ellipsis or truncation", () => {
    render(<Figure value="$172,280.45" />);
    const figure = screen.getByTestId("figure");
    expect(figure).toHaveTextContent("$172,280.45");
    expect(figure.className).not.toMatch(/truncate|text-ellipsis|line-clamp/);
    expect(figure.className).toContain("[overflow-wrap:anywhere]");
  });

  it("steps a long figure down a size, then lets it wrap", () => {
    expect(figureSize("$9,500")).toBe("text-[22px]");
    expect(figureSize("$172,280.45")).toBe("text-[19px]");
    expect(figureSize("$12,255,344,000.00")).toBe("text-[16px]");
  });
});

describe("F24 the table shows the current topic", () => {
  it("names the topic of a question in a few words", () => {
    expect(topicOf("Should we open a Dubai office?")).toBe("Dubai office");
    expect(topicOf("What is our runway?")).toBe("Runway");
    expect(topicOf("Should we hire two more engineers?")).toBe("Two more engineers");
    expect(topicOf("Should we open a Dubai office? · changed: only two people")).toBe("Dubai office");
  });

  it("never says 'This decision', and follows each new question", () => {
    const dubai = { message: "Should we open a Dubai office?", subject: "This decision" };
    expect(tableTopic(dubai, { message: dubai.message, isDecision: true })).toBe("Dubai office");
    expect(tableTopic({ ...dubai, subject: "A full Dubai office" }, null)).toBe("Dubai office");
    expect(tableTopic(dubai, { message: "Should we raise prices by 10%?", isDecision: false })).toBe("Prices by 10%");
    // Accept and Ask more are steps of the open decision: the topic stays.
    expect(tableTopic(dubai, { message: 'Go with "Partner or distributor": write the decision memo.', isDecision: false })).toBe("Dubai office");
  });
});

describe("F22 the app always opens on Welcome", () => {
  afterEach(() => {
    window.localStorage.clear();
    window.location.hash = "";
    vi.unstubAllGlobals();
  });

  it("offers the open decision in one line instead of reopening it", async () => {
    const { reducer, initialState } = await import("@/lib/workspace");
    const { save } = await import("@/lib/persist");
    let s = reducer(initialState, { type: "session", id: "s1" });
    s = reducer(s, { type: "run", runId: "r1", message: "Should we open a Dubai office?" });
    s = reducer(s, { type: "turn", turn: { id: "you-1", role: "you", text: "Should we open a Dubai office?" } });
    s = reducer(s, { type: "turn", turn: { id: "advisor-r1", role: "advisor", runId: "r1" } });
    const r1 = s.runs.r1;
    if (!r1) throw new Error("no run");
    s = { ...s, runs: { ...s.runs, r1: { ...r1, decisionType: "new_office", status: "done" } } };
    save(s);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    vi.stubGlobal("EventSource", undefined);
    const { default: App } = await import("@/App");
    render(<App />);
    expect(await screen.findByTestId("welcome")).toBeInTheDocument();
    expect(screen.queryByTestId("boardroom")).not.toBeInTheDocument();
    expect(screen.getByTestId("open-decision")).toHaveTextContent(/You have an open decision: Dubai office\.\s*Continue it\?/);
    fireEvent.click(screen.getByRole("link", { name: /Continue it/ }));
    expect(await screen.findByTestId("boardroom")).toBeInTheDocument();
    // What was said before stays folded: the Advisor does not recite it.
    const earlier = screen.getAllByTestId("earlier-turns")[0];
    expect(earlier).toHaveTextContent("Earlier in this conversation (2)");
    expect(earlier).not.toHaveAttribute("open");
  });
});

describe("F23 the Advisor answers in 3 sentences or fewer", () => {
  const wall = [
    "Open through a partner first. It keeps the runway above 14 months. A full office costs $1.5M more a year.",
    "The Verifier checked every figure.",
    "",
    "**Kill criteria**",
    "- Revenue under $40k by June",
    "- Partner churn over 10 %",
    "",
    "**Predictions**",
    "1. Two clients sign by Q2.",
  ].join("\n");

  it("keeps three sentences, and a decimal figure is not a sentence end", () => {
    const { brief, more } = briefAnswer(wall);
    expect(brief).toBe("Open through a partner first. It keeps the runway above 14 months. A full office costs $1.5M more a year.");
    expect(more).toBe(true);
    expect(briefAnswer("Runway is 14.2 months.").more).toBe(false);
  });

  it("folds the rest under Full answer", () => {
    render(<BriefAnswer text={wall} streaming={false} />);
    expect(screen.getByTestId("answer-brief").querySelector("p")).not.toHaveTextContent("Kill criteria");
    expect(screen.getByTestId("answer-full")).not.toHaveAttribute("open");
  });
});
