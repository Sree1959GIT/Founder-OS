import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AssumptionTag, CitationChips, LineageChip, Pill, VerifiedBadge } from "@/components/common";
import type { DecisionFrame, OptionCost } from "@/lib/api";
import { metricValue, money, seconds, signedMonths } from "@/lib/format";
import type { RunView } from "@/lib/workspace";

function optionCost(option: OptionCost, currency: string): string {
  if (!option.modelled) return "cost not modelled";
  const parts = [];
  if (option.one_off) parts.push(`${money(option.one_off, currency, 0)} one-off`);
  if (option.monthly) parts.push(`${money(option.monthly, currency, 0)} a month`);
  return parts.join(" + ") || "no new cost";
}

/** In a decision answer: the proposed option first, then what the full model would cost. Both are assumptions. */
export function DecisionLead({ frame }: { frame: DecisionFrame }) {
  const proposed = frame.options.find((o) => o.name === frame.default_option) ?? frame.options[0];
  const full = frame.cost_model?.cases.find((c) => c.name === "base");
  const fullOption = frame.options.find((o) => o.is_full);
  if (!proposed && !full) return null;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[#4A3A1C] bg-[#1A1610] p-2.5 text-[13px]" data-testid="decision-lead">
      {proposed ? (
        <div>
          <p className="text-xs text-muted-foreground">Proposed</p>
          <p className="font-semibold text-foreground">{proposed.name}</p>
          <p className="num text-xs text-foreground">
            {optionCost(proposed, frame.currency)}
            {proposed.modelled ? ` · runway ${signedMonths(proposed.runway_change_months)}` : ""}
          </p>
          {proposed.modelled ? null : <p className="text-xs text-muted-foreground">Not modelled: {proposed.note}</p>}
        </div>
      ) : null}
      {full && !proposed?.is_full ? (
        <div className="border-t border-[#4A3A1C] pt-2">
          <p className="text-xs text-muted-foreground">Full model{fullOption ? `: ${fullOption.name}` : ""}</p>
          <p className="num text-xs text-foreground">
            {money(full.one_off, frame.currency, 0)} one-off + {money(full.monthly, frame.currency, 0)} a month · runway{" "}
            {signedMonths(full.runway_change_months)}
          </p>
        </div>
      ) : null}
      <div>
        <AssumptionTag />
      </div>
    </div>
  );
}

export function AnswerText({ text }: { text: string }) {
  return (
    <div className="prose-chat text-[13.5px] leading-relaxed">
      <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
    </div>
  );
}

export function AnswerCard({ run }: { run: RunView }) {
  const result = run.result;
  const finished = run.status !== "running";
  const provider = result?.advisor_provider ?? "";
  const where = provider === "rules" ? "written by code" : provider === "ollama" ? "local" : provider;
  const removed = result ? result.agents.reduce((n, a) => n + a.removed.length, 0) : 0;
  const unfinishedWithoutAnswer = finished && !run.answer;
  return (
    <article
      aria-label="Advisor answer"
      className="flex flex-col gap-2 rounded-[12px_12px_12px_4px] border border-border bg-card p-3"
      data-testid="advisor-answer"
    >
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          Advisor
          {result ? <span className="num"> · {seconds(result.elapsed_ms)}</span> : null}
          {where ? ` · ${where}` : ""}
        </span>
        <span className="flex-1" />
        {finished ? <VerifiedBadge verified={result ? result.verified : null} checks={result?.issues.length ?? 0} /> : null}
      </div>
      {run.frame ? <DecisionLead frame={run.frame} /> : null}
      {run.answer ? <AnswerText text={run.answer} /> : null}
      {!finished && !run.answer ? (
        <p className="text-[13px] text-muted-foreground" aria-live="polite">
          {run.awaitingApproval ? "The team is waiting for your approval." : "Working on it…"}
        </p>
      ) : null}
      {run.awaitingApproval ? (
        <a
          href="#/activity"
          className="inline-flex h-10 items-center justify-center rounded-lg bg-signal px-3 text-[13px] font-semibold text-[#1A1206] hover:no-underline"
        >
          Review the team
        </a>
      ) : null}
      {unfinishedWithoutAnswer ? (
        <p className="text-[13px] text-muted-foreground">
          {run.status === "cancelled" ? "Stopped." : run.status === "rejected" ? "The team was held back." : "This run did not finish."}
        </p>
      ) : null}
      {result?.metrics.length ? (
        <ul aria-label="Numbers used" className="flex flex-wrap gap-1.5">
          {result.metrics.map((m, i) => (
            <li key={`${m.metric}-${i}`} className="max-w-full">
              <LineageChip lineage={m.lineage} label={`${m.label} ${metricValue(m.value, m.unit, m.metric)}`} />
            </li>
          ))}
        </ul>
      ) : null}
      {result ? <CitationChips citations={result.citations} /> : null}
      {removed > 0 ? (
        <p className="text-xs text-muted-foreground">
          <span className="num">{removed}</span> {removed === 1 ? "claim" : "claims"} taken out by the source check.
        </p>
      ) : null}
      {result?.memo ? (
        <div>
          <a href="#/memo" className="text-[13px]">
            Open the decision memo
          </a>{" "}
          <Pill tone="neutral">Draft</Pill>
        </div>
      ) : null}
    </article>
  );
}
