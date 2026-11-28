import { Database, Settings } from "lucide-react";

import { SystemStatus } from "@/components/HealthBadge";
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
    <header className="glass-header print-hide sticky top-0 z-30 flex min-h-[61px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 text-foreground md:static md:px-6 md:py-2.5">
      <Logo />
      <div className="hidden items-center gap-2 rounded-md border border-border-strong bg-card px-3 py-1.5 md:flex">
        <span className="text-xs text-muted-foreground">Workspace</span>
        <span className="font-semibold">{workspace}</span>
      </div>
      <nav aria-label="Main" className="order-last -mx-4 flex w-[calc(100%+32px)] items-center gap-1 overflow-x-auto px-4 md:order-none md:mx-0 md:w-auto md:flex-wrap md:overflow-visible md:px-0">
        {LINKS.map((link) => (
          <a
            key={link.view}
            href={link.href}
            aria-current={view === link.view ? "page" : undefined}
            className={cn(
              "inline-flex h-11 shrink-0 items-center rounded-md px-2.5 text-[13px] hover:bg-accent hover:no-underline md:h-9",
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
      <div className="hidden md:contents">
        <SystemStatus health={health} />
      </div>
      <a
        href="#/settings"
        aria-label="Settings"
        aria-current={view === "settings" ? "page" : undefined}
        className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-border-strong bg-card text-foreground hover:bg-accent"
      >
        <Settings aria-hidden="true" className="h-4 w-4" />
      </a>
    </header>
  );
}
