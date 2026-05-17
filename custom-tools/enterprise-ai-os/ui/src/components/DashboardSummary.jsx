import { useEffect, useState } from "react";
import { fetchSummary } from "../api";

export default function DashboardSummary() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    fetchSummary().then(setSummary);
  }, []);

  if (!summary) return <p>Loading summary...</p>;

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px", marginBottom: "16px" }}>
      <h2>Platform Summary</h2>
      <p>Total Traces: {summary.total_traces}</p>
      <p>Total Reports: {summary.total_reports}</p>
      <p>Open Incidents: {summary.open_incidents}</p>
      <p>Governance Events: {summary.governance_events}</p>
    </section>
  );
}
