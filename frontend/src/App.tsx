import { AgentActivity } from "@/components/activity/AgentActivity";
import { AgentRail } from "@/components/activity/AgentRail";
import { Canvas } from "@/components/canvas/Canvas";
import { AdvisorPanel } from "@/components/chat/AdvisorPanel";
import { TopBar } from "@/components/layout/TopBar";
import { MemoView } from "@/components/memo/MemoView";
import { DataPanel } from "@/components/panels/DataPanel";
import { SettingsPanel } from "@/components/panels/SettingsPanel";
import { VaultPanel } from "@/components/panels/VaultPanel";
import { useHealth } from "@/hooks/useHealth";
import { useRoute } from "@/hooks/useRoute";
import { WorkspaceProvider } from "@/lib/workspace";

function Body() {
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
      return (
        <>
          <AdvisorPanel />
          <Canvas />
          <AgentRail />
        </>
      );
  }
}

export default function App() {
  const health = useHealth();
  const route = useRoute();
  return (
    <WorkspaceProvider>
      <div className="flex min-h-full flex-col">
        <TopBar health={health} view={route.view} />
        <div className="flex flex-1 flex-wrap items-stretch">
          <Body />
        </div>
      </div>
    </WorkspaceProvider>
  );
}
