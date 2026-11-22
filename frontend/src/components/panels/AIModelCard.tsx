import { KeyRound } from "lucide-react";
import { useEffect, useState } from "react";

import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  fetchAIModel,
  removeAIModelKey,
  switchToLocalAIModel,
  testAIModel,
  type AIModelPreset,
  type AIModelView,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const inputClass =
  "h-10 w-full rounded-lg border border-border-strong bg-background px-2 text-sm disabled:opacity-60 placeholder:text-muted-foreground";

/** The fluorescent-green chip: only shown when the backend says the key passed its test. */
export function VerifiedChip({
  label,
  model,
}: {
  label: string;
  model: string;
}) {
  return (
    <span
      data-testid="ai-model-verified"
      className="inline-flex items-center gap-1.5 rounded-full border border-[#39FF14] bg-[#39FF14] px-3 py-1 text-xs font-semibold text-[#06210A] shadow-[0_0_12px_rgba(57,255,20,0.55)]"
    >
      {label} · {model} · key verified
    </span>
  );
}

function presetById(view: AIModelView, id: string): AIModelPreset | undefined {
  return view.presets.find((p) => p.id === id) ?? view.presets[0];
}

/**
 * Settings → AI model (M7a). Its buttons act at once and do not wait for the page's Save: a key is only ever kept once
 * "Test key" has passed, and "Use Qwen" / "Remove key" are safe in both directions.
 */
export function AIModelCard({ onChanged }: { onChanged?: () => void }) {
  const [view, setView] = useState<AIModelView | null>(null);
  const [presetId, setPresetId] = useState("qwen_local");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<null | "test" | "local" | "remove">(null);
  const [failure, setFailure] = useState<string | null>(null);

  const pick = (v: AIModelView, id: string) => {
    const preset = presetById(v, id);
    if (!preset) return;
    setPresetId(preset.id);
    const saved = v.saved?.preset === preset.id ? v.saved : null;
    setModel(saved?.model || preset.default_model);
    setBaseUrl(saved?.base_url || preset.base_url);
    setApiKey("");
    setFailure(null);
  };

  useEffect(() => {
    fetchAIModel()
      .then((v) => {
        setView(v);
        pick(
          v,
          v.in_use.verified
            ? v.in_use.preset
            : (v.saved?.preset ?? v.in_use.preset),
        );
      })
      .catch((err: unknown) =>
        setFailure(
          err instanceof Error ? err.message : "The AI model could not be read",
        ),
      );
  }, []);

  if (!view) {
    return failure ? <ErrorNote>{failure}</ErrorNote> : null;
  }

  const preset = presetById(view, presetId);
  if (!preset) return null;
  const verified = view.in_use.verified;
  const savedHere =
    view.saved && view.saved.preset === preset.id && !view.saved.unreadable
      ? view.saved
      : null;

  const run = async (kind: "test" | "local" | "remove") => {
    setBusy(kind);
    setFailure(null);
    try {
      if (kind === "test") {
        const result = await testAIModel({
          preset: preset.id,
          model: model.trim(),
          base_url: baseUrl.trim(),
          api_key: apiKey.trim(),
        });
        setView(result.view);
        if (result.ok) setApiKey("");
        else setFailure(result.message);
      } else {
        const next =
          kind === "local"
            ? await switchToLocalAIModel()
            : await removeAIModelKey();
        setView(next);
        if (kind === "remove") pick(next, "qwen_local");
      }
      onChanged?.();
    } catch (err) {
      setFailure(
        err instanceof Error ? err.message : "That did not work. Try again.",
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <section
      data-testid="ai-model-card"
      data-state={verified ? "verified" : "grey"}
      className={cn(
        "rounded-2xl border p-4 transition-colors",
        verified
          ? "border-[#39FF14]/60 bg-card"
          : "border-border bg-[#16171A] text-foreground/90",
      )}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">AI model</h2>
        {verified ? (
          <VerifiedChip label={view.in_use.label} model={view.in_use.model} />
        ) : (
          <span
            className="inline-flex items-center rounded-full border border-border-strong px-3 py-1 text-xs text-muted-foreground"
            data-testid="ai-model-local"
          >
            In use: Qwen on our server · {view.in_use.model}
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        The deep-work agents (risks, market, memo) use this model. If it fails
        or this month&apos;s cost cap is reached, Qwen answers instead. The
        privacy filter still applies, and voice always stays on our server. API
        keys only: subscription sign-ins (Claude Pro or Max, Google AI Pro or
        Ultra, ChatGPT) cannot be used here.
      </p>
      {view.secret_problem ? (
        <ErrorNote>{view.secret_problem}</ErrorNote>
      ) : null}
      {view.cloud_paused ? (
        <p
          className="mb-3 rounded-lg border border-[#4A3A1C] bg-[#1A1610] px-3 py-2 text-xs"
          role="status"
        >
          Paused: &quot;Allow cloud agents&quot; is off, so Qwen answers. Turn
          it on and Save to use {view.in_use.label}.
        </p>
      ) : null}
      {view.saved?.unreadable ? (
        <p className="mb-3 text-xs text-danger" role="status">
          Your saved {view.saved.label} key can no longer be read (the server
          secret changed). Enter it again and test it.
        </p>
      ) : null}

      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="ai-preset" className="text-[13px]">
            Model provider
          </label>
          <select
            id="ai-preset"
            className={inputClass}
            value={preset.id}
            onChange={(e) => pick(view, e.target.value)}
          >
            {view.presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </div>

        {preset.needs_key ? (
          <>
            <div className="flex flex-col gap-1">
              <label htmlFor="ai-model" className="text-[13px]">
                Model
              </label>
              <input
                id="ai-model"
                className={inputClass}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={preset.default_model || "model name"}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="ai-base-url" className="text-[13px]">
                Server address
              </label>
              <input
                id="ai-base-url"
                className={inputClass}
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                disabled={!preset.custom_base_url}
                placeholder="https://api.example.com/v1"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label
                htmlFor="ai-key"
                className="flex items-center gap-1.5 text-[13px]"
              >
                <KeyRound aria-hidden="true" className="h-3.5 w-3.5" /> API key
              </label>
              <input
                id="ai-key"
                type="password"
                autoComplete="off"
                spellCheck={false}
                className={inputClass}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  savedHere
                    ? `Saved key ${savedHere.key_masked}: leave empty to test it again`
                    : "Paste your API key"
                }
              />
              <p className="text-xs text-muted-foreground">
                Get one at {preset.key_hint}. It is kept encrypted, only after
                the test passes, and never shown again.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => void run("test")} disabled={busy !== null}>
                {busy === "test"
                  ? `Testing… (up to ${view.test_timeout_s} s)`
                  : "Test key"}
              </Button>
              {view.saved ? (
                <Button
                  variant="outline"
                  onClick={() => void run("remove")}
                  disabled={busy !== null}
                >
                  Remove key
                </Button>
              ) : null}
              {view.saved && !view.saved.unreadable ? (
                <span
                  className="text-xs text-muted-foreground"
                  data-testid="ai-model-saved"
                >
                  Saved: {view.saved.label} · {view.saved.model} ·{" "}
                  {view.saved.key_masked}
                  {verified ? "" : " (not in use)"}
                </span>
              ) : null}
            </div>
          </>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {verified ? (
              <Button
                variant="outline"
                onClick={() => void run("local")}
                disabled={busy !== null}
              >
                Use Qwen
              </Button>
            ) : (
              <p className="text-xs text-muted-foreground">
                Qwen is in use: free and private, slower than the cloud models.
              </p>
            )}
            {view.saved ? (
              <Button
                variant="outline"
                onClick={() => void run("remove")}
                disabled={busy !== null}
              >
                Remove key
              </Button>
            ) : null}
          </div>
        )}
        {failure ? <ErrorNote>{failure}</ErrorNote> : null}
      </div>
    </section>
  );
}
