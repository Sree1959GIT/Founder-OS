import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AgentNotices, WhereBadge } from "@/components/activity/AgentNotices";
import { caption, evidenceLine, seatStatus, speakingId } from "@/lib/boardroom";
import { micProblem } from "@/lib/voiceContext";
import type { AgentView, RunView, Turn } from "@/lib/workspace";

/** M7b: the agent's card (F8d, F19), the Boardroom's seats and caption, and the friendly mic message. Fakes only. */

const slow = vi.fn();
const turns: Turn[] = [
  { id: "t1", role: "slow", runId: "r1", agentId: "a1", text: "People & Ops is taking longer…", reason: "Groq has not answered in 5 s", status: "offered" },
];
vi.mock("@/lib/workspace", async (orig) => ({
  ...(await orig<typeof import("@/lib/workspace")>()),
  useWorkspace: () => ({ state: { turns }, slow }),
}));

const agent = (extra: Partial<AgentView> = {}) =>
  ({ id: "a1", type: "people_ops", name: "People & Ops", is_cloud: true, provider: "groq", status: "waiting_cloud", ...extra }) as AgentView;

describe("F8d and F19 on the agent's card", () => {
  it("shows the slow offer with both choices", () => {
    render(<AgentNotices runId="r1" agent={agent({ slowReason: "Groq has not answered in 5 s" })} />);
    expect(screen.getByTestId("agent-slow")).toHaveTextContent("Groq has not answered in 5 s");
    screen.getByRole("button", { name: "Continue on Qwen on our server" }).click();
    expect(slow).toHaveBeenCalledWith("t1", true);
    expect(screen.getByRole("button", { name: "Keep waiting" })).toBeInTheDocument();
  });

  it("says the switch to Qwen instead of the planned cloud provider", () => {
    const text = "Groq hit its per-minute limit, so People & Ops finished on Qwen on our server.";
    render(
      <>
        <WhereBadge agent={agent({ fallback: text })} />
        <AgentNotices runId="r1" agent={agent({ fallback: text, status: "done" })} />
      </>,
    );
    expect(screen.getByText("Switched to Qwen")).toBeInTheDocument();
    expect(screen.queryByText(/Cloud · groq/)).toBeNull();
    expect(screen.getByTestId("agent-fallback")).toHaveTextContent(text);
    expect(screen.queryByTestId("agent-slow")).toBeNull(); // the offer is over once it switched
  });
});

describe("the Boardroom's seats and caption", () => {
  it("says done / thinking / next / slow / switched under each face", () => {
    expect(seatStatus(agent({ status: "done" })).text).toBe("done ✓");
    expect(seatStatus(agent({ status: "thinking" })).text).toBe("thinking…");
    expect(seatStatus(agent({ status: "queued" })).text).toBe("next");
    expect(seatStatus(agent({ status: "thinking", slowReason: "slow" })).text).toBe("slow");
    expect(seatStatus(agent({ status: "thinking", fallback: "x" })).text).toBe("switched to Qwen");
  });

  it("glows the newest working agent, or the Advisor while the voice speaks", () => {
    const run = { status: "running", answer: "" } as RunView;
    const a = agent({ id: "a", status: "thinking", startedAt: "2026-11-26T10:00:00Z" });
    const b = agent({ id: "b", status: "thinking", startedAt: "2026-11-26T10:01:00Z" });
    expect(speakingId(run, [a, b], false)).toBe("b");
    expect(speakingId(run, [a, b], true)).toBe("advisor");
    expect(speakingId(null, [], false)).toBeNull();
  });

  it("captions the voice first, then the last lane line, never an old line after a new question", () => {
    const lane: Turn[] = [{ id: "l", role: "lane", text: "Team: Financial Analyst.", kind: "narration" }];
    expect(caption(lane, "", "")?.text).toBe("Team: Financial Analyst.");
    expect(caption(lane, "Here is what I found.", "")?.text).toBe("Here is what I found.");
    expect(caption(lane, "", "should we")?.who).toBe("you");
    expect(caption([...lane, { id: "y", role: "you", text: "Next?" }], "", "")).toBeNull();
  });

  it("counts sources and checks for the evidence link", () => {
    const run = {
      agents: { a: { verified: true }, b: { verified: null } },
      result: { agents: [{ citations: [{ path: "p.md", heading: "", chunk_id: "1" }, { path: "q.md", heading: "", chunk_id: "2" }] }] },
    } as unknown as RunView;
    expect(evidenceLine(run)).toBe("2 sources · 1 check");
  });
});

describe("the microphone message", () => {
  it("is friendly about https and permission", () => {
    expect(micProblem("Cannot read properties of undefined (reading 'getUserMedia')", false)).toMatch(/secure \(https\)/);
    expect(micProblem("Voice connection closed", false)).toBe("Voice connection closed"); // not every error is the mic
    expect(micProblem("NotAllowedError: Permission denied", true)).toMatch(/blocked/);
  });
});
