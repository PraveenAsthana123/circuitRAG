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

import { useEffect, useRef, useState } from 'react';
import {
  api,
  ApiError,
  type HealthDetailedResponse,
  type BreakerState,
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

export default function AdminPage() {
  const [data, setData] = useState<HealthDetailedResponse | null>(null);
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
        const resp = await api.healthDetailed(ctl.signal);
        if (cancelled) return;
        setData(resp);
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
