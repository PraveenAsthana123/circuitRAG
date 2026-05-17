import { useEffect, useState } from "react";
import { fetchCostSummary } from "../api";

export default function CostPanel() {
  const [cost, setCost] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchCostSummary({ signal: controller.signal })
      .then(setCost)
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
      <h2>Cost Summary</h2>
      {error && <p role="alert">{error}</p>}
      {!error && loading && <p>Loading cost data...</p>}
      {cost && <pre>{JSON.stringify(cost, null, 2)}</pre>}
    </section>
  );
}
