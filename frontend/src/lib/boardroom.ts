/** M7b Boardroom: who is speaking, what each seat says under its face, and the live caption. Words only, no maths. */
import { useWorkspace, type AgentView, type RunView, type Turn } from "@/lib/workspace";

export type SeatTone = "done" | "working" | "next" | "slow" | "switched" | "failed" | "idle";

const WORKING = new Set(["thinking", "querying_data", "searching_vault", "searching_web", "waiting_cloud", "verifying"]);

/** Under each face: done ✓ / thinking… / next / slow / switched to Qwen (founder F8d, F19). */
export function seatStatus(agent: Pick<AgentView, "status" | "slowReason" | "fallback">): { text: string; tone: SeatTone } {
  if (agent.fallback && agent.status !== "failed") {
    return agent.status === "done" ? { text: "done on Qwen ✓", tone: "switched" } : { text: "switched to Qwen", tone: "switched" };
  }
  if (agent.status === "done") return { text: "done ✓", tone: "done" };
  if (agent.status === "failed") return { text: "could not finish", tone: "failed" };
  if (agent.status === "cancelled") return { text: "held back", tone: "idle" };
  if (agent.slowReason) return { text: "slow", tone: "slow" };
  if (agent.status === "queued") return { text: "next", tone: "next" };
  if (WORKING.has(agent.status)) return { text: "thinking…", tone: "working" };
  return { text: agent.status, tone: "idle" };
}

/**
 * The one face that glows: the Advisor while the voice speaks or the answer streams, otherwise the agent that is
 * working now (the one that started last). null: nobody is speaking.
 */
export function speakingId(run: RunView | null, agents: AgentView[], voiceSpeaking: boolean): string | null {
  if (voiceSpeaking) return "advisor";
  if (!run) return null;
  const working = agents.filter((a) => WORKING.has(a.status));
  if (working.length) {
    return [...working].sort((a, b) => (b.startedAt ?? "").localeCompare(a.startedAt ?? ""))[0]?.id ?? null;
  }
  if (run.status === "running" && run.answer) return "advisor";
  return null;
}

/** The live caption: what the voice is saying, else the last thing the Advisor said in the lane. */
export function caption(turns: Turn[], voiceSaying: string, heard: string): { who: "you" | "advisor"; text: string } | null {
  if (heard) return { who: "you", text: heard };
  if (voiceSaying) return { who: "advisor", text: voiceSaying };
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const t = turns[i];
    if (t?.role === "lane" || t?.role === "slow" || t?.role === "amendment") {
      const text = t.role === "amendment" ? (t.offer ?? t.text) : t.text;
      if (text.trim()) return { who: "advisor", text };
    }
    if (t?.role === "you") return null; // the newest thing is the member's own question: nothing said since
  }
  return null;
}

/** "12 sources · 9 checks": what the options rest on, counted from the run (citations and Verifier checks). */
export function evidenceLine(run: RunView | null): string {
  if (!run) return "";
  const agents = run.result?.agents ?? [];
  const sources = new Set(agents.flatMap((a) => a.citations.map((c) => `${c.path}#${c.chunk_id ?? ""}`))).size;
  const checks = Object.values(run.agents).filter((a) => a.verified !== null).length;
  const parts = [];
  if (sources) parts.push(`${sources} ${sources === 1 ? "source" : "sources"}`);
  if (checks) parts.push(`${checks} ${checks === 1 ? "check" : "checks"}`);
  return parts.join(" · ");
}

/** The run the Boardroom shows: the newest run, or the open decision when a small question follows it. */
export function useBoardroomRun(): { run: RunView | null; decision: RunView | null } {
  const { currentRun, decisionRun } = useWorkspace();
  return { run: currentRun ?? decisionRun, decision: decisionRun };
}
