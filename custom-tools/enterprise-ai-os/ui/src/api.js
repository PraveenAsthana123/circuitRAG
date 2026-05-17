const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function authHeaders() {
  const token = window.localStorage?.getItem("enterprise_ai_os_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function requestJson(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    throw new Error(`Request failed ${res.status}: ${path}`);
  }

  return res.json();
}

export function fetchSummary(options) {
  return requestJson("/command-center/summary", options);
}

export function fetchTraces(options) {
  return requestJson("/command-center/traces", options);
}

export function fetchGovernanceFailures(options) {
  return requestJson("/command-center/governance/failures", options);
}

export function fetchOpenIncidents(options) {
  return requestJson("/command-center/incidents/open", options);
}

export function fetchCostSummary(options) {
  return requestJson("/command-center/cost/summary", options);
}
