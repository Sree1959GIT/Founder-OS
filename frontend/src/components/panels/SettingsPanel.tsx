import { ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ErrorNote, Pill, Section } from "@/components/common";
import { Button } from "@/components/ui/button";
import { leaveTo, setNavigationGuard } from "@/hooks/useRoute";
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

/** The settings a founder edits. Nothing here is applied, cloud included, until Save (founder review 36). */
const EDITABLE = [
  "cloud_allowed",
  "deep_provider",
  "agent_models",
  "cloud_monthly_cap_usd",
  "team_approval",
  "max_local_agents",
  "max_cloud_agents",
] as const;
type Editable = Pick<SettingsView, (typeof EDITABLE)[number]>;

function changedSettings(saved: SettingsView, draft: SettingsView): Partial<Editable> {
  const out: Record<string, unknown> = {};
  EDITABLE.forEach((key) => {
    if (JSON.stringify(saved[key]) !== JSON.stringify(draft[key])) out[key] = draft[key];
  });
  return out as Partial<Editable>;
}

export function SettingsPanel() {
  const [saved, setSaved] = useState<SettingsView | null>(null);
  const [view, setView] = useState<SettingsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState(false);
  const [leaving, setLeaving] = useState<string | null>(null);

  useEffect(() => {
    fetchSettings()
      .then((v) => {
        setSaved(v);
        setView(v);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Settings could not be read"));
  }, []);

  const pending = saved && view ? changedSettings(saved, view) : {};
  const dirty = Object.keys(pending).length > 0;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  // Leaving with unsaved changes asks first: another page in the app gets Save / Discard / Stay. Closing or
  // reloading the tab gets the browser's own "Leave site?" prompt: a browser allows no other buttons there.
  useEffect(() => {
    setNavigationGuard((target) => {
      if (!dirtyRef.current) return true;
      setLeaving(target);
      return false;
    });
    const onUnload = (e: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      setNavigationGuard(null);
      window.removeEventListener("beforeunload", onUnload);
    };
  }, []);

  const change = (update: Partial<SettingsView>) => {
    setSavedNote(false);
    setView((v) => (v ? { ...v, ...update } : v));
  };

  const save = useCallback(async (): Promise<boolean> => {
    if (!saved || !view) return false;
    setError(null);
    try {
      const fresh = await putSettings(changedSettings(saved, view));
      setSaved(fresh);
      setView(fresh);
      setSavedNote(true);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "The settings were not saved");
      return false;
    }
  }, [saved, view]);

  const discard = () => {
    setView(saved);
    setSavedNote(false);
  };

  if (!view) {
    return <main className="flex-1 px-6 py-5">{error ? <ErrorNote>{error}</ErrorNote> : null}</main>;
  }

  const configured = view.providers.filter((p) => p.configured);
  const spent = view.spend.spent_usd;
  const setRoute = (type: string, value: string) => {
    const others = Object.entries(view.agent_models).filter(([key]) => key !== type);
    change({ agent_models: Object.fromEntries(value ? [...others, [type, value]] : others) });
  };

  return (
    <main className="flex min-w-0 flex-1 flex-col gap-4 px-6 py-5">
      <h1 className="text-[22px] font-bold tracking-tight">Settings</h1>
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {dirty ? (
        <div
          className="sticky top-2 z-30 flex flex-wrap items-center gap-2 rounded-xl border border-[#4A3A1C] bg-[#1A1610] p-3 text-[13px]"
          data-testid="unsaved"
          role="status"
        >
          <span className="flex-1 font-medium">You have unsaved changes. Nothing changes until you save.</span>
          <Button onClick={() => void save()}>Save</Button>
          <Button variant="outline" onClick={discard}>
            Discard
          </Button>
        </div>
      ) : savedNote ? (
        <p className="text-[13px] text-ok" role="status">
          Saved.
        </p>
      ) : null}
      {leaving !== null ? (
        <div role="alertdialog" aria-label="Save your changes?" className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
          <div className="flex w-full max-w-sm flex-col gap-3 rounded-2xl border border-border-strong bg-panel p-4">
            <p className="text-[15px] font-semibold">Save your changes?</p>
            <p className="text-[13px] text-muted-foreground">Your settings have changes that are not saved yet.</p>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => {
                  const target = leaving;
                  void save().then((ok) => {
                    setLeaving(null);
                    if (ok) leaveTo(target);
                  });
                }}
              >
                Save
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  const target = leaving;
                  discard();
                  setLeaving(null);
                  leaveTo(target);
                }}
              >
                Discard
              </Button>
              <Button variant="ghost" onClick={() => setLeaving(null)}>
                Stay
              </Button>
            </div>
          </div>
        </div>
      ) : null}
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
                onChange={(e) => change({ cloud_allowed: e.target.checked })}
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
                onChange={(e) => change({ deep_provider: e.target.value })}
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
                    {p.name}: {p.name === "ollama" ? "local" : p.configured ? "key set" : "no key"}
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
              onCommit={(v) => change({ cloud_monthly_cap_usd: v })}
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
                onChange={(e) => change({ team_approval: e.target.value as SettingsView["team_approval"] })}
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
              onCommit={(v) => change({ max_local_agents: v })}
            />
            {view.cloud_allowed ? (
              <NumberField
                id="cloud-slots"
                label="Cloud agents at once"
                value={view.max_cloud_agents}
                min={1}
                max={32}
                step={1}
                onCommit={(v) => change({ max_cloud_agents: v })}
              />
            ) : null}
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
