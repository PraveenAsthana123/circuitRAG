const API_BASE = "http://localhost:8000";

export async function fetchSummary() {
  const res = await fetch(`${API_BASE}/command-center/summary`);
  return res.json();
}

export async function fetchTraces() {
  const res = await fetch(`${API_BASE}/command-center/traces`);
  return res.json();
}

export async function fetchGovernanceFailures() {
  const res = await fetch(`${API_BASE}/command-center/governance/failures`);
  return res.json();
}

export async function fetchOpenIncidents() {
  const res = await fetch(`${API_BASE}/command-center/incidents/open`);
  return res.json();
}
