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

// -- Operator / health surfaces ---------------------------------------

export interface BreakerState {
  name: string;
  state: 'closed' | 'open' | 'half_open';
  failures: number | null;
  recovery_timeout_s: number | null;
}

export interface HealthDetailedResponse {
  service: string;
  uptime_s: number;
  observed_at: string;
  breakers: BreakerState[];
  readiness: Record<string, string>;
}

export interface ToolLatencyStats {
  count: number;
  sum_seconds: number;
  avg_seconds: number | null;
}

export interface ToolStats {
  namespace: string;
  tool: string;
  // outcome → count: ok | error | replay | http_<status> | in_progress | conflict
  calls: Record<string, number>;
  latency: ToolLatencyStats;
  // reason → count: NOT_AUTHENTICATED | INVALID_TOKEN | INSUFFICIENT_SCOPE | UNKNOWN
  denials: Record<string, number>;
}

export interface HealthToolsResponse {
  service: string;
  observed_at: string;
  tools: ToolStats[];
  // namespaces whose /metrics scrape failed; UI shows them as "(stale)"
  unreachable: string[];
}

export interface PromptInfo {
  name: string;
  version: string;
  model: string | null;
  temperature: number | null;
  max_tokens: number | null;
  status: string;
}

export interface HealthPromptsResponse {
  service: string;
  observed_at: string;
  // false when the DB is unreachable or the registry table is missing —
  // UI renders "(registry unavailable)" rather than "(no active prompts)"
  // since the two states have very different operational meaning.
  db_reachable: boolean;
  prompts: PromptInfo[];
}

export interface TraceLinkAuditRow {
  id: string;
  timestamp: string;
  tenant_id: string | null;
  actor_id: string | null;
  actor_type: string;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  fail_closed_failed: boolean;
}

export interface TraceLinkDraftRow {
  draft_id: string;
  tenant_id: string | null;
  tool: string;
  status: string;
  reason: string;
  created_at: string;
  replayed_at: string | null;
}

export interface TraceLinkResponse {
  correlation_id: string;
  observed_at: string;
  db_reachable: boolean;
  audit_rows: TraceLinkAuditRow[];
  draft_rows: TraceLinkDraftRow[];
  // Jaeger deep-link if DOCUMIND_JAEGER_URL is configured server-side
  jaeger_url: string | null;
}

export interface UpstreamHealthRow {
  name: string;
  kind: string; // 'http_service' | 'mcp' | 'llm' | 'db' | 'kafka'
  url: string;
  reachable: boolean;
  latency_ms: number | null;
  status: string | null;
  version: string | null;
  error: string | null;
}

export interface HealthUpstreamsResponse {
  service: string;
  observed_at: string;
  upstreams: UpstreamHealthRow[];
}

export interface TechstackEntry {
  name: string;
  category: string;
  source: string; // 'pip' | 'npm' | 'binary' | 'docker'
  installed: boolean;
  version: string | null;
  purpose: string;
  error: string | null;
}

export interface HealthTechstackResponse {
  service: string;
  observed_at: string;
  installed_count: number;
  pending_count: number;
  entries: TechstackEntry[];
}

export interface ClientErrorRecord {
  id: string;
  received_at: string;
  kind: string; // 'window_error' | 'unhandled_rejection' | 'react_boundary' | 'manual'
  message: string;
  stack: string | null;
  route: string | null;
  user_agent: string | null;
  correlation_id: string | null;
  extra: Record<string, unknown>;
}

export interface ClientErrorListResponse {
  service: string;
  observed_at: string;
  capacity: number;
  count: number;
  records: ClientErrorRecord[];
}

// Body shape posted by the global error reporter.
export interface ClientErrorReportBody {
  kind: string;
  message: string;
  stack?: string | null;
  route?: string | null;
  user_agent?: string | null;
  correlation_id?: string | null;
  extra?: Record<string, unknown>;
}

export const api = {
  /**
   * Operator-facing detailed health. Powers the admin dashboard:
   * breaker states + readiness flags + uptime + observed_at, refreshed
   * client-side every few seconds. The endpoint is unauthenticated by
   * design (operators reach it through nginx + admin role at the
   * gateway, not through tenant auth).
   */
  healthDetailed: (signal?: AbortSignal) =>
    request<HealthDetailedResponse>('/api/v1/health/detailed', {
      timeout: 5_000,
      signal,
    }),

  /**
   * Per-tool aggregate of MCP /metrics across every registered MCP
   * server. Powers the per-tool monitoring panel in the admin
   * dashboard — calls by outcome, latency aggregate, denials by
   * reason, all keyed by (namespace, tool).
   */
  healthTools: (signal?: AbortSignal) =>
    request<HealthToolsResponse>('/api/v1/health/tools', {
      timeout: 5_000,
      signal,
    }),

  /**
   * Active prompt registry — operator visibility into which prompt
   * versions + models + tuning are live. Reads governance.prompts
   * WHERE status='active'; ``db_reachable=false`` means the DB
   * couldn't be queried (degradation, not "no prompts").
   */
  healthPrompts: (signal?: AbortSignal) =>
    request<HealthPromptsResponse>('/api/v1/health/prompts', {
      timeout: 5_000,
      signal,
    }),

  /**
   * Cross-service reachability probes from inference-svc's
   * perspective — retrieval-svc, ollama, MCP namespaces, governance
   * DB. Probes run in parallel server-side with a 2s per-probe
   * timeout, so the UI gets a complete picture even when one
   * upstream is wedged.
   */
  healthUpstreams: (signal?: AbortSignal) =>
    request<HealthUpstreamsResponse>('/api/v1/health/upstreams', {
      timeout: 5_000,
      signal,
    }),

  /**
   * Curated tech-stack inventory — installed pip/npm packages vs
   * pending. Read-only; no installs from the UI. Operators see
   * which RAG/agent/observability/data tools are wired and run
   * `pip install X` themselves for any pending row they want.
   */
  healthTechstack: (signal?: AbortSignal) =>
    request<HealthTechstackResponse>('/api/v1/health/techstack', {
      timeout: 5_000,
      signal,
    }),

  /**
   * List recent client-side errors reported by the frontend's
   * global error reporter. Newest first, in-memory ring buffer.
   */
  clientErrorList: (signal?: AbortSignal) =>
    request<ClientErrorListResponse>('/api/v1/admin/client-errors', {
      timeout: 5_000,
      signal,
    }),

  /**
   * Submit a client-error report. Called by the global error
   * reporter on window.onerror / unhandledrejection / React
   * error boundaries. Best-effort; reporting must not break
   * further error handling (so callers ignore the response).
   *
   * The request wrapper auto-sets Content-Type when ``body`` is
   * a non-FormData object, so pass the plain object — don't
   * pre-stringify.
   */
  reportClientError: (body: ClientErrorReportBody) =>
    request<ClientErrorRecord>('/api/v1/admin/client-errors', {
      method: 'POST',
      body,
      timeout: 3_000,
    }),

  /**
   * Trace → draft → audit reconstruction by (correlation_id,
   * tenant_id). Tenant is required because audit_log RLS is
   * FORCE-enabled and the documind_app role is non-BYPASSRLS;
   * the lookup scopes per-tenant honestly rather than pretending
   * cross-tenant access works.
   *
   * Backend returns 400 on a malformed UUID for either field.
   * The UI surfaces that as "(invalid X)".
   */
  traceLink: (correlationId: string, tenantId: string, signal?: AbortSignal) =>
    request<TraceLinkResponse>(
      `/api/v1/admin/trace/${encodeURIComponent(correlationId)}`
        + `?tenant_id=${encodeURIComponent(tenantId)}`,
      { timeout: 5_000, signal },
    ),

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
