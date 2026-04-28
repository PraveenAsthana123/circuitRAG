'use client';

/**
 * Operator admin dashboard — live view of /api/v1/health/detailed.
 *
 * Closes the convergence-shortlist top item (cited in 4 separate
 * gap reviews):
 *   * frontend code review #3      — "admin is a placeholder"
 *   * platform-and-tooling-gap-review §9 — operator visibility
 *   * enterprise-gap-review §1     — operator-facing dashboards
 *   * architecture-and-ai-governance-gap-review §3 — debug UI
 *
 * Renders the same data /api/v1/health/detailed exposes:
 *   * per-namespace circuit breaker state (open / half_open / closed)
 *   * readiness flags (draft store, audit log, auth, agent service,
 *     replay worker)
 *   * uptime + observed_at
 * Refreshes every 5s while the tab is open. Client component (not
 * a Server Component) because the data is operational — changes
 * second-to-second and shouldn't be cached at the SSR layer.
 */

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  api,
  ApiError,
  type HealthDetailedResponse,
  type FrontendBuildInfoResponse,
  type HealthPromptsResponse,
  type HealthToolsResponse,
  type HealthUpstreamsResponse,
  type BreakerState,
  type PromptInfo,
  type ToolStats,
  type TraceLinkAuditRow,
  type TraceLinkDraftRow,
  type TraceLinkHitlRow,
  type TraceLinkResponse,
  type UpstreamHealthRow,
} from '../../lib/api';

const REFRESH_INTERVAL_MS = 5_000;

function fmtUptime(s: number): string {
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

function fmtObservedAt(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function breakerBadgeClass(state: BreakerState['state']): string {
  // Reuses the existing badge palette from globals.css.
  if (state === 'open') return 'badge badge-failed';
  if (state === 'half_open') return 'badge badge-parsing';
  return 'badge badge-active';
}

function fmtMs(s: number | null): string {
  if (s == null) return '—';
  return `${(s * 1000).toFixed(1)} ms`;
}

function sumValues(rec: Record<string, number>): number {
  return Object.values(rec).reduce((a, b) => a + b, 0);
}

/**
 * Compact pill list "ok=3 error=1 replay=2" — keeps the table dense
 * since each tool can have a half-dozen outcome / denial-reason
 * variants and breaking each into its own column would explode width.
 */
function PillRecord({
  rec,
  emptyLabel = '—',
}: {
  rec: Record<string, number>;
  emptyLabel?: string;
}) {
  const entries = Object.entries(rec).filter(([, v]) => v > 0);
  if (entries.length === 0) return <span className="field-help">{emptyLabel}</span>;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {entries
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => (
          <span
            key={k}
            style={{
              fontSize: 12,
              padding: '2px 6px',
              borderRadius: 4,
              backgroundColor: '#f3f4f6',
              fontFamily: 'monospace',
            }}
          >
            {k}={v}
          </span>
        ))}
    </div>
  );
}

export default function AdminPage() {
  const [data, setData] = useState<HealthDetailedResponse | null>(null);
  const [buildInfo, setBuildInfo] = useState<FrontendBuildInfoResponse | null>(null);
  const [tools, setTools] = useState<HealthToolsResponse | null>(null);
  const [prompts, setPrompts] = useState<HealthPromptsResponse | null>(null);
  const [upstreams, setUpstreams] = useState<HealthUpstreamsResponse | null>(null);

  // Trace-link panel: search-driven, not poll-driven. Operator
  // supplies BOTH correlation_id and tenant_id (audit_log RLS is
  // FORCE-enabled; the lookup is honestly per-tenant — see the
  // backend route docstring).
  const [traceQuery, setTraceQuery] = useState('');
  const [traceTenant, setTraceTenant] = useState('');
  const [trace, setTrace] = useState<TraceLinkResponse | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const traceAbortRef = useRef<AbortController | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // ``lastFetchAt`` is local clock — used to show how stale the panel
  // is when the backend goes unreachable and refreshes start failing.
  const [lastFetchAt, setLastFetchAt] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      // Abort any in-flight request before starting a new one.
      abortRef.current?.abort();
      const ctl = new AbortController();
      abortRef.current = ctl;
      try {
        // Fetch detailed health, per-tool stats, prompt registry,
        // and upstream probes in parallel. All four panels render at
        // the same cadence; serializing would multiply the stale
        // window. The backend probes upstreams in parallel internally
        // too, so the worst-case latency is bounded by the slowest
        // single upstream.
        const [resp, buildInfoResp, toolsResp, promptsResp, upstreamsResp] = await Promise.all([
          api.healthDetailed(ctl.signal),
          api.frontendBuildInfo(ctl.signal),
          api.healthTools(ctl.signal),
          api.healthPrompts(ctl.signal),
          api.healthUpstreams(ctl.signal),
        ]);
        if (cancelled) return;
        setData(resp);
        setBuildInfo(buildInfoResp);
        setTools(toolsResp);
        setPrompts(promptsResp);
        setUpstreams(upstreamsResp);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setError(`${e.status} ${e.errorCode}: ${e.detail}`);
        } else if ((e as Error).name === 'AbortError') {
          return; // expected on rapid refresh / unmount
        } else {
          setError((e as Error).message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setLastFetchAt(Date.now());
        }
      }
    }

    load();
    const id = setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, []);

  async function runTraceLookup(e: React.FormEvent) {
    e.preventDefault();
    const q = traceQuery.trim();
    const t = traceTenant.trim();
    if (!q || !t) return;
    traceAbortRef.current?.abort();
    const ctl = new AbortController();
    traceAbortRef.current = ctl;
    setTraceLoading(true);
    setTraceError(null);
    try {
      const resp = await api.traceLink(q, t, ctl.signal);
      setTrace(resp);
    } catch (err) {
      setTrace(null);
      if (err instanceof ApiError) {
        // The 400 INVALID_CORRELATION_ID / INVALID_TENANT_ID paths
        // land here — give the operator the actionable string.
        setTraceError(`${err.status}: ${err.detail}`);
      } else if ((err as Error).name !== 'AbortError') {
        setTraceError((err as Error).message);
      }
    } finally {
      setTraceLoading(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Operator Dashboard</h1>
          <p className="page-subtitle">
            Live view of <code>/api/v1/health/detailed</code> — breaker
            states, readiness flags, and service uptime. Refreshes
            every {REFRESH_INTERVAL_MS / 1000}s while this tab is open.
          </p>
        </div>
      </div>

      {/* Top strip: service + uptime + last refresh. */}
      <div className="metrics-strip">
        <div className="metric-card">
          <div className="metric-label">Service</div>
          <div className="metric-value">{data?.service ?? '—'}</div>
          <div className="field-help">Backend reporting health.</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Uptime</div>
          <div className="metric-value">
            {data ? fmtUptime(data.uptime_s) : '—'}
          </div>
          <div className="field-help">Since process start.</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Observed at</div>
          <div className="metric-value">
            {data ? fmtObservedAt(data.observed_at) : '—'}
          </div>
          <div className="field-help">Server clock at last fetch.</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Last refresh</div>
          <div className="metric-value">
            {lastFetchAt ? new Date(lastFetchAt).toLocaleTimeString() : '—'}
          </div>
          <div className="field-help">
            {error ? (
              <span style={{ color: '#991b1b' }}>stale — fetch failed</span>
            ) : (
              'auto-refresh active'
            )}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Frontend build</div>
          <div className="metric-value">
            {buildInfo?.build_id ? (
              <code style={{ fontSize: 12 }}>{buildInfo.build_id}</code>
            ) : (
              '—'
            )}
          </div>
          <div className="field-help">
            {buildInfo?.git_sha
              ? `git ${buildInfo.git_sha.slice(0, 12)}`
              : buildInfo?.app_version
                ? `version ${buildInfo.app_version}`
                : 'runtime build id'}
          </div>
        </div>
      </div>

      {/* Error banner — visible AND announced to assistive tech. */}
      {error && (
        <div
          className="card"
          role="alert"
          aria-live="assertive"
          style={{ borderColor: '#fecaca' }}
        >
          <strong>Backend unreachable.</strong>
          <div className="field-help" style={{ marginTop: 8 }}>
            {error}. The dashboard will keep retrying every{' '}
            {REFRESH_INTERVAL_MS / 1000}s.
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Deep dives</strong>
          <div className="field-help">
            Interview-grade explanations for the load-bearing topics: Python,
            LLMOps, databases, MCP, breakers, RAG, microservices, chatbot
            system design, the Lang family, and compiler/runtime fit.
          </div>
        </div>
        <div className="page-actions">
          <a href="/admin/python/deep" className="btn">Python</a>
          <a href="/admin/llmops/deep" className="btn">LLMOps</a>
          <a href="/admin/database/deep" className="btn">Databases</a>
          <a href="/admin/mcp/deep" className="btn">MCP</a>
          <a href="/admin/breakers/deep" className="btn">Breakers</a>
          <a href="/admin/rag/deep" className="btn">RAG</a>
          <a href="/admin/microservices/deep" className="btn">Microservices</a>
          <a href="/admin/system-design/chatbot" className="btn">Chatbot design</a>
          <a href="/admin/lang-family/rag" className="btn">Lang family</a>
          <a href="/admin/compiler-stack/rag" className="btn">LLVM / MLIR fit</a>
        </div>
      </div>

      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Frontend build and deploy identity</strong>
          <div className="field-help">
            Use this when users report chunk-load failures, stale bundles, or deployment drift.
          </div>
        </div>
        <div className="table-wrap">
          <table className="table">
            <tbody>
              <tr>
                <th>Build ID</th>
                <td>
                  {buildInfo?.build_id ? (
                    <code>{buildInfo.build_id}</code>
                  ) : (
                    <span className="field-help">unavailable</span>
                  )}
                </td>
              </tr>
              <tr>
                <th>App version</th>
                <td>{buildInfo?.app_version ?? <span className="field-help">—</span>}</td>
              </tr>
              <tr>
                <th>Git SHA</th>
                <td>
                  {buildInfo?.git_sha ? (
                    <code>{buildInfo.git_sha}</code>
                  ) : (
                    <span className="field-help">not provided by runtime</span>
                  )}
                </td>
              </tr>
              <tr>
                <th>Node env</th>
                <td>{buildInfo?.node_env ?? <span className="field-help">—</span>}</td>
              </tr>
              <tr>
                <th>Observed at</th>
                <td>
                  {buildInfo ? (
                    <code>{buildInfo.generated_at}</code>
                  ) : (
                    <span className="field-help">—</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Breakers table. */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Circuit breakers</strong>
          <div className="field-help">
            Open = dependency unreachable; half-open = probing; closed
            = healthy. Recovery timeout shows how long the breaker
            waits in OPEN before allowing a probe.
          </div>
        </div>
        {loading && !data ? (
          <div className="list-empty">
            <span className="spinner" /> Loading…
          </div>
        ) : data && data.breakers.length === 0 ? (
          <div className="list-empty">
            No breakers reported. Backend may not be wired for breaker
            reporting.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>State</th>
                  <th>Failures</th>
                  <th>Recovery timeout</th>
                </tr>
              </thead>
              <tbody>
                {data?.breakers.map((b) => (
                  <tr key={b.name}>
                    <td>
                      <code>{b.name}</code>
                    </td>
                    <td>
                      <span className={breakerBadgeClass(b.state)}>
                        {b.state}
                      </span>
                    </td>
                    <td>{b.failures ?? '—'}</td>
                    <td>
                      {b.recovery_timeout_s != null
                        ? `${b.recovery_timeout_s}s`
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Upstream reachability — cross-service health view from
          inference-svc's perspective. */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Upstreams</strong>
          <div className="field-help">
            Reachability + probe latency for every upstream this service
            depends on — retrieval-svc, ollama, MCP servers, governance
            DB. Each row is a parallel probe with a 2s timeout; one slow
            upstream doesn't stall the rest.
          </div>
        </div>
        {loading && !upstreams ? (
          <div className="list-empty">
            <span className="spinner" /> Loading…
          </div>
        ) : upstreams && upstreams.upstreams.length === 0 ? (
          <div className="list-empty">No upstreams configured.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Kind</th>
                  <th>URL</th>
                  <th>Reachable</th>
                  <th>Latency</th>
                  <th>Status</th>
                  <th>Version</th>
                </tr>
              </thead>
              <tbody>
                {upstreams?.upstreams.map((u: UpstreamHealthRow) => (
                  <tr key={u.name}>
                    <td>
                      <code>{u.name}</code>
                    </td>
                    <td>
                      <span className="field-help">{u.kind}</span>
                    </td>
                    <td>
                      <code style={{ fontSize: 11 }}>{u.url}</code>
                    </td>
                    <td>
                      {u.reachable ? (
                        <span className="badge badge-active">yes</span>
                      ) : (
                        <span className="badge badge-failed">
                          {u.error ?? 'no'}
                        </span>
                      )}
                    </td>
                    <td>
                      {u.latency_ms != null ? (
                        `${u.latency_ms.toFixed(1)} ms`
                      ) : (
                        <span className="field-help">—</span>
                      )}
                    </td>
                    <td>
                      {u.status ? (
                        <code>{u.status}</code>
                      ) : (
                        <span className="field-help">—</span>
                      )}
                    </td>
                    <td>
                      {u.version ?? <span className="field-help">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Per-tool monitoring — aggregate of MCP /metrics. */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Per-tool monitoring</strong>
          <div className="field-help">
            Aggregate of <code>/metrics</code> across registered MCP
            servers, keyed by (namespace, tool). Latency is the
            histogram count + average; <em>p95 stays in Prometheus</em>
            (deriving it from buckets is lossy). Denials list
            auth/scope rejection counts by reason — alert on a sudden
            spike in any reason for a given tool.
          </div>
        </div>
        {tools && tools.unreachable.length > 0 && (
          <div
            className="field-help"
            style={{ marginBottom: 12, color: '#991b1b' }}
            role="status"
          >
            Unreachable namespaces (showing stale data or none):{' '}
            {tools.unreachable.map((n) => (
              <code key={n} style={{ marginRight: 8 }}>
                {n}
              </code>
            ))}
          </div>
        )}
        {loading && !tools ? (
          <div className="list-empty">
            <span className="spinner" /> Loading…
          </div>
        ) : tools && tools.tools.length === 0 ? (
          <div className="list-empty">
            No MCP tool calls observed yet. Make a call to populate this
            panel.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Namespace</th>
                  <th>Tool</th>
                  <th>Calls (by outcome)</th>
                  <th>Latency</th>
                  <th>Denials (by reason)</th>
                </tr>
              </thead>
              <tbody>
                {tools?.tools.map((t: ToolStats) => (
                  <tr key={`${t.namespace}::${t.tool}`}>
                    <td>
                      <code>{t.namespace}</code>
                    </td>
                    <td>
                      <code>{t.tool}</code>
                    </td>
                    <td>
                      <PillRecord rec={t.calls} emptyLabel="no calls" />
                      <div className="field-help" style={{ marginTop: 4 }}>
                        total={sumValues(t.calls)}
                      </div>
                    </td>
                    <td>
                      <div>avg {fmtMs(t.latency.avg_seconds)}</div>
                      <div className="field-help">
                        n={t.latency.count}
                      </div>
                    </td>
                    <td>
                      <PillRecord rec={t.denials} emptyLabel="0" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Prompt registry — active rows from governance.prompts. */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Prompt registry</strong>
          <div className="field-help">
            Active rows from <code>governance.prompts</code> — name,
            version, model, tuning. Template bodies are intentionally
            not shown here; that's a governance-UI concern. This panel
            answers "which prompt + model is live <em>right now</em>?"
          </div>
        </div>
        {loading && !prompts ? (
          <div className="list-empty">
            <span className="spinner" /> Loading…
          </div>
        ) : prompts && !prompts.db_reachable ? (
          <div
            className="list-empty"
            role="status"
            style={{ color: '#991b1b' }}
          >
            Registry unavailable — governance DB unreachable. The
            running service falls back to in-code defaults; check the
            governance-svc connection.
          </div>
        ) : prompts && prompts.prompts.length === 0 ? (
          <div className="list-empty">
            No active prompt rows in <code>governance.prompts</code>.
            Service falls back to in-code <code>PROMPT_TEMPLATES</code>.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Version</th>
                  <th>Model</th>
                  <th>Temperature</th>
                  <th>Max tokens</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {prompts?.prompts.map((p: PromptInfo) => (
                  <tr key={`${p.name}::${p.version}`}>
                    <td>
                      <code>{p.name}</code>
                    </td>
                    <td>
                      <code>{p.version}</code>
                    </td>
                    <td>{p.model ?? <span className="field-help">—</span>}</td>
                    <td>
                      {p.temperature ?? <span className="field-help">—</span>}
                    </td>
                    <td>
                      {p.max_tokens ?? <span className="field-help">—</span>}
                    </td>
                    <td>
                      <span className="badge badge-active">{p.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Trace lookup — given a correlation_id, show audit + draft
          rows linked to it. Search-driven, not auto-refreshing. */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Trace lookup</strong>
          <div className="field-help">
            Paste a <code>correlation_id</code> (the UUID propagated
            via <code>X-Correlation-ID</code> through every request)
            to see the audit rows + draft rows it touched. Reconstructs
            the request end-to-end without code archaeology.
          </div>
        </div>
        <form
          onSubmit={runTraceLookup}
          style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}
        >
          <input
            type="text"
            value={traceQuery}
            onChange={(e) => setTraceQuery(e.target.value)}
            placeholder="correlation_id (UUID)"
            aria-label="Correlation ID"
            style={{
              flex: '1 1 280px',
              padding: '6px 10px',
              fontFamily: 'monospace',
              fontSize: 13,
              border: '1px solid #d1d5db',
              borderRadius: 4,
            }}
          />
          <input
            type="text"
            value={traceTenant}
            onChange={(e) => setTraceTenant(e.target.value)}
            placeholder="tenant_id (UUID)"
            aria-label="Tenant ID"
            style={{
              flex: '1 1 280px',
              padding: '6px 10px',
              fontFamily: 'monospace',
              fontSize: 13,
              border: '1px solid #d1d5db',
              borderRadius: 4,
            }}
          />
          <button
            type="submit"
            className="button"
            disabled={
              traceLoading || !traceQuery.trim() || !traceTenant.trim()
            }
          >
            {traceLoading ? 'Searching…' : 'Search'}
          </button>
        </form>
        {traceError && (
          <div
            className="field-help"
            role="alert"
            style={{ color: '#991b1b', marginBottom: 12 }}
          >
            {traceError}
          </div>
        )}
        {trace && !trace.db_reachable && (
          <div className="list-empty" role="status" style={{ color: '#991b1b' }}>
            Governance DB unreachable — cannot answer trace lookups.
          </div>
        )}
        {trace && trace.db_reachable && (
          <>
            {trace.jaeger_url && (
              <div className="field-help" style={{ marginBottom: 12 }}>
                Open the trace in Jaeger:{' '}
                <a href={trace.jaeger_url} target="_blank" rel="noreferrer">
                  view spans →
                </a>
              </div>
            )}
            <div style={{ marginBottom: 16 }}>
              <strong style={{ fontSize: 14 }}>
                Audit rows ({trace.audit_rows.length})
              </strong>
              {trace.audit_rows.length === 0 ? (
                <div className="field-help" style={{ marginTop: 4 }}>
                  No audit rows found for this correlation_id.
                </div>
              ) : (
                <div className="table-wrap" style={{ marginTop: 6 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Timestamp</th>
                        <th>Action</th>
                        <th>Actor</th>
                        <th>Tenant</th>
                        <th>Resource</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trace.audit_rows.map((row: TraceLinkAuditRow) => (
                        <tr key={row.id}>
                          <td>
                            <code>{row.timestamp}</code>
                          </td>
                          <td>
                            <code>{row.action}</code>
                          </td>
                          <td>
                            <code>
                              {row.actor_id ?? '—'} ({row.actor_type})
                            </code>
                          </td>
                          <td>
                            <code>{row.tenant_id ?? '—'}</code>
                          </td>
                          <td>
                            {row.resource_type ? (
                              <code>
                                {row.resource_type}:{row.resource_id ?? '—'}
                              </code>
                            ) : (
                              <span className="field-help">—</span>
                            )}
                          </td>
                          <td>
                            {row.fail_closed_failed ? (
                              <span className="badge badge-failed">
                                fail_closed_failed
                              </span>
                            ) : (
                              <span className="badge badge-active">ok</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div>
              <strong style={{ fontSize: 14 }}>
                Draft rows ({trace.draft_rows.length})
              </strong>
              {trace.draft_rows.length === 0 ? (
                <div className="field-help" style={{ marginTop: 4 }}>
                  No drafts found for this correlation_id.
                </div>
              ) : (
                <div className="table-wrap" style={{ marginTop: 6 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Draft</th>
                        <th>Tool</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Replayed</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trace.draft_rows.map((row: TraceLinkDraftRow) => (
                        <tr key={row.draft_id}>
                          <td>
                            <code>{row.draft_id}</code>
                          </td>
                          <td>
                            <code>{row.tool}</code>
                          </td>
                          <td>
                            <span
                              className={
                                row.status === 'replayed'
                                  ? 'badge badge-active'
                                  : row.status === 'rejected'
                                    ? 'badge badge-failed'
                                    : 'badge badge-parsing'
                              }
                            >
                              {row.status}
                            </span>
                          </td>
                          <td>
                            <code>{row.created_at}</code>
                          </td>
                          <td>
                            {row.replayed_at ? (
                              <code>{row.replayed_at}</code>
                            ) : (
                              <span className="field-help">—</span>
                            )}
                          </td>
                          <td>{row.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {/* HITL queue rows — added with the forensics endpoint
                extension that joined governance.hitl_queue. The
                inline form on the dashboard now matches the
                dedicated /admin/forensics page in coverage. */}
            <div style={{ marginTop: 16 }}>
              <strong style={{ fontSize: 14 }}>
                HITL queue ({trace.hitl_rows.length}) — human-review evidence
              </strong>
              {trace.hitl_rows.length === 0 ? (
                <div className="field-help" style={{ marginTop: 4 }}>
                  No HITL items for this correlation_id (the answer
                  was not flagged for human review).
                </div>
              ) : (
                <div className="table-wrap" style={{ marginTop: 6 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Question</th>
                        <th>Confidence</th>
                        <th>Flag reason</th>
                        <th>Review</th>
                        <th>Reviewer</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trace.hitl_rows.map((row: TraceLinkHitlRow) => (
                        <tr key={row.id}>
                          <td>
                            <code style={{ fontSize: 11 }}>
                              {row.id.slice(0, 8)}…
                            </code>
                          </td>
                          <td
                            title={row.question}
                            style={{
                              maxWidth: 320,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {row.question}
                          </td>
                          <td>
                            <code>
                              {row.confidence !== null && row.confidence !== undefined
                                ? row.confidence.toFixed(3)
                                : '—'}
                            </code>
                          </td>
                          <td>
                            {row.flag_reason ?? <span className="field-help">—</span>}
                          </td>
                          <td>
                            <span
                              className={
                                row.review_status === 'approved'
                                  ? 'badge badge-active'
                                  : row.review_status === 'rejected'
                                    ? 'badge badge-failed'
                                    : 'badge badge-parsing'
                              }
                            >
                              {row.review_status}
                            </span>
                          </td>
                          <td>
                            {row.reviewer_id ? (
                              <code style={{ fontSize: 11 }}>
                                {row.reviewer_id.slice(0, 8)}…
                              </code>
                            ) : (
                              <span className="field-help">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {/* Open in dedicated Forensics page — useful when an
                operator wants the larger view, deep-link to
                share, or richer table layout. The inline form
                here remains because some operators prefer to
                stay on the dashboard. */}
            {traceQuery.trim() && traceTenant.trim() && (
              <div className="field-help" style={{ marginTop: 16 }}>
                <Link
                  href={`/admin/forensics?correlation_id=${encodeURIComponent(traceQuery.trim())}&tenant_id=${encodeURIComponent(traceTenant.trim())}`}
                  style={{ color: '#2563eb', textDecoration: 'none' }}
                >
                  Open in Forensics →
                </Link>
              </div>
            )}
          </>
        )}
      </div>

      {/* Readiness flags. */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Readiness</strong>
          <div className="field-help">
            Operational flags reported by the inference service lifespan.
          </div>
        </div>
        {data ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Subsystem</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.readiness).map(([k, v]) => (
                  <tr key={k}>
                    <td>
                      <code>{k}</code>
                    </td>
                    <td>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="list-empty">—</div>
        )}
      </div>
    </>
  );
}
