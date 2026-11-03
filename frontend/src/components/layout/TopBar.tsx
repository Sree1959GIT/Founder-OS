import { Database, Settings } from "lucide-react";

import { HealthBadge } from "@/components/HealthBadge";
import { Logo } from "@/components/Logo";
import { PrivacyBadge } from "@/components/PrivacyBadge";
import { Button } from "@/components/ui/button";
import type { HealthState } from "@/hooks/useHealth";

export function TopBar({ health }: { health: HealthState }) {
  const workspace = health.kind === "ready" ? health.data.workspace_id : "default";
  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-border bg-panel px-6 py-3">
      <Logo />
      <div className="flex items-center gap-2 rounded-md border border-border-strong bg-card px-3 py-1.5">
        <span className="text-xs text-muted-foreground">Workspace</span>
        <span className="font-semibold">{workspace}</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Database aria-hidden="true" className="h-3.5 w-3.5" />
        No data sources yet
      </div>
      <div className="flex-1" />
      <PrivacyBadge health={health} />
      <HealthBadge health={health} />
      <Button variant="outline" size="icon" aria-label="Settings (available in M4)" disabled>
        <Settings aria-hidden="true" />
      </Button>
    </header>
  );
}
