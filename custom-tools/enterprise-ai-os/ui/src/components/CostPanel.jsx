// ⚠️ STUB — imported by App.jsx but NO source was provided in Tool Set
//     31. Replace with operator source. See ../../TRUNCATED.md.

import { useEffect, useState } from "react";

export default function CostPanel() {
  const [cost, setCost] = useState(null);

  useEffect(() => {
    fetch("http://localhost:8000/command-center/cost/summary")
      .then((res) => res.json())
      .then(setCost)
      .catch(() => setCost({ error: "Cost endpoint not available" }));
  }, []);

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px" }}>
      <h2>Cost Summary</h2>
      {!cost && <p>Loading cost data...</p>}
      {cost && cost.error && <p>{cost.error}</p>}
      {cost && !cost.error && (
        <pre>{JSON.stringify(cost, null, 2)}</pre>
      )}
    </section>
  );
}
