import { Pill } from "@/components/common";
import { useWorkspace, type AgentView } from "@/lib/workspace";

/** Where the agent ran. Founder F19: after a switch to Qwen it says so, not the cloud provider it was planned on. */
export function WhereBadge({ agent }: { agent: Pick<AgentView, "is_cloud" | "provider" | "fallback"> }) {
  if (agent.fallback) {
    return (
      <Pill tone="info" title={agent.fallback}>
        Switched to Qwen
      </Pill>
    );
  }
  return <Pill tone={agent.is_cloud ? "amber" : "ok"}>{agent.is_cloud ? `Cloud · ${agent.provider}` : "Local"}</Pill>;
}

/**
 * On the agent's own card (founder F8d, F19): the slow-agent offer with its two choices, the same offer as in the
 * Advisor panel (answering either answers both), and the sentence saying the agent finished on Qwen.
 */
export function AgentNotices({ runId, agent, compact = false }: { runId: string; agent: AgentView; compact?: boolean }) {
  const { state, slow } = useWorkspace();
  const offer = state.turns.find((t) => t.role === "slow" && t.agentId === agent.id && t.runId === runId);
  const pending = offer && offer.role === "slow" && offer.status === "offered" && !agent.fallback && agent.status !== "done";
  return (
    <>
      {agent.fallback ? (
        <p className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-info" data-testid="agent-fallback" role="status">
          {agent.fallback}
        </p>
      ) : null}
      {pending && offer.role === "slow" ? (
        <div className="flex flex-col gap-1.5 rounded-lg border border-attention-border bg-attention p-2" data-testid="agent-slow" role="status">
          <p className="text-xs text-foreground">{compact ? "Taking longer than usual." : `Taking longer than usual: ${offer.reason || agent.slowReason}.`}</p>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => void slow(offer.id, true)}
              className="min-h-[36px] rounded-full bg-signal px-3 text-xs font-semibold text-on-signal hover:bg-signal/90"
            >
              Continue on Qwen on our server
            </button>
            <button
              type="button"
              onClick={() => void slow(offer.id, false)}
              className="min-h-[36px] rounded-full border border-border-strong bg-card px-3 text-xs text-foreground hover:bg-accent"
            >
              Keep waiting
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
