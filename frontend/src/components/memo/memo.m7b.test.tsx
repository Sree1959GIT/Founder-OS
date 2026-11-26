import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { memoWhen } from "@/lib/format";

/** Founder F18: the memo page. Fakes only. */
const send = vi.fn();
vi.mock("@/lib/workspace", () => ({ useWorkspace: () => ({ currentRun: null, send, state: { sending: false } }) }));
vi.mock("@/components/memo/PriorityMatrix", () => ({ PriorityMatrix: () => null }));
vi.mock("@/lib/api", () => ({
  fetchNotes: () => Promise.resolve({ notes: [{ path: "decisions/2026-11-26-dubai.md", title: "Dubai office" }] }),
  fetchNote: () =>
    Promise.resolve({
      path: "decisions/2026-11-26-dubai.md",
      kind: "md",
      title: "Dubai office",
      body: "# Dubai office\\n\\nPartner first.",
      frontmatter: { title: "Dubai office", status: "proposed", written_at: "2026-11-26T10:42", proposed_option: "Partner or distributor" },
      backlinks: [],
    }),
  fetchMemoVersions: () =>
    Promise.resolve({ path: "x", versions: [{ id: "20261126T093000", written_at: "2026-11-26T09:30", title: "Dubai office", proposed_option: "Travel-led pilot" }] }),
  fetchMemoVersion: () => Promise.resolve({ id: "20261126T093000", frontmatter: { status: "proposed" }, body: "Travel first." }),
  saveNote: vi.fn(),
}));

const { MemoView } = await import("@/components/memo/MemoView");

describe("F18: one memo per decision, with its versions", () => {
  it("shows Latest with date and time, earlier versions, Close, Regenerate and Ask the team", async () => {
    render(<MemoView path="decisions/2026-11-26-dubai.md" />);
    await waitFor(() => expect(screen.getByTestId("memo-latest")).toHaveTextContent(`Latest · ${memoWhen("2026-11-26T10:42")}`));
    expect(screen.getByTestId("memo-versions")).toHaveTextContent("Travel-led pilot");
    expect(screen.getByRole("link", { name: "Back to the decision" })).toHaveAttribute("href", "#/");
    expect(screen.getByRole("button", { name: "Close the memo" })).toBeInTheDocument();
    screen.getByRole("button", { name: "Regenerate memo" }).click();
    expect(send).toHaveBeenCalledWith('Write the memo again for "Dubai office", with what we know now.');
    expect(screen.getByRole("button", { name: "Ask the team about this" })).toBeInTheDocument();
    screen.getByRole("button", { name: /Travel-led pilot/ }).click();
    await waitFor(() => expect(screen.getByTestId("memo-sheet")).toHaveTextContent("Earlier version"));
  });

  it("formats when a memo was written", () => {
    expect(memoWhen("2026-11-26")).toBe("26 Nov 2026");
    expect(memoWhen("20261126T093000")).toMatch(/^26 Nov 2026, \d{2}:\d{2}$/);
    expect(memoWhen("")).toBe("");
  });
});
