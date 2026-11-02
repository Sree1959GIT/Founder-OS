import { Cloud, Lock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { HealthState } from "@/hooks/useHealth";

/** "Local only" unless Settings allow cloud for deep-work agents (PRD R2). */
export function PrivacyBadge({ health }: { health: HealthState }) {
  const cloud = health.kind === "ready" ? health.data.dependencies.find((d) => d.name === "cloud") : undefined;
  const cloudAllowed = cloud?.info["cloud_allowed"] === true;
  if (!cloudAllowed) {
    return (
      <Badge variant="ok">
        <Lock aria-hidden="true" className="h-3 w-3" />
        Local only
      </Badge>
    );
  }
  return (
    <Badge variant="signal">
      <Cloud aria-hidden="true" className="h-3 w-3" />
      Local · cloud on approval
    </Badge>
  );
}
