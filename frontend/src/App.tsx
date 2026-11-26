import { useCallback, useEffect, useState } from "react";

import { AgentActivity } from "@/components/activity/AgentActivity";
import { AgentWindow } from "@/components/activity/AgentWindow";
import { BoardroomStage, OptionsPanel, PhoneBar } from "@/components/boardroom/Boardroom";
import { CanvasCards } from "@/components/canvas/Canvas";
import { AdvisorPanel } from "@/components/chat/AdvisorPanel";
import { VoiceDock } from "@/components/chat/VoiceControls";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import { TopBar } from "@/components/layout/TopBar";
import { MemoView } from "@/components/memo/MemoView";
import { DataPanel } from "@/components/panels/DataPanel";
import { SettingsPanel } from "@/components/panels/SettingsPanel";
import { VaultPanel } from "@/components/panels/VaultPanel";
import { Welcome } from "@/components/welcome/Welcome";
import { useHealth, type HealthState } from "@/hooks/useHealth";
import { useRoute } from "@/hooks/useRoute";
import { fetchSettings, putSettings } from "@/lib/api";
import { browserCurrency, currencyMissing } from "@/lib/currency";
import { LEFT, maxWidth, RIGHT, shownWidths, usePanelLayout, useViewportWidth } from "@/lib/layout";
import { cn } from "@/lib/utils";
import { VoiceProvider } from "@/lib/voiceContext";
import { useWorkspace, WorkspaceProvider } from "@/lib/workspace";

/** The Boardroom (M7b): the Advisor on the left, the table and the decision's cards in the middle, the options on
 * the right. On a phone the table comes first, then the options, then the conversation. */
function Workspace({ agentsOpen, toggleAgents }: { agentsOpen: boolean; toggleAgents: () => void }) {
  const { layout, setWidth, reset, toggleLeft } = usePanelLayout();
  const vw = useViewportWidth();
  const shown = shownWidths(layout, vw);
  return (
    <>
      <div aria-hidden="true" className="glow glow-tomato -left-24 top-24 h-80 w-80" />
      <div aria-hidden="true" className="glow glow-violet -right-24 top-[45%] h-96 w-96" />
      <div className="order-3 flex w-full md:order-none md:w-auto">
        <AdvisorPanel
          width={shown.left}
          collapsed={layout.leftCollapsed}
          onToggle={toggleLeft}
          onAgents={toggleAgents}
          agentsOpen={agentsOpen}
        />
      </div>
      {layout.leftCollapsed ? null : (
        <ResizeHandle
          side="left"
          label="Advisor panel width"
          width={shown.left}
          min={LEFT.min}
          max={maxWidth("left", layout, vw)}
          onResize={(w) => setWidth("left", w)}
          onReset={() => reset("left")}
        />
      )}
      <BoardroomStage>
        <CanvasCards />
      </BoardroomStage>
      <ResizeHandle
        side="right"
        label="Options panel width"
        width={shown.right}
        min={RIGHT.min}
        max={maxWidth("right", layout, vw)}
        onResize={(w) => setWidth("right", w)}
        onReset={() => reset("right")}
        className="md:hidden xl:block"
      />
      <OptionsPanel width={vw >= 1280 ? shown.right : undefined} />
      <PhoneBar />
    </>
  );
}

/** Welcome when nothing is open yet (no question asked in this window, no decision); the Boardroom after. */
function Home({ health, agentsOpen, toggleAgents }: { health: HealthState; agentsOpen: boolean; toggleAgents: () => void }) {
  const { state, decisionRun } = useWorkspace();
  if (state.turns.length === 0 && !decisionRun) return <Welcome health={health} />;
  return <Workspace agentsOpen={agentsOpen} toggleAgents={toggleAgents} />;
}

function Body({ health, agentsOpen, toggleAgents }: { health: HealthState; agentsOpen: boolean; toggleAgents: () => void }) {
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
      return <Home health={health} agentsOpen={agentsOpen} toggleAgents={toggleAgents} />;
  }
}

export default function App() {
  const health = useHealth();
  const route = useRoute();
  // The agent window stays open across views, so it can watch a run while the founder reads a memo.
  const [agentsOpen, setAgentsOpen] = useState(false);
  const toggleAgents = useCallback(() => setAgentsOpen((open) => !open), []);
  const closeAgents = useCallback(() => setAgentsOpen(false), []);
  // Founder F12: until the member picks a currency in Settings, the browser's region decides (silently, once).
  // Founder F12b: `member_currency` is null until chosen (the check for "" never matched, so prices stayed in US$).
  const ready = health.kind === "ready";
  useEffect(() => {
    if (!ready) return;
    fetchSettings()
      .then((s) => (currencyMissing(s.member_currency) ? putSettings({ member_currency: browserCurrency() }) : null))
      .catch(() => undefined);
  }, [ready]);
  return (
    <WorkspaceProvider>
      <VoiceProvider>
        <Shell health={health} view={route.view} agentsOpen={agentsOpen} toggleAgents={toggleAgents} />
        {route.view !== "workspace" ? <VoiceDock /> : null}
      </VoiceProvider>
      {agentsOpen ? <AgentWindow onClose={closeAgents} /> : null}
    </WorkspaceProvider>
  );
}

function Shell({
  health,
  view,
  agentsOpen,
  toggleAgents,
}: {
  health: HealthState;
  view: ReturnType<typeof useRoute>["view"];
  agentsOpen: boolean;
  toggleAgents: () => void;
}) {
  const { state, decisionRun } = useWorkspace();
  const welcome = view === "workspace" && state.turns.length === 0 && !decisionRun;
  return (
    <div className={welcome ? "theme-cream flex min-h-full flex-col bg-background text-foreground" : "flex min-h-full flex-col"}>
      <TopBar health={health} view={view} />
      <div className={cn("relative flex flex-1 flex-wrap items-stretch overflow-x-clip md:flex-nowrap", view === "workspace" && !welcome && "pb-24 md:pb-0")}>
        <Body health={health} agentsOpen={agentsOpen} toggleAgents={toggleAgents} />
      </div>
    </div>
  );
}
