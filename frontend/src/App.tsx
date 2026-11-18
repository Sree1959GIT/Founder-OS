import { useCallback, useState } from "react";

import { AgentActivity } from "@/components/activity/AgentActivity";
import { AgentRail } from "@/components/activity/AgentRail";
import { AgentWindow } from "@/components/activity/AgentWindow";
import { Canvas } from "@/components/canvas/Canvas";
import { AdvisorPanel } from "@/components/chat/AdvisorPanel";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import { TopBar } from "@/components/layout/TopBar";
import { MemoView } from "@/components/memo/MemoView";
import { DataPanel } from "@/components/panels/DataPanel";
import { SettingsPanel } from "@/components/panels/SettingsPanel";
import { VaultPanel } from "@/components/panels/VaultPanel";
import { useHealth } from "@/hooks/useHealth";
import { useRoute } from "@/hooks/useRoute";
import { LEFT, maxWidth, RIGHT, usePanelLayout, viewportWidth } from "@/lib/layout";
import { WorkspaceProvider } from "@/lib/workspace";

function Workspace({ agentsOpen, toggleAgents }: { agentsOpen: boolean; toggleAgents: () => void }) {
  const { layout, setWidth, reset, toggleLeft } = usePanelLayout();
  const vw = viewportWidth();
  return (
    <>
      <AdvisorPanel
        width={layout.left}
        collapsed={layout.leftCollapsed}
        onToggle={toggleLeft}
        onAgents={toggleAgents}
        agentsOpen={agentsOpen}
      />
      {layout.leftCollapsed ? null : (
        <ResizeHandle
          side="left"
          label="Advisor panel width"
          width={layout.left}
          min={LEFT.min}
          max={maxWidth("left", layout, vw)}
          onResize={(w) => setWidth("left", w)}
          onReset={() => reset("left")}
        />
      )}
      <Canvas />
      <ResizeHandle
        side="right"
        label="Agents panel width"
        width={layout.right}
        min={RIGHT.min}
        max={maxWidth("right", layout, vw)}
        onResize={(w) => setWidth("right", w)}
        onReset={() => reset("right")}
        className="md:hidden xl:block"
      />
      <AgentRail width={layout.right} />
    </>
  );
}

function Body({ agentsOpen, toggleAgents }: { agentsOpen: boolean; toggleAgents: () => void }) {
  const route = useRoute();
  switch (route.view) {
    case "activity":
      return <AgentActivity />;
    case "memo":
      return <MemoView path={route.path} />;
    case "data":
      return <DataPanel />;
    case "vault":
      return <VaultPanel path={route.path} />;
    case "settings":
      return <SettingsPanel />;
    default:
      return <Workspace agentsOpen={agentsOpen} toggleAgents={toggleAgents} />;
  }
}

export default function App() {
  const health = useHealth();
  const route = useRoute();
  // The agent window stays open across views, so it can watch a run while the founder reads a memo.
  const [agentsOpen, setAgentsOpen] = useState(false);
  const toggleAgents = useCallback(() => setAgentsOpen((open) => !open), []);
  const closeAgents = useCallback(() => setAgentsOpen(false), []);
  return (
    <WorkspaceProvider>
      <div className="flex min-h-full flex-col">
        <TopBar health={health} view={route.view} />
        <div className="flex flex-1 flex-wrap items-stretch md:flex-nowrap">
          <Body agentsOpen={agentsOpen} toggleAgents={toggleAgents} />
        </div>
      </div>
      {agentsOpen ? <AgentWindow onClose={closeAgents} /> : null}
    </WorkspaceProvider>
  );
}
