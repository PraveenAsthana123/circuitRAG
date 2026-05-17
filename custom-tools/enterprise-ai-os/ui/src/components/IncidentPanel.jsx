// ⚠️ STUB — imported by App.jsx but NO source was provided in Tool Set
//     31. Replace with operator source. See ../../TRUNCATED.md.

import { useEffect, useState } from "react";
import { fetchOpenIncidents } from "../api";

export default function IncidentPanel() {
  const [incidents, setIncidents] = useState([]);

  useEffect(() => {
    fetchOpenIncidents()
      .then((data) => setIncidents(data.incidents || []))
      .catch(() => setIncidents([]));
  }, []);

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px" }}>
      <h2>Open Incidents</h2>
      {incidents.length === 0 && <p>No open incidents.</p>}
      {incidents.map((incident, index) => (
        <pre key={index}>{JSON.stringify(incident, null, 2)}</pre>
      ))}
    </section>
  );
}
