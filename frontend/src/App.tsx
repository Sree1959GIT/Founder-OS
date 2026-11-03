import { AdvisorPanel } from "@/components/layout/AdvisorPanel";
import { AgentRail } from "@/components/layout/AgentRail";
import { Canvas } from "@/components/layout/Canvas";
import { TopBar } from "@/components/layout/TopBar";
import { useHealth } from "@/hooks/useHealth";

export default function App() {
  const health = useHealth();
  return (
    <div className="flex min-h-full flex-col">
      <TopBar health={health} />
      <div className="flex flex-1 flex-wrap items-stretch">
        <AdvisorPanel />
        <Canvas />
        <AgentRail />
      </div>
    </div>
  );
}
