import { Database, Settings } from "lucide-react";

import { HealthBadge } from "@/components/HealthBadge";
import { Logo } from "@/components/Logo";
import { PrivacyBadge } from "@/components/PrivacyBadge";
import type { HealthState } from "@/hooks/useHealth";
import type { View } from "@/hooks/useRoute";
import { cn } from "@/lib/utils";

const LINKS: { view: View; href: string; label: string }[] = [
  { view: "workspace", href: "#/", label: "Workspace" },
  { view: "activity", href: "#/activity", label: "Activity" },
  { view: "memo", href: "#/memo", label: "Decisions" },
  { view: "data", href: "#/data", label: "Data" },
  { view: "vault", href: "#/vault", label: "Vault" },
];

export function TopBar({ health, view }: { health: HealthState; view: View }) {
  const workspace = health.kind === "ready" ? health.data.workspace_id : "default";
  return (
    <header className="print-hide flex min-h-[61px] flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-panel px-6 py-2.5">
      <Logo />
      <div className="flex items-center gap-2 rounded-md border border-border-strong bg-card px-3 py-1.5">
        <span className="text-xs text-muted-foreground">Workspace</span>
        <span className="font-semibold">{workspace}</span>
      </div>
      <nav aria-label="Main" className="flex flex-wrap items-center gap-1">
        {LINKS.map((link) => (
          <a
            key={link.view}
            href={link.href}
            aria-current={view === link.view ? "page" : undefined}
            className={cn(
              "inline-flex h-9 items-center rounded-md px-2.5 text-[13px] hover:bg-accent hover:no-underline",
              view === link.view ? "bg-accent font-medium text-foreground" : "text-muted-foreground",
            )}
          >
            {link.view === "data" ? <Database aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" /> : null}
            {link.label}
          </a>
        ))}
      </nav>
      <div className="flex-1" />
      <PrivacyBadge health={health} />
      <HealthBadge health={health} />
      <a
        href="#/settings"
        aria-label="Settings"
        aria-current={view === "settings" ? "page" : undefined}
        className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-border-strong bg-card text-foreground hover:bg-accent"
      >
        <Settings aria-hidden="true" className="h-4 w-4" />
      </a>
    </header>
  );
}
