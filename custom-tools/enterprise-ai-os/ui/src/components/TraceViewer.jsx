import { useEffect, useState } from "react";
import { fetchTraces } from "../api";

export default function TraceViewer() {
  const [traces, setTraces] = useState([]);

  useEffect(() => {
    fetchTraces().then((data) => setTraces(data.traces || []));
  }, []);

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px" }}>
      <h2>Traces</h2>

      {traces.length === 0 && <p>No traces yet.</p>}

      {traces.map((trace, index) => (
        <pre key={index}>{JSON.stringify(trace, null, 2)}</pre>
      ))}
    </section>
  );
}
