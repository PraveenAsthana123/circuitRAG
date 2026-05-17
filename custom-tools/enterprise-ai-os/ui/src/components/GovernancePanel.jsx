import { useEffect, useState } from "react";
import { fetchGovernanceFailures } from "../api";

export default function GovernancePanel() {
  const [failures, setFailures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchGovernanceFailures({ signal: controller.signal })
      .then((data) => setFailures(data.failures || []))
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
      <h2>Governance Failures</h2>
      {error && <p role="alert">{error}</p>}
      {!error && loading && <p>Loading governance failures...</p>}
      {!error && !loading && failures.length === 0 && <p>No governance failures.</p>}
      {failures.map((failure, index) => (
        <pre key={index}>{JSON.stringify(failure, null, 2)}</pre>
      ))}
    </section>
  );
}
