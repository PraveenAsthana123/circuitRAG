import { useEffect, useState } from "react";
import { fetchOpenIncidents } from "../api";

export default function IncidentPanel() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchOpenIncidents({ signal: controller.signal })
      .then((data) => setIncidents(data.incidents || []))
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, []);

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px" }}>
      <h2>Open Incidents</h2>
      {error && <p role="alert">{error}</p>}
      {!error && loading && <p>Loading incidents...</p>}
      {!error && !loading && incidents.length === 0 && <p>No open incidents.</p>}
      {incidents.map((incident, index) => (
        <pre key={index}>{JSON.stringify(incident, null, 2)}</pre>
      ))}
    </section>
  );
}
