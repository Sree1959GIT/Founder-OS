import { ArrowRight, Check, Lock } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Face, memberOf, TEAM, WELCOME_TEAM } from "@/components/boardroom/faces";
import { KpiRow } from "@/components/canvas/Canvas";
import { MicButton } from "@/components/chat/VoiceControls";
import { Button } from "@/components/ui/button";
import type { HealthState } from "@/hooks/useHealth";
import { unlockAudio } from "@/lib/audioUnlock";
import { useVoice } from "@/lib/voiceContext";
import { tableTopic } from "@/lib/format";
import { useWorkspace, type RunView } from "@/lib/workspace";
import { cn } from "@/lib/utils";

const EXAMPLES = ["Should we open a Dubai office?", "Can we afford two more engineers this year?", "Should we raise our prices by 10%?"];

const STEPS = [
  { n: "1", title: "You ask", text: "Type or say the decision on your mind, in your own words." },
  { n: "2", title: "Your team debates", text: "Six advisors read your numbers and notes, argue it out and check each other." },
  { n: "3", title: "You get a clear choice", text: "Options with costs and risks, one proposal, and a memo you can keep." },
];

/** The small chip that says which AI the team uses (founder F6): a verified key, or Qwen on our server. */
export function KeyChip({ health }: { health: HealthState }) {
  const cloud = health.kind === "ready" ? health.data.dependencies.find((d) => d.name === "cloud") : undefined;
  const model = cloud?.info["ai_model"] as { text?: string; verified?: boolean } | null | undefined;
  const on = cloud?.info["cloud_allowed"] === true && cloud?.info["cloud_usable"] !== false && Boolean(model?.text);
  return (
    <a
      href="#/settings"
      className="inline-flex min-h-[36px] items-center gap-1.5 rounded-full border border-border-strong bg-card px-3 text-xs font-medium text-foreground hover:no-underline"
      data-testid="key-chip"
    >
      {on ? <Check aria-hidden="true" className="h-3.5 w-3.5 text-ok" /> : <Lock aria-hidden="true" className="h-3.5 w-3.5 text-ok" />}
      {on ? `Key verified · ${model?.text}` : "Private · Qwen on our server"}
    </a>
  );
}

const openTopic = (run: RunView) => tableTopic({ message: run.message, subject: run.frame?.subject }, null);

export function Welcome({ health }: { health: HealthState }) {
  const { send, state, decisionRun, enter } = useWorkspace();
  const voice = useVoice();
  const [text, setText] = useState("");
  const [depth, setDepth] = useState<"quick" | "thorough">("thorough");

  const call = (question: string) => {
    const q = question.trim();
    if (!q) return;
    unlockAudio(); // iPhone Safari: the first tap unlocks sound for the Advisor's voice
    setText("");
    void send(q);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    call(text);
  };

  return (
    <main className="theme-cream flex min-h-[calc(100vh-61px)] w-full flex-col bg-background text-foreground" data-testid="welcome">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-14 px-4 pb-20 pt-8 sm:px-8 md:pt-14">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {decisionRun ? (
            // Founder F22: an unfinished decision is offered in one line; it is never reopened by itself.
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-full border border-border bg-card py-1 pl-4 pr-1 text-[14px]" data-testid="open-decision">
              <span>
                You have an open decision: <strong className="font-semibold">{openTopic(decisionRun)}</strong>.
              </span>
              <a
                href="#/boardroom"
                onClick={enter}
                className="inline-flex min-h-[40px] items-center gap-1 rounded-full bg-ink px-4 text-[13px] font-semibold text-paper hover:no-underline"
              >
                Continue it?
                <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
              </a>
            </p>
          ) : (
            <span />
          )}
          <KeyChip health={health} />
        </div>

        <section className="rise flex flex-col gap-6" aria-labelledby="welcome-title">
          <h1 id="welcome-title" className="display max-w-5xl text-[44px] leading-[1.02] sm:text-[64px] lg:text-[84px]">
            Ask a hard question. Six AI advisors argue it out. <em className="not-italic text-signal-soft">You decide.</em>
          </h1>
          <p className="max-w-2xl text-[17px] leading-relaxed text-muted-foreground sm:text-[19px]">
            They read your own numbers, check each other's work, and give you clear options with costs and risks. In about
            four minutes.
          </p>

          <form
            onSubmit={submit}
            className="flex flex-col gap-3 rounded-[22px] border border-border bg-card p-3 shadow-[0_18px_40px_-24px_rgba(20,20,20,0.35)] sm:flex-row sm:items-center"
          >
            <label htmlFor="welcome-ask" className="sr-only">
              What are you deciding?
            </label>
            <input
              id="welcome-ask"
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="What are you deciding?"
              autoComplete="off"
              className="h-14 min-w-0 flex-1 rounded-xl bg-transparent px-4 text-[18px] text-foreground placeholder:text-muted-foreground focus-visible:ring-offset-card"
            />
            <div className="flex items-center gap-2">
              <MicButton big label={voice.on ? undefined : "Talk"} />
              <Button type="submit" disabled={!text.trim() || state.sending} className="h-14 flex-1 gap-2 rounded-full px-6 text-base font-semibold sm:flex-none">
                Call the team
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </Button>
            </div>
          </form>
          {voice.error ? (
            <p role="alert" className="text-sm text-danger">
              {voice.error}
            </p>
          ) : null}

          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <ul className="flex flex-wrap gap-2" aria-label="Example questions">
              {EXAMPLES.map((q) => (
                <li key={q}>
                  <button
                    type="button"
                    onClick={() => call(q)}
                    className="min-h-[44px] rounded-full border border-border-strong bg-card px-4 text-sm text-foreground hover:bg-accent"
                  >
                    {q}
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex flex-col items-start gap-1 sm:items-end">
              <div role="group" aria-label="How deep" className="inline-flex rounded-full border border-border-strong bg-card p-1">
                {(["quick", "thorough"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={depth === d}
                    onClick={() => setDepth(d)}
                    className={cn(
                      "min-h-[40px] whitespace-nowrap rounded-full px-4 text-sm",
                      depth === d ? "bg-ink font-semibold text-paper" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {d === "quick" ? "Quick · ~1 min" : "Thorough · ~4 min"}
                  </button>
                ))}
              </div>
              {depth === "quick" ? (
                <p className="text-xs text-muted-foreground">Quick arrives in a coming update. Today every team is thorough.</p>
              ) : null}
            </div>
          </div>
        </section>

        <section aria-labelledby="how-title" className="flex flex-col gap-5">
          <h2 id="how-title" className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            How it works
          </h2>
          <ol className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {STEPS.map((step) => (
              <li key={step.n} className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-5">
                <span className="display text-[40px] leading-none text-signal-soft">{step.n}</span>
                <span className="text-[17px] font-semibold">{step.title}</span>
                <span className="text-sm leading-relaxed text-muted-foreground">{step.text}</span>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="team-title" className="flex flex-col gap-5">
          <h2 id="team-title" className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Meet your team
          </h2>
          <ul className="flex snap-x gap-3 overflow-x-auto pb-2 md:grid md:grid-cols-7 md:overflow-visible" data-testid="meet-team">
            {["advisor", ...WELCOME_TEAM].map((type) => (
              <li key={type} className="flex w-[150px] shrink-0 snap-start flex-col items-center gap-2 rounded-2xl border border-border bg-card p-4 text-center md:w-auto">
                <span className="rounded-full bg-ink p-2">
                  <Face type={type} size={52} />
                </span>
                <span className="text-sm font-semibold">{memberOf(type).name}</span>
                <span className="text-xs leading-snug text-muted-foreground">{TEAM[type]?.role}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="numbers-title" className="flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="numbers-title" className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Your numbers today
            </h2>
            <a href="#/boardroom" className="inline-flex min-h-[44px] items-center text-sm">
              Try what-ifs in the Boardroom →
            </a>
          </div>
          <KpiRow refreshKey="welcome" />
        </section>
      </div>
    </main>
  );
}
