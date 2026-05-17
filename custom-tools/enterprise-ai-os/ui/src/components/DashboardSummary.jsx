import { useEffect, useState } from "react";
import { fetchSummary } from "../api";

export default function DashboardSummary() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchSummary({ signal: controller.signal })
      .then(setSummary)
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });

    return () => controller.abort();
  }, []);

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px", marginBottom: "16px" }}>
      <h2>Platform Summary</h2>
      {error && <p role="alert">{error}</p>}
      {!error && !summary && <p>Loading summary...</p>}
      {summary && (
        <>
          <p>Total Traces: {summary.total_traces}</p>
          <p>Total Reports: {summary.total_reports}</p>
          <p>Open Incidents: {summary.open_incidents}</p>
          <p>Governance Events: {summary.governance_events}</p>
        </>
      )}
    </section>
  );
}
