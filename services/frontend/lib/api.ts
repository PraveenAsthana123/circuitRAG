/**
 * Centralized API client (global CLAUDE.md §14.2 rule 3).
 *
 * - Same-origin: Next.js rewrites /api/* to the gateway (see next.config.mjs)
 * - Attaches X-Tenant-ID + X-Correlation-ID
 * - Parses the standard error envelope from documind_core.schemas.ErrorResponse
 * - Timeout via AbortController (component can pass its own signal to cancel
 *   in-flight requests on unmount)
 */

const TENANT_ID = process.env.NEXT_PUBLIC_DEMO_TENANT_ID ?? 'demo-tenant';
const DEFAULT_TIMEOUT_MS = 30_000;

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  body?: unknown;
  signal?: AbortSignal;
  timeout?: number;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly errorCode: string,
    public readonly detail: string,
    public readonly correlationId: string,
  ) {
    super(`${status} ${errorCode}: ${detail}`);
    this.name = 'ApiError';
  }
}

function correlationId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, timeout = DEFAULT_TIMEOUT_MS } = opts;

  // Caller-supplied signal is honored; we also attach our own timeout.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const combinedSignal = signal ?? controller.signal;

  const headers: Record<string, string> = {
    'X-Tenant-ID': TENANT_ID,
    'X-Correlation-ID': correlationId(),
  };

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body != null) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  try {
    const resp = await fetch(path, { method, headers, body: payload, signal: combinedSignal });
    if (!resp.ok) {
      const cid = resp.headers.get('X-Correlation-ID') ?? '';
      let errorCode = 'HTTP_ERROR';
      let detail = `Request failed with status ${resp.status}`;
      try {
        const envelope = await resp.json();
        errorCode = envelope.error_code ?? errorCode;
        detail = envelope.detail ?? detail;
      } catch {
        /* non-JSON error body — use defaults */
      }
      throw new ApiError(resp.status, errorCode, detail, cid);
    }
    if (resp.status === 204) return undefined as T;
    return (await resp.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

// -- Typed endpoint wrappers -------------------------------------------

export interface DocumentSummary {
  id: string;
  filename: string;
  title?: string;
  state: string;
  size_bytes: number;
  page_count?: number;
  chunk_count?: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentList {
  items: DocumentSummary[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface UploadResponse {
  document_id: string;
  state: string;
  saga_id?: string;
  message: string;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  page_number: number;
  snippet: string;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  model: string;
  prompt_version: string;
  tokens_prompt: number;
  tokens_completion: number;
  confidence: number;
  correlation_id: string;
  debug?: Record<string, unknown>;
}

export const api = {
  uploadDocument: (file: File, { sync = false }: { sync?: boolean } = {}) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('sync', String(sync));
    return request<UploadResponse>('/api/v1/documents/upload', {
      method: 'POST',
      body: fd,
      timeout: 120_000,
    });
  },

  listDocuments: ({ offset = 0, limit = 50, state }: { offset?: number; limit?: number; state?: string } = {}) => {
    const p = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (state) p.set('state', state);
    return request<DocumentList>(`/api/v1/documents?${p}`);
  },

  deleteDocument: (id: string) =>
    request<null>(`/api/v1/documents/${id}`, { method: 'DELETE' }),

  ask: (
    payload: { query: string; top_k?: number; strategy?: string; model?: string },
    { debug = false }: { debug?: boolean } = {},
  ) =>
    request<AskResponse>(`/api/v1/ask${debug ? '?debug=true' : ''}`, {
      method: 'POST',
      body: payload,
      timeout: 120_000,
    }),
};
