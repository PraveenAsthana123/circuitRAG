// Centralized API client — every fetch in the UI goes through here.
// Adds X-Tenant-ID + X-Correlation-ID, handles timeouts + AbortController.

const BASE = import.meta.env.VITE_API_BASE_URL || '';
const TENANT = import.meta.env.VITE_DEMO_TENANT_ID || 'demo-tenant';
const DEFAULT_TIMEOUT = 30_000;

function correlationId() {
  return (crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
}

async function request(path, { method = 'GET', body, signal, timeout = DEFAULT_TIMEOUT } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const link = signal ? { signal } : { signal: controller.signal };

  const headers = {
    'X-Tenant-ID': TENANT,
    'X-Correlation-ID': correlationId(),
  };
  let payload = body;
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  try {
    const resp = await fetch(`${BASE}${path}`, { method, headers, body: payload, ...link });
    if (!resp.ok) {
      const text = await resp.text();
      let detail = text;
      try { detail = JSON.parse(text)?.detail || text; } catch { /* leave as text */ }
      throw new Error(`${resp.status}: ${detail}`);
    }
    if (resp.status === 204) return null;
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  uploadDocument: async (file, { sync = false } = {}) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('sync', String(sync));
    return request('/api/v1/documents/upload', { method: 'POST', body: fd, timeout: 120_000 });
  },
  listDocuments: ({ offset = 0, limit = 50, state } = {}) => {
    const p = new URLSearchParams({ offset, limit });
    if (state) p.set('state', state);
    return request(`/api/v1/documents?${p}`);
  },
  getDocument: (id) => request(`/api/v1/documents/${id}`),
  getChunks: (id) => request(`/api/v1/documents/${id}/chunks`),
  deleteDocument: (id) => request(`/api/v1/documents/${id}`, { method: 'DELETE' }),
  ask: (payload, { debug = false } = {}) =>
    request(`/api/v1/ask${debug ? '?debug=true' : ''}`, {
      method: 'POST',
      body: payload,
      timeout: 120_000,
    }),
};
