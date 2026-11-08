import { AssumptionTag, Pill, Section } from "@/components/common";
import type { DecisionFrame, GoalCheck } from "@/lib/api";
import { itemValue, money, signedMonths } from "@/lib/format";

const GOAL_WORDS: Record<string, string> = {
  moves_away: "Moves away from this goal",
  moves_toward: "Moves toward this goal",
  open_question: "Open question",
  neutral: "No effect seen",
};

function GoalRow({ goal }: { goal: GoalCheck }) {
  const words = GOAL_WORDS[goal.status] ?? goal.status.replace(/_/g, " ");
  return (
    <li className="rounded-lg border border-border bg-background p-2.5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-medium">{goal.goal}</span>
        <Pill tone={goal.status === "moves_away" ? "amber" : "neutral"}>{words}</Pill>
      </div>
      {goal.sentence ? <p className="text-xs text-muted-foreground">{goal.sentence}</p> : null}
    </li>
  );
}

export function DecisionFrameCard({ frame }: { frame: DecisionFrame }) {
  const model = frame.cost_model;
  const currency = frame.currency || model?.currency || "USD";
  const low = model?.cases.find((c) => c.name === "low");
  const base = model?.cases.find((c) => c.name === "base");
  const high = model?.cases.find((c) => c.name === "high");
  return (
    <Section title="Decision frame" aside={model ? <AssumptionTag /> : undefined}>
      <div className="flex flex-col gap-4" data-testid="decision-frame">
        {frame.options.length ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">Options</h3>
            <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {frame.options.map((option) => (
                <li key={option.name} className="flex flex-col gap-1 rounded-lg border border-border bg-background p-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-semibold">{option.name}</span>
                    {option.name === frame.default_option ? <Pill tone="amber">Proposed</Pill> : null}
                    {option.is_full ? <Pill>Full model</Pill> : null}
                  </div>
                  {option.modelled ? (
                    <p className="num text-xs">
                      {money(option.one_off, currency, 0)} one-off · {money(option.monthly, currency, 0)} a month · runway{" "}
                      {signedMonths(option.runway_change_months)}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">Not modelled</p>
                  )}
                  {option.trade_off ? <p className="text-xs text-muted-foreground">{option.trade_off}</p> : null}
                  {option.basis === "assumption" ? (
                    <span>
                      <AssumptionTag />
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {model ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              Cost model: {model.subject}
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-[13px]">
                <thead className="text-xs text-muted-foreground">
                  <tr className="border-b border-border">
                    <th scope="col" className="py-1.5 pr-3 font-medium">Item</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">Low</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">Base</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">High</th>
                    <th scope="col" className="py-1.5 font-medium">Basis</th>
                  </tr>
                </thead>
                <tbody>
                  {model.items.map((item) => {
                    const show = (v: number) => itemValue(v, item, currency);
                    return (
                      <tr key={item.key} className="border-b border-border/60">
                        <td className="py-1.5 pr-3">
                          {item.name}
                          <span className="text-xs text-muted-foreground">
                            {item.cadence === "monthly" ? " · a month" : item.cadence === "one_off" ? " · one-off" : ""}
                          </span>
                        </td>
                        <td className="num py-1.5 pr-3 text-right">{show(item.low)}</td>
                        <td className="num py-1.5 pr-3 text-right">{show(item.base)}</td>
                        <td className="num py-1.5 pr-3 text-right">{show(item.high)}</td>
                        <td className="py-1.5">
                          {item.basis === "assumption" ? <AssumptionTag /> : <span className="text-xs text-muted-foreground">{item.basis === "founder" ? "your figure" : "your data"}</span>}
                        </td>
                      </tr>
                    );
                  })}
                  {base ? (
                    <tr>
                      <th scope="row" className="py-1.5 pr-3 text-left font-semibold">Runway change</th>
                      <td className="num py-1.5 pr-3 text-right">{signedMonths(low?.runway_change_months ?? null)}</td>
                      <td className="num py-1.5 pr-3 text-right">{signedMonths(base.runway_change_months)}</td>
                      <td className="num py-1.5 pr-3 text-right">{signedMonths(high?.runway_change_months ?? null)}</td>
                      <td className="py-1.5 text-xs text-muted-foreground">computed</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            {model.scope_note ? <p className="mt-2 text-xs text-muted-foreground">{model.scope_note}</p> : null}
            <p className="num mt-1 break-words text-[11px] text-muted-foreground">{model.formula}</p>
          </div>
        ) : null}

        {frame.goals.length ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">Goal check</h3>
            <ul className="flex flex-col gap-2">
              {frame.goals.map((goal) => (
                <GoalRow key={goal.goal} goal={goal} />
              ))}
            </ul>
          </div>
        ) : null}

        {frame.questions.length ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">To confirm</h3>
            <ul className="list-disc pl-4 text-[13px]">
              {frame.questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Section>
  );
}
