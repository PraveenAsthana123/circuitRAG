import { useEffect, useState } from "react";
import { fetchTraces } from "../api";

export default function TraceViewer() {
  const [traces, setTraces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchTraces({ signal: controller.signal })
      .then((data) => setTraces(data.traces || []))
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
      <h2>Traces</h2>
      {error && <p role="alert">{error}</p>}
      {!error && loading && <p>Loading traces...</p>}
      {!error && !loading && traces.length === 0 && <p>No traces yet.</p>}
      {traces.map((trace, index) => (
        <pre key={index}>{JSON.stringify(trace, null, 2)}</pre>
      ))}
    </section>
  );
}
