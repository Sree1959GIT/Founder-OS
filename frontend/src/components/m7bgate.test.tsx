import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Figure } from "@/components/common";
import { figureSize } from "@/lib/format";

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
