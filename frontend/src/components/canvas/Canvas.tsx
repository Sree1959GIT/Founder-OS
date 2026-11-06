import { useEffect, useState } from "react";

import { AnswerText } from "@/components/chat/AnswerCard";
import { DecisionFrameCard } from "@/components/canvas/DecisionFrameCard";
import { ScenarioSimulator } from "@/components/canvas/ScenarioSimulator";
import { CitationChips, EmptyNote, LineageChip, Pill, Section, VerifiedBadge } from "@/components/common";
import { fetchSummary, type AgentResult, type Artifact, type MetricResult } from "@/lib/api";
import { metricValue, monthLabel } from "@/lib/format";
import { useWorkspace, type RunView } from "@/lib/workspace";

const KPIS = ["runway", "net_burn", "mrr", "gross_margin"];
const KPI_TITLES: Record<string, string> = { runway: "Runway", net_burn: "Net burn", mrr: "MRR", gross_margin: "Gross margin" };

function KpiRow({ refreshKey }: { refreshKey: string }) {
  const [metrics, setMetrics] = useState<MetricResult[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetchSummary(controller.signal)
      .then((summary) => {
        if (!Array.isArray(summary.metrics)) return;
        setMetrics(KPIS.flatMap((k) => summary.metrics.filter((m) => m.metric === k)));
        setProblem(null);
      })
      .catch((err: unknown) => {
        if (!(err instanceof DOMException)) setProblem("Metrics are not available yet.");
      });
    return () => controller.abort();
  }, [refreshKey]);
  if (problem) return <EmptyNote>{problem}</EmptyNote>;
  if (metrics === null) return null;
  if (metrics.length === 0) {
    return (
      <EmptyNote>
        No financial data is loaded. <a href="#/data">Load the data</a> to see your numbers.
      </EmptyNote>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4" data-testid="kpi-row">
      {metrics.map((m) => {
        const zero = m.metric === "runway" ? (m.detail?.zero_cash_month as string | undefined) : undefined;
        return (
          <article key={m.metric} className="flex min-w-0 flex-col gap-1 rounded-xl border border-border bg-card p-3.5" data-testid={`kpi-${m.metric}`}>
            <p className="text-xs text-muted-foreground">{KPI_TITLES[m.metric] ?? m.label}</p>
            <p className="num text-[24px] font-semibold leading-tight">{metricValue(m.value, m.unit, m.metric)}</p>
            <p className="min-h-4 text-xs text-muted-foreground">
              {zero ? <>Zero cash {monthLabel(zero.slice(0, 7))}</> : <>As of {monthLabel(m.as_of)}</>}
            </p>
            <div className="min-w-0">
              <LineageChip lineage={m.lineage} />
            </div>
          </article>
        );
      })}
    </div>
  );
}

interface Risk {
  risk: string;
  likelihood?: string;
  impact?: string;
  mitigation?: string;
}

function RiskList({ artifact }: { artifact: Artifact }) {
  const risks = Array.isArray(artifact.data.risks) ? (artifact.data.risks as Risk[]) : [];
  if (!risks.length) return null;
  return (
    <ul className="mb-3 flex flex-col gap-2" aria-label="Risks">
      {risks.map((r, i) => {
        const high = (r.likelihood ?? "").toLowerCase() === "high" || (r.impact ?? "").toLowerCase() === "high";
        return (
          <li key={i} className="rounded-lg border border-border bg-background p-2.5">
            <div className="mb-1 flex items-start gap-2">
              <span
                className={
                  high
                    ? "rounded bg-signal px-1.5 py-0.5 text-[11px] font-semibold text-[#1A1206]"
                    : "rounded bg-[#3A4150] px-1.5 py-0.5 text-[11px] font-semibold text-foreground"
                }
              >
                {high ? "High" : "Med"}
              </span>
              <span className="text-[13px]">{r.risk}</span>
            </div>
            {r.mitigation ? <p className="text-xs text-muted-foreground">Mitigation: {r.mitigation}</p> : null}
          </li>
        );
      })}
    </ul>
  );
}

function FindingCard({ agent }: { agent: AgentResult }) {
  const risks = agent.artifacts.filter((a) => a.kind === "risk_register");
  return (
    <Section
      title={agent.name}
      aside={
        <span className="flex items-center gap-2">
          {agent.status !== "done" ? <Pill tone="danger">{agent.status}</Pill> : null}
          <VerifiedBadge verified={agent.verified} />
        </span>
      }
    >
      {risks.map((a) => (
        <RiskList key={a.id} artifact={a} />
      ))}
      {agent.text ? <AnswerText text={agent.text} /> : null}
      {agent.citations.length ? (
        <div className="mt-2">
          <CitationChips citations={agent.citations} />
        </div>
      ) : null}
      {agent.removed.length ? (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="num">{agent.removed.length}</span> {agent.removed.length === 1 ? "claim" : "claims"} taken out by the source check.
        </p>
      ) : null}
    </Section>
  );
}

function Findings({ run }: { run: RunView }) {
  const agents = (run.result?.agents ?? []).filter((a) => a.type !== "memo_writer" && (a.text || a.artifacts.length));
  if (!agents.length) return null;
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2" data-testid="findings">
      {agents.map((agent) => (
        <FindingCard key={agent.agent_id} agent={agent} />
      ))}
    </div>
  );
}

export function Canvas() {
  const { currentRun: run } = useWorkspace();
  const isDecision = Boolean(run && (run.frame || run.decisionType));
  const reviewDate = run?.result?.memo?.review_date;
  return (
    <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-4 px-6 py-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <span className="text-xs text-muted-foreground">{isDecision ? "Open decision" : "Workspace"}</span>
          <h1 className="text-[22px] font-bold tracking-tight">{isDecision ? (run?.frame?.subject || run?.message) : "No decision open yet"}</h1>
        </div>
        {run?.reversibility === "one_way" ? <Pill tone="amber">One-way door · full analysis</Pill> : null}
        {run?.reversibility === "two_way" ? <Pill tone="info">Two-way door · light analysis</Pill> : null}
        {reviewDate ? (
          <Pill>
            Review on <span className="num">{reviewDate}</span>
          </Pill>
        ) : null}
      </div>
      <KpiRow refreshKey={run?.status ?? "none"} />
      {run?.frame ? <DecisionFrameCard frame={run.frame} /> : null}
      <ScenarioSimulator frame={run?.frame ?? null} />
      {run ? <Findings run={run} /> : null}
    </main>
  );
}
