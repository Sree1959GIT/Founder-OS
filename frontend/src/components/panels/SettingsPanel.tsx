import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { ErrorNote, Pill, Section } from "@/components/common";
import { fetchSettings, putSettings, type SettingsView } from "@/lib/api";

const selectClass = "h-10 rounded-lg border border-border-strong bg-background px-2 text-sm disabled:opacity-60";

function NumberField({
  id,
  label,
  value,
  min,
  max,
  step,
  onCommit,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onCommit: (value: number) => void;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  return (
    <div className="flex items-center justify-between gap-3">
      <label htmlFor={id} className="text-[13px]">
        {label}
      </label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        step={step}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          const parsed = Number(text);
          if (Number.isFinite(parsed) && parsed >= min && parsed <= max && parsed !== value) onCommit(parsed);
          else setText(String(value));
        }}
        className="num h-10 w-28 rounded-lg border border-border-strong bg-background px-2 text-right text-sm"
      />
    </div>
  );
}

export function SettingsPanel() {
  const [view, setView] = useState<SettingsView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSettings()
      .then(setView)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Settings could not be read"));
  }, []);

  const change = async (update: Partial<SettingsView>) => {
    setError(null);
    try {
      setView(await putSettings(update));
    } catch (err) {
      setError(err instanceof Error ? err.message : "That setting was not saved");
    }
  };

  if (!view) {
    return <main className="flex-1 px-6 py-5">{error ? <ErrorNote>{error}</ErrorNote> : null}</main>;
  }

  const configured = view.providers.filter((p) => p.configured);
  const spent = view.spend.spent_usd;
  const setRoute = (type: string, value: string) => {
    const others = Object.entries(view.agent_models).filter(([key]) => key !== type);
    void change({ agent_models: Object.fromEntries(value ? [...others, [type, value]] : others) });
  };

  return (
    <main className="flex min-w-0 flex-1 flex-col gap-4 px-6 py-5">
      <h1 className="text-[22px] font-bold tracking-tight">Settings</h1>
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      <section className="flex items-start gap-2.5 rounded-2xl border border-[#1F5A45] bg-[#10261E] p-4" data-testid="privacy-note">
        <ShieldCheck aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
        <p className="text-[13px] leading-relaxed text-foreground">{view.privacy_note}</p>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Section title="Cloud">
          <div className="flex flex-col gap-3">
            <label className="flex min-h-10 items-center justify-between gap-3 text-[13px]">
              Allow cloud agents
              <input
                type="checkbox"
                checked={view.cloud_allowed}
                onChange={(e) => void change({ cloud_allowed: e.target.checked })}
                className="h-5 w-5 accent-[#F2A93B]"
              />
            </label>
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="deep-provider" className="text-[13px]">
                Deep-work provider
              </label>
              <select
                id="deep-provider"
                className={selectClass}
                value={view.deep_provider}
                onChange={(e) => void change({ deep_provider: e.target.value })}
              >
                {view.providers.map((p) => (
                  <option key={p.name} value={p.name} disabled={!p.configured}>
                    {p.name}
                    {p.configured ? "" : " (no key)"}
                  </option>
                ))}
              </select>
            </div>
            <ul className="flex flex-wrap gap-1.5" aria-label="Providers">
              {view.providers.map((p) => (
                <li key={p.name}>
                  <Pill tone={p.configured ? "ok" : "neutral"}>
                    {p.name}: {p.configured ? "key set" : "no key"}
                  </Pill>
                </li>
              ))}
            </ul>
            <NumberField
              id="cost-cap"
              label="Monthly cost cap (USD)"
              value={view.cloud_monthly_cap_usd}
              min={0}
              max={100_000}
              step={1}
              onCommit={(v) => void change({ cloud_monthly_cap_usd: v })}
            />
            <p className="text-xs text-muted-foreground">
              Spent this month: <span className="num">{spent === undefined ? "n/a" : `$${spent.toFixed(2)}`}</span>. Over the cap, cloud agents fall back to local.
            </p>
          </div>
        </Section>

        <Section title="Team">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="team-approval" className="text-[13px]">
                Ask before a team runs
              </label>
              <select
                id="team-approval"
                className={selectClass}
                value={view.team_approval}
                onChange={(e) => void change({ team_approval: e.target.value as SettingsView["team_approval"] })}
              >
                <option value="always">Always</option>
                <option value="cloud_only">Only when cloud is used</option>
                <option value="never">Never</option>
              </select>
            </div>
            <NumberField
              id="local-slots"
              label="Local agents at once"
              value={view.max_local_agents}
              min={1}
              max={16}
              step={1}
              onCommit={(v) => void change({ max_local_agents: v })}
            />
            <NumberField
              id="cloud-slots"
              label="Cloud agents at once"
              value={view.max_cloud_agents}
              min={1}
              max={32}
              step={1}
              onCommit={(v) => void change({ max_cloud_agents: v })}
            />
          </div>
        </Section>
      </div>

      <Section title="Provider per agent">
        <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2" data-testid="agent-routes">
          {view.agents.map((agent) => {
            const current = view.agent_models[agent.type] ?? "";
            const locked = agent.privacy === "local";
            const custom = current && !view.providers.some((p) => p.name === current);
            return (
              <li key={agent.type} className="flex items-center gap-3 rounded-lg border border-border bg-background p-2.5">
                <div className="min-w-0 flex-1">
                  <label htmlFor={`route-${agent.type}`} className="block truncate text-[13px] font-medium">
                    {agent.title}
                  </label>
                  <p className="truncate text-xs text-muted-foreground" title={agent.job}>
                    {agent.job}
                  </p>
                </div>
                {locked ? <Pill tone="ok">Local only</Pill> : null}
                <select
                  id={`route-${agent.type}`}
                  className={`${selectClass} w-40`}
                  disabled={locked}
                  value={locked ? "" : current}
                  onChange={(e) => setRoute(agent.type, e.target.value)}
                >
                  <option value="">{locked ? "This PC" : "Default"}</option>
                  {custom ? <option value={current}>{current}</option> : null}
                  {configured.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </li>
            );
          })}
        </ul>
      </Section>
    </main>
  );
}
