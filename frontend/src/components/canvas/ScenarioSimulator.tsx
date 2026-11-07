import { useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AssumptionTag, ErrorNote, LineageChip, Section } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  postMonteCarlo,
  postScenario,
  type DecisionFrame,
  type MonteCarloResult,
  type ScenarioAdjustments,
  type ScenarioResult,
} from "@/lib/api";
import { money, moneyShort, monthLabel } from "@/lib/format";

const BASE = "#7FB2F5";
const SCENARIO = "#F2A93B";
const NEUTRAL: ScenarioAdjustments = {
  price_change_pct: 0,
  churn_change_pts: 0,
  cac_change_pct: 0,
  new_hires: 0,
  spend_change_monthly: 0,
  one_off_cost: 0,
};

type Lever = {
  key: keyof ScenarioAdjustments;
  label: string;
  min: number;
  max: number;
  step: number;
  show: (v: number) => string;
};

const signed = (v: number, unit: string) => `${v > 0 ? "+" : ""}${v}${unit}`;
const LEVERS: Lever[] = [
  { key: "price_change_pct", label: "Price change", min: -30, max: 30, step: 1, show: (v) => signed(v, "%") },
  { key: "churn_change_pts", label: "Churn change", min: -5, max: 5, step: 0.5, show: (v) => signed(v, " pts") },
  { key: "cac_change_pct", label: "CAC change", min: -50, max: 50, step: 5, show: (v) => signed(v, "%") },
  { key: "new_hires", label: "New hires", min: 0, max: 20, step: 1, show: (v) => String(v) },
  { key: "spend_change_monthly", label: "Spend a month", min: -50_000, max: 100_000, step: 1000, show: (v) => money(v, "USD", 0) },
  { key: "one_off_cost", label: "One-off cost", min: 0, max: 500_000, step: 5000, show: (v) => money(v, "USD", 0) },
];

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

function Legend({ items }: { items: { color: string; dashed?: boolean; label: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-3 text-xs text-muted-foreground">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden="true">
            <line x1="0" y1="3" x2="22" y2="3" stroke={item.color} strokeWidth="2.5" strokeDasharray={item.dashed ? "7 5" : undefined} />
          </svg>
          {item.label}
        </li>
      ))}
    </ul>
  );
}

const axisProps = {
  tick: { fill: "#9AA3B2", fontSize: 11, fontFamily: "JetBrains Mono, monospace" },
  tickLine: false,
  axisLine: { stroke: "#262B35" },
} as const;

const tooltipStyle = {
  contentStyle: { background: "#11151B", border: "1px solid #2A303B", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#9AA3B2" },
  itemStyle: { color: "#E6E8EC", fontFamily: "JetBrains Mono, monospace" },
} as const;

const toMonth = (value: string | null) => (value ? value.slice(0, 7) : null);

function CashChart({ result }: { result: ScenarioResult }) {
  const zero = toMonth(result.scenario_zero_cash_month);
  const months = result.points.map((p) => p.month);
  const at = zero ? months.indexOf(zero) : -1;
  const bandStart = at >= 0 ? (months[Math.max(0, at - 3)] ?? null) : null;
  // The axis fits the data, not zero to the top (founder review 6), with a little room above and below.
  const values = result.points.flatMap((p) => [Number(p.base_cash), Number(p.scenario_cash)]).filter(Number.isFinite);
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 1;
  const pad = Math.max((hi - lo) * 0.08, Math.abs(hi) * 0.01, 1);
  const same = result.points.every((p) => Number(p.base_cash) === Number(p.scenario_cash));
  return (
    <div className="relative h-[280px] w-full" role="img" aria-label="Cash by month, base against scenario">
      {same ? (
        <p className="absolute right-8 top-0 z-10 text-xs text-muted-foreground">The scenario matches the base.</p>
      ) : null}
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={result.points} margin={{ top: 12, right: 24, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="#262B35" vertical={false} />
          <XAxis dataKey="month" tickFormatter={monthLabel} minTickGap={32} {...axisProps} />
          <YAxis
            tickFormatter={(v: number) => moneyShort(v, result.currency)}
            width={64}
            domain={[Math.floor(lo - pad), Math.ceil(hi + pad)]}
            allowDataOverflow={false}
            {...axisProps}
          />
          <Tooltip
            {...tooltipStyle}
            labelFormatter={(m: string) => monthLabel(m)}
            formatter={(v: number, name: string) => [money(v, result.currency, 0), name]}
          />
          {bandStart && zero ? (
            <ReferenceArea
              x1={bandStart}
              x2={zero}
              fill={SCENARIO}
              fillOpacity={0.14}
              label={{ value: "Under 3 months of cash", position: "insideTop", fill: "#F2C77A", fontSize: 11 }}
            />
          ) : null}
          {zero && at >= 0 ? (
            <ReferenceLine
              x={zero}
              stroke={SCENARIO}
              strokeDasharray="3 3"
              label={{ value: "Zero cash", position: "insideBottomRight", fill: "#F2C77A", fontSize: 11 }}
            />
          ) : null}
          {/* The scenario first and wider, the base on top and thinner: where they overlap, both stay visible. */}
          <Line
            type="monotone"
            dataKey="scenario_cash"
            name="Scenario"
            stroke={SCENARIO}
            strokeWidth={3.5}
            strokeDasharray="7 5"
            dot={false}
            isAnimationActive={false}
          />
          <Line type="monotone" dataKey="base_cash" name="Base" stroke={BASE} strokeWidth={1.75} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function FanChart({ result, currency }: { result: MonteCarloResult; currency: string }) {
  return (
    <div className="h-[220px] w-full" role="img" aria-label="Monte Carlo range of cash by month">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={result.points} margin={{ top: 12, right: 24, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="#262B35" vertical={false} />
          <XAxis dataKey="month" tickFormatter={monthLabel} minTickGap={32} {...axisProps} />
          <YAxis tickFormatter={(v: number) => moneyShort(v, currency)} width={64} {...axisProps} />
          <Tooltip
            {...tooltipStyle}
            labelFormatter={(m: string) => monthLabel(m)}
            formatter={(v: number | number[], name: string) => [
              Array.isArray(v) ? `${money(v[0] ?? 0, currency, 0)} to ${money(v[1] ?? 0, currency, 0)}` : money(v, currency, 0),
              name,
            ]}
          />
          <Area
            type="monotone"
            dataKey={(p: { p10: number; p90: number }) => [p.p10, p.p90]}
            name="P10 to P90"
            stroke="none"
            fill={SCENARIO}
            fillOpacity={0.2}
            isAnimationActive={false}
          />
          <Line type="monotone" dataKey="p50" name="P50" stroke={SCENARIO} strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-background px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="num truncate text-[15px] font-semibold">{value}</p>
    </div>
  );
}

const runway = (months: number | null) => (months === null ? "beyond the model" : `${months.toFixed(2)} mo`);

export function ScenarioSimulator({ frame }: { frame: DecisionFrame | null }) {
  const [levers, setLevers] = useState<ScenarioAdjustments>(NEUTRAL);
  const [scenario, setScenario] = useState<ScenarioResult | null>(null);
  const [fan, setFan] = useState<MonteCarloResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const forChart = useDebounced(levers, 150);
  const forFan = useDebounced(levers, 400);

  useEffect(() => {
    const controller = new AbortController();
    postScenario(forChart, controller.signal)
      .then((result) => {
        if (!Array.isArray(result.points)) return;
        setScenario(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!(err instanceof DOMException)) setError(err instanceof Error ? err.message : "The scenario did not run");
      });
    return () => controller.abort();
  }, [forChart]);

  useEffect(() => {
    const controller = new AbortController();
    postMonteCarlo(forFan, controller.signal)
      .then((result) => {
        if (Array.isArray(result.points)) setFan(result);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [forFan]);

  const modelled = (frame?.options ?? []).filter((o) => o.modelled);
  const changed = LEVERS.some((l) => levers[l.key] !== 0);

  return (
    <>
      <Section
        title="Cash runway · base vs scenario"
        aside={<Legend items={[{ color: BASE, label: "Base" }, { color: SCENARIO, dashed: true, label: "Scenario" }]} />}
      >
        <div data-testid="scenario-simulator" className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_260px]">
          <div className="min-w-0">
            {error ? <ErrorNote>{error}</ErrorNote> : null}
            {scenario ? <CashChart result={scenario} /> : !error ? <div className="h-[280px]" /> : null}
            {scenario ? (
              <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
                <Tile label="Base, with growth" value={runway(scenario.base_runway_months)} />
                <Tile label="Scenario, with growth" value={runway(scenario.scenario_runway_months)} />
                <Tile label="Base zero cash" value={monthLabel(toMonth(scenario.base_zero_cash_month)) || "beyond the model"} />
                <Tile label="Scenario zero cash" value={monthLabel(toMonth(scenario.scenario_zero_cash_month)) || "beyond the model"} />
              </div>
            ) : null}
            {scenario ? (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <AssumptionTag />
                <span className="min-w-0">{scenario.growth_assumption}</span>
                <LineageChip lineage={scenario.lineage} label="Scenario formula" />
              </div>
            ) : null}
            {scenario ? (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-muted-foreground">Show as a table</summary>
                <div className="mt-1 max-h-56 overflow-auto">
                  <table className="w-full text-left">
                    <thead className="text-muted-foreground">
                      <tr>
                        <th scope="col" className="py-1 pr-3 font-medium">Month</th>
                        <th scope="col" className="py-1 pr-3 text-right font-medium">Base</th>
                        <th scope="col" className="py-1 text-right font-medium">Scenario</th>
                      </tr>
                    </thead>
                    <tbody className="num">
                      {scenario.points.map((p) => (
                        <tr key={p.month}>
                          <td className="py-0.5 pr-3">{p.month}</td>
                          <td className="py-0.5 pr-3 text-right">{money(p.base_cash, scenario.currency, 0)}</td>
                          <td className="py-0.5 text-right">{money(p.scenario_cash, scenario.currency, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            ) : null}
          </div>
          <div className="flex flex-col gap-3">
            <h3 className="text-[13px] font-semibold">Scenario levers</h3>
            {LEVERS.map((lever) => {
              const value = levers[lever.key];
              return (
                <div key={lever.key} className="flex flex-col gap-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <label htmlFor={`lever-${lever.key}`} className="text-xs text-muted-foreground">
                      {lever.label}
                    </label>
                    <span className="num text-xs text-signal-soft">{lever.show(value)}</span>
                  </div>
                  <input
                    id={`lever-${lever.key}`}
                    type="range"
                    min={Math.min(lever.min, value)}
                    max={Math.max(lever.max, value)}
                    step={lever.step}
                    value={value}
                    onChange={(e) => setLevers({ ...levers, [lever.key]: Number(e.target.value) })}
                    className="h-6 w-full accent-[#F2A93B]"
                  />
                </div>
              );
            })}
            {modelled.map((option) => (
              <Button
                key={option.name}
                size="sm"
                variant="outline"
                className="h-auto min-h-9 whitespace-normal py-1 text-left"
                onClick={() => setLevers({ ...NEUTRAL, spend_change_monthly: option.monthly, one_off_cost: option.one_off })}
              >
                Try: {option.name}
              </Button>
            ))}
            <Button size="sm" variant="ghost" disabled={!changed} onClick={() => setLevers(NEUTRAL)}>
              Reset levers
            </Button>
          </div>
        </div>
      </Section>
      {fan ? (
        <Section
          title={
            <>
              Monte Carlo · <span className="num">{fan.runs.toLocaleString("en-US")}</span> runs
            </>
          }
          aside={<Legend items={[{ color: SCENARIO, label: "P50" }, { color: "#F2A93B66", label: "P10 to P90 runway range" }]} />}
        >
          <div data-testid="monte-carlo">
            <FanChart result={fan} currency={scenario?.currency ?? "USD"} />
            <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
              <Tile label="Runway P10" value={runway(fan.runway_p10)} />
              <Tile label="Runway P50" value={runway(fan.runway_p50)} />
              <Tile label="Runway P90" value={runway(fan.runway_p90)} />
              <Tile
                label="Chance of running out of cash within 12 months"
                value={`${(fan.probability_cash_out_within_12_months * 100).toFixed(0)}%`}
              />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <AssumptionTag />
              <span>{fan.runway_label}</span>
              <LineageChip lineage={fan.lineage} label="Simulation formula" />
            </div>
          </div>
        </Section>
      ) : null}
    </>
  );
}
