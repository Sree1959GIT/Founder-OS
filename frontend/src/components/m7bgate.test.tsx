import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Figure } from "@/components/common";
import { figureSize, tableTopic, topicOf } from "@/lib/format";

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
