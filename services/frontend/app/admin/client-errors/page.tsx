'use client';

/**
 * Client-error admin page — shows the in-memory ring buffer of
 * frontend errors (uncaught exceptions, unhandled promise
 * rejections, React error-boundary catches) reported by every
 * browser tab via the global ClientErrorReporter.
 *
 * Closes the gap that bit during the techstack rollout: the user
 * reported "Application error: client-side exception" but the
 * backend had no visibility into what JS error fired. With the
 * reporter mounted in layout.tsx, the next browser-side error
 * shows up here automatically.
 *
 * Auto-refresh every 5s (operator typically tabs over to this
 * page WHILE the user is reporting an issue, not after; quick
 * cadence matters).
 */

import { useEffect, useRef, useState } from 'react';
import {
  api,
  ApiError,
  type ClientErrorListResponse,
  type ClientErrorRecord,
  type FrontendBuildInfoResponse,
} from '../../../lib/api';

const REFRESH_INTERVAL_MS = 5_000;

function kindBadgeClass(kind: string): string {
  if (kind === 'window_error') return 'badge badge-failed';
  if (kind === 'unhandled_rejection') return 'badge badge-failed';
  if (kind === 'react_boundary') return 'badge badge-parsing';
  // fetch_failed (4xx/5xx) and fetch_error (network/timeout/CORS) are
  // separate signals — color them amber so they stand out from JS
  // exceptions but don't read as 'crashed.'
  if (kind === 'fetch_failed' || kind === 'fetch_error') return 'badge badge-parsing';
  return 'badge badge-active';
}

export default function ClientErrorsPage() {
  const [data, setData] = useState<ClientErrorListResponse | null>(null);
  const [buildInfo, setBuildInfo] = useState<FrontendBuildInfoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      abortRef.current?.abort();
      const ctl = new AbortController();
      abortRef.current = ctl;
      try {
        // Fetch errors + build identity together. When operators are
        // looking at "what broke in the browser," knowing WHICH BUILD
        // those browsers are running is load-bearing — a chunk error
        // on build A and a chunk error on build B mean different
        // things.
        const [resp, biResp] = await Promise.all([
          api.clientErrorList(ctl.signal),
          api.frontendBuildInfo(ctl.signal),
        ]);
        if (cancelled) return;
        setData(resp);
        setBuildInfo(biResp);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setError(`${e.status}: ${e.detail}`);
        } else if ((e as Error).name !== 'AbortError') {
          setError((e as Error).message);
        }
      } finally {
        if (!cancelled) setLoading(false);
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

  function toggle(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Client-side errors</h1>
          <p className="page-subtitle">
            Frontend uncaught exceptions, unhandled Promise rejections,
            and React error-boundary catches reported by every browser
            tab. In-memory ring buffer (capacity{' '}
            <strong>{data?.capacity ?? '—'}</strong>) — restart drops
            history. Refreshes every {REFRESH_INTERVAL_MS / 1000}s.
          </p>
        </div>
      </div>

      <div className="metrics-strip">
        <div className="metric-card">
          <div className="metric-label">Errors in buffer</div>
          <div className="metric-value">{data?.count ?? '—'}</div>
          <div className="field-help">newest first</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Buffer capacity</div>
          <div className="metric-value">{data?.capacity ?? '—'}</div>
          <div className="field-help">oldest evicted when full</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Observed at</div>
          <div className="metric-value">
            {data
              ? new Date(data.observed_at).toLocaleTimeString()
              : '—'}
          </div>
          <div className="field-help">server clock at last fetch</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Frontend build</div>
          <div
            className="metric-value"
            style={{ fontFamily: 'monospace', fontSize: 14 }}
            title={buildInfo?.build_id ?? '—'}
          >
            {buildInfo?.build_id
              ? buildInfo.build_id.slice(0, 8)
              : '—'}
          </div>
          <div className="field-help">
            {buildInfo
              ? `v${buildInfo.app_version ?? '—'} (${buildInfo.node_env ?? '—'})`
              : '—'}
          </div>
        </div>
      </div>

      {error && (
        <div className="card" role="alert" style={{ borderColor: '#fecaca' }}>
          <strong>Cannot fetch client errors.</strong>
          <div className="field-help" style={{ marginTop: 8 }}>
            {error}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Recent errors</strong>
          <div className="field-help">
            Click a row to expand stack trace. Stacks are capped at 4KB
            server-side.
          </div>
        </div>
        {loading && !data ? (
          <div className="list-empty">
            <span className="spinner" /> Loading…
          </div>
        ) : data && data.records.length === 0 ? (
          <div className="list-empty">
            No client errors in the last buffer cycle. The reporter is
            installed; this is the healthy state.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 90 }}>Kind</th>
                  <th>When</th>
                  <th>Route</th>
                  <th>Message</th>
                  <th>Correlation ID</th>
                </tr>
              </thead>
              <tbody>
                {data?.records.map((r: ClientErrorRecord) => (
                  <>
                    <tr key={r.id}>
                      <td>
                        <span className={kindBadgeClass(r.kind)}>{r.kind}</span>
                      </td>
                      <td>
                        <code style={{ fontSize: 11 }}>
                          {new Date(r.received_at).toLocaleTimeString()}
                        </code>
                      </td>
                      <td>
                        <code style={{ fontSize: 12 }}>{r.route ?? '—'}</code>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => toggle(r.id)}
                          style={{
                            background: 'none',
                            border: 'none',
                            padding: 0,
                            color: '#1e3a8a',
                            cursor: 'pointer',
                            textAlign: 'left',
                            font: 'inherit',
                          }}
                        >
                          {r.message}
                        </button>
                      </td>
                      <td>
                        {r.correlation_id ? (
                          <code style={{ fontSize: 11 }}>
                            {r.correlation_id}
                          </code>
                        ) : (
                          <span className="field-help">—</span>
                        )}
                      </td>
                    </tr>
                    {expanded[r.id] && (
                      <tr key={`${r.id}-detail`}>
                        <td colSpan={5}>
                          <div
                            style={{
                              backgroundColor: '#f9fafb',
                              padding: 8,
                              borderRadius: 4,
                              fontSize: 12,
                            }}
                          >
                            <div className="field-help" style={{ marginBottom: 6 }}>
                              user-agent: <code>{r.user_agent ?? '—'}</code>
                            </div>
                            {r.stack ? (
                              <pre
                                style={{
                                  whiteSpace: 'pre-wrap',
                                  margin: 0,
                                  fontSize: 11,
                                }}
                              >
                                {r.stack}
                              </pre>
                            ) : (
                              <span className="field-help">
                                No stack trace recorded.
                              </span>
                            )}
                            {Object.keys(r.extra).length > 0 && (
                              <div style={{ marginTop: 6 }}>
                                <span className="field-help">extra: </span>
                                <code style={{ fontSize: 11 }}>
                                  {JSON.stringify(r.extra)}
                                </code>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
