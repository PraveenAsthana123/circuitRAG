// ⚠️ SOURCE WAS TRUNCATED IN THIS FILE — cut off at:
//      {failures.length ===
// The closing brace, JSX, and final return statement were not present
// in the source paste (50K-char limit). See ../../TRUNCATED.md.
//
// The reconstructed body below is a minimal completion so the file
// parses + renders. Replace with the real source when available.

import { useEffect, useState } from "react";
import { fetchGovernanceFailures } from "../api";

export default function GovernancePanel() {
  const [failures, setFailures] = useState([]);

  useEffect(() => {
    fetchGovernanceFailures().then((data) => setFailures(data.failures || []));
  }, []);

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px" }}>
      <h2>Governance Failures</h2>

      {/* TRUNCATED IN SOURCE — original code was: */}
      {/*   {failures.length === <truncated here>                  */}
      {/* Minimal reconstructed body follows: */}
      {failures.length === 0 && <p>No governance failures.</p>}

      {failures.map((failure, index) => (
        <pre key={index}>{JSON.stringify(failure, null, 2)}</pre>
      ))}
    </section>
  );
}
