import { Mic } from "lucide-react";

import { Button } from "@/components/ui/button";

export function AdvisorPanel() {
  return (
    <aside
      aria-label="Executive Advisor"
      className="flex min-w-0 flex-[1_1_340px] flex-col border-r border-border bg-panel md:max-w-[380px]"
    >
      <div className="flex items-center justify-between px-5 pb-2 pt-4">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Executive Advisor
        </span>
        <span className="text-xs text-muted-foreground">Socratic mode</span>
      </div>
      <div className="flex flex-1 flex-col justify-center gap-2 px-5 py-2 text-muted-foreground">
        <p className="leading-relaxed">
          The advisor will question your ideas and test them against your real numbers.
        </p>
        <p className="text-xs">Conversation arrives in milestone M3a; voice in M5.</p>
      </div>
      <div className="m-4 flex flex-col gap-3 rounded-2xl border border-border-strong bg-card p-3.5">
        <div className="flex items-center gap-2">
          <label htmlFor="ask" className="sr-only">
            Type a question
          </label>
          <input
            id="ask"
            type="text"
            disabled
            placeholder="Type, or just speak..."
            className="h-11 min-w-0 flex-1 rounded-lg border border-border-strong bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-60"
          />
          <Button size="icon" aria-label="Microphone (available in M5)" disabled className="h-11 w-11 rounded-lg">
            <Mic aria-hidden="true" />
          </Button>
        </div>
      </div>
    </aside>
  );
}
