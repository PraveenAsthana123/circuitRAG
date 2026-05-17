import DashboardSummary from "./components/DashboardSummary";
import AgentGraph from "./components/AgentGraph";
import TraceViewer from "./components/TraceViewer";
import GovernancePanel from "./components/GovernancePanel";
import CostPanel from "./components/CostPanel";
import IncidentPanel from "./components/IncidentPanel";

export default function App() {
  return (
    <main style={{ padding: "24px", fontFamily: "Arial" }}>
      <h1>Enterprise AI-OS Command Center</h1>

      <DashboardSummary />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
        <AgentGraph />
        <TraceViewer />
        <GovernancePanel />
        <CostPanel />
        <IncidentPanel />
      </div>
    </main>
  );
}
