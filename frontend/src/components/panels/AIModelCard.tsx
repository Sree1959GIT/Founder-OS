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

/** F3: the provider a key belongs to, from its prefix (the backend's table, most specific first). */
function detectPreset(view: AIModelView, key: string): string | null {
  const k = key.trim();
  if (!k) return null;
  return view.key_shapes.find((s) => k.startsWith(s.prefix))?.preset ?? null;
}

/**
 * F2: masked by CSS (`.secret-field`), not `type="password"`, so browser password managers (Chrome, Edge, Safari) do
 * not offer to save it. Only a browser without `-webkit-text-security` falls back to a password field, so it still
 * never shows the key in clear.
 */
function cssMaskWorks(): boolean {
  if (typeof CSS === "undefined" || typeof CSS.supports !== "function")
    return true;
  return CSS.supports("-webkit-text-security", "disc");
}

/**
 * Settings → AI model (M7a; key-only setup after the founder's F3). Paste a key and press Test key: the provider is
 * found from the key's shape, the backend asks it which models the key can use and picks the best one. The provider
 * list stays as a manual override, "Change model" offers the models the key has. The buttons act at once and do not
 * wait for the page's Save: a key is only ever kept once "Test key" has passed.
 */
export function AIModelCard({ onChanged }: { onChanged?: () => void }) {
  const [view, setView] = useState<AIModelView | null>(null);
  const [presetId, setPresetId] = useState("qwen_local");
  const [manual, setManual] = useState(false); // the member picked the provider: the key's shape no longer overrides
  const [customModel, setCustomModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<null | "test" | "local" | "remove">(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [masked] = useState(cssMaskWorks);

  const pick = (v: AIModelView, id: string, byHand: boolean) => {
    const preset = presetById(v, id);
    if (!preset) return;
    setPresetId(preset.id);
    setManual(byHand && preset.needs_key);
    const saved = v.saved?.preset === preset.id ? v.saved : null;
    setCustomModel(preset.custom_base_url ? (saved?.model ?? "") : "");
    setBaseUrl(saved?.base_url || preset.base_url);
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
          false,
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
  const detected = detectPreset(view, apiKey);
  const detectedPreset = detected ? presetById(view, detected) : undefined;
  const savedHere =
    view.saved && view.saved.preset === preset.id && !view.saved.unreadable
      ? view.saved
      : null;
  const models = savedHere?.models ?? [];
  const keyPreset = preset.needs_key ? preset : detectedPreset;

  const onKey = (value: string) => {
    setApiKey(value);
    setFailure(null);
    const found = detectPreset(view, value);
    if (found && !manual && found !== presetId) pick(view, found, false);
  };

  const run = async (
    kind: "test" | "local" | "remove",
    changeModel?: string,
  ) => {
    setBusy(kind);
    setFailure(null);
    try {
      if (kind === "test") {
        // Qwen in the list and a key that matches no known shape: the backend says to pick the provider.
        const target = preset.needs_key ? preset.id : (detected ?? "");
        const result = await testAIModel({
          preset: target,
          model:
            changeModel ?? (preset.custom_base_url ? customModel.trim() : ""),
          base_url: preset.custom_base_url ? baseUrl.trim() : "",
          api_key: changeModel ? "" : apiKey.trim(),
        });
        setView(result.view);
        if (result.ok) {
          setApiKey("");
          if (result.preset) pick(result.view, result.preset, manual);
        } else setFailure(result.message);
      } else {
        const next =
          kind === "local"
            ? await switchToLocalAIModel()
            : await removeAIModelKey();
        setView(next);
        if (kind === "remove") pick(next, "qwen_local", false);
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

  const testable = preset.needs_key || apiKey.trim() !== "" || busy !== null;

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

      {/* F2: no <form> (nothing is submitted, so no "save password?" prompt), and no password field. */}
      <div className="flex flex-col gap-3" role="group" aria-label="AI model">
        <div className="flex flex-col gap-1">
          <label
            htmlFor="ai-key"
            className="flex items-center gap-1.5 text-[13px]"
          >
            <KeyRound aria-hidden="true" className="h-3.5 w-3.5" /> API key
          </label>
          <input
            id="ai-key"
            name="founderos-ai-key"
            type={masked ? "text" : "password"}
            className={cn(inputClass, masked && "secret-field")}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            inputMode="text"
            data-lpignore="true"
            data-1p-ignore="true"
            data-bwignore="true"
            data-form-type="other"
            data-gramm="false"
            data-testid="ai-key"
            value={apiKey}
            onChange={(e) => onKey(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && testable) {
                e.preventDefault();
                void run("test");
              }
            }}
            placeholder={
              savedHere
                ? `Saved key ${savedHere.key_masked}: leave empty to test it again`
                : "Paste your API key"
            }
          />
          <p
            className="text-xs text-muted-foreground"
            data-testid="ai-key-hint"
          >
            {detectedPreset && apiKey.trim()
              ? `Looks like a ${detectedPreset.label} key. Press Test key: FounderOS finds the best model this key can use.`
              : keyPreset
                ? `Get one at ${keyPreset.key_hint}. Kept encrypted, only after the test passes, and never shown again.`
                : "Paste a Claude, Gemini, OpenAI, OpenRouter or Groq key: the provider and the model are found for you."}
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="ai-preset" className="text-[13px]">
            Model provider
          </label>
          <select
            id="ai-preset"
            className={inputClass}
            value={preset.id}
            onChange={(e) => pick(view, e.target.value, true)}
          >
            {view.presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
          {preset.needs_key && !manual && detected === preset.id ? (
            <p className="text-xs text-muted-foreground">
              Found from the key. Pick another provider here if that is wrong.
            </p>
          ) : null}
        </div>

        {savedHere && models.length > 0 && verified ? (
          <div className="flex flex-col gap-1">
            <label htmlFor="ai-change-model" className="text-[13px]">
              Change model (optional)
            </label>
            <select
              id="ai-change-model"
              className={inputClass}
              value={view.in_use.model}
              disabled={busy !== null}
              onChange={(e) => void run("test", e.target.value)}
            >
              {models.some((m) => m.id === view.in_use.model) ? null : (
                <option value={view.in_use.model}>{view.in_use.model}</option>
              )}
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label && m.label !== m.id ? `${m.label} (${m.id})` : m.id}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {preset.custom_base_url ? (
          <details open className="rounded-lg border border-border px-3 py-2">
            <summary className="cursor-pointer text-[13px]">Advanced</summary>
            <div className="mt-2 flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <label htmlFor="ai-base-url" className="text-[13px]">
                  Server address
                </label>
                <input
                  id="ai-base-url"
                  className={inputClass}
                  value={baseUrl}
                  autoComplete="off"
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.example.com/v1"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="ai-custom-model" className="text-[13px]">
                  Model name (only if the server lists none)
                </label>
                <input
                  id="ai-custom-model"
                  className={inputClass}
                  value={customModel}
                  autoComplete="off"
                  onChange={(e) => setCustomModel(e.target.value)}
                  placeholder="found from the server when empty"
                />
              </div>
            </div>
          </details>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          {testable ? (
            <Button
              type="button"
              onClick={() => void run("test")}
              disabled={busy !== null}
            >
              {busy === "test"
                ? `Testing… (up to ${view.test_timeout_s} s)`
                : "Test key"}
            </Button>
          ) : null}
          {!preset.needs_key && verified ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => void run("local")}
              disabled={busy !== null}
            >
              Use Qwen
            </Button>
          ) : null}
          {view.saved ? (
            <Button
              type="button"
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
        {!preset.needs_key && !verified && !apiKey.trim() ? (
          <p className="text-xs text-muted-foreground">
            Qwen is in use: free and private, slower than the cloud models.
          </p>
        ) : null}
        {failure ? <ErrorNote>{failure}</ErrorNote> : null}
      </div>
    </section>
  );
}
