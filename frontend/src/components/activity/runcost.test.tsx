import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/** Founder F12b: "Run cost" in the Activity header is in the member's currency; US$ only in the tooltip. */

const run = {
  id: "run_1",
  message: "Should we open in Dubai?",
  status: "done",
  agents: {},
  result: { est_cost_usd: 0.285, cost_shown: "about ₹25" },
};
vi.mock("@/lib/workspace", () => ({
  useWorkspace: () => ({ currentRun: run }),
  teamOf: () => [],
}));
vi.mock("@/hooks/useCatalog", () => ({
  useCatalog: () => null,
  cloudOn: () => true,
  slotsInUse: () => ({ local: 0, cloud: 0 }),
}));

const { AgentActivity } = await import("@/components/activity/AgentActivity");

describe("Activity header, fix round 3", () => {
  it("F12b: the run cost reads in rupees, the US dollars only in the tooltip, to 2 decimals", () => {
    render(<AgentActivity />);
    const cost = screen.getByTestId("run-cost");
    expect(cost).toHaveTextContent("about ₹25");
    expect(cost.textContent).not.toContain("$");
    expect(cost.parentElement).toHaveAttribute("title", expect.stringContaining("(US$0.29)") as unknown as string);
  });
});
