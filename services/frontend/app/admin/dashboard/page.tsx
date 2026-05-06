'use client';

/**
 * /admin/dashboard — executive single-page summary.
 *
 * Reads /api/v1/dashboard/summary and renders the four headline
 * panels: system health, council bottleneck, approval engine,
 * provider rollup. Auto-refreshes every 10s.
 *
 * Per CLAUDE.md §47 (architecture) + §53.39 (observability taxonomy).
 * Drilled at drill_dashboard_summary_api.py.
 */
import { useCallback, useEffect, useState } from 'react';

type ProviderRow = {
  provider: string;
  attempted: number;
  applied: number;
  apply_rate: number;
  avg_latency_s: number;
  latency_samples?: number;
  note?: string;
};

type Summary = {
  version: string;
  paperclip_version: string;
  generated_at: number;
  system_health: {
    overall: 'healthy' | 'degraded' | 'alarm';
    outbox_status: string;
    drill_pass_rate: number;
    drill_failed: number;
    stale_outbox_5m: number;
  };
  council_signal: {
    apply_rate: number;
    bottleneck_active: boolean;
    bottleneck_reason: string;
    suggested_action: string | null;
  };
  approval_engine: {
    policy_version: string;
    auto_count: number;
    ask_count: number;
    batched_count: number;
    blocked_count: number;
    cache_hits: number;
    cache_active: number;
    queue_depth: number;
    queue_is_due: boolean;
    audit_total: number;
    spam_reduction_pct: number;
  };
  providers: ProviderRow[];
  ops_queue: {
    tasks_total: number;
    tasks_completed: number;
    tasks_pending: number;
    hitl_pending: number;
    pending_issues_total: number;
  };
  links: Record<string, string>;
  honest_gaps: string[];
};

type Resp = { data: Summary; correlation_id: string };

const HEALTH_COLORS = {
  healthy: '#393',
  degraded: '#c80',
  alarm: '#c33',
} as const;

function HealthPill({ status }: { status: 'healthy' | 'degraded' | 'alarm' }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: 12,
        background: HEALTH_COLORS[status],
        color: 'white',
        fontWeight: 600,
        fontSize: 12,
        textTransform: 'uppercase',
      }}
    >
      {status}
    </span>
  );
}

export default function DashboardPage() {
  const [resp, setResp] = useState<Resp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/dashboard/summary', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setResp(j);
      setError(null);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(refresh, 10000);
    return () => clearInterval(id);
  }, [autoRefresh, refresh]);

  if (error) return <div style={{ padding: 20, color: '#c33' }}>Error: {error}</div>;
  if (!resp) return <div style={{ padding: 20 }}>Loading…</div>;

  const d = resp.data;
  // Defensive guards: when Paperclip is older than v8/v9, some surface
  // keys may be missing. Use empty objects so accessor expressions
  // below don't crash. Drill enforces optional-chaining presence.
  const sh = d.system_health ?? { overall: 'healthy' as const, outbox_status: 'unknown', drill_pass_rate: 1.0, drill_failed: 0, stale_outbox_5m: 0 };
  const cs = d.council_signal ?? { apply_rate: 0, bottleneck_active: false, bottleneck_reason: 'no signal', suggested_action: null };
  const ae = d.approval_engine ?? { policy_version: 'unknown', auto_count: 0, ask_count: 0, batched_count: 0, blocked_count: 0, cache_hits: 0, cache_active: 0, queue_depth: 0, queue_is_due: false, audit_total: 0, spam_reduction_pct: 0 };
  const oq = d.ops_queue ?? { tasks_total: 0, tasks_completed: 0, tasks_pending: 0, hitl_pending: 0, pending_issues_total: 0 };
  const providers = d.providers ?? [];
  const honest_gaps = d.honest_gaps ?? [];

  return (
    <div style={{ padding: 20 }}>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">
            Executive dashboard <HealthPill status={sh.overall} />
          </h1>
          <p className="page-subtitle">
            Single-page consolidation of Paperclip <code>{d.paperclip_version}</code>{' '}
            surface keys. Auto-refresh every 10s. Backed by{' '}
            <code>/api/v1/dashboard/summary</code> → <code>/api/v1/paperclip</code>.
          </p>
        </div>
        <label style={{ float: 'right' }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />{' '}
          Auto-refresh
        </label>
      </div>

      {/* System health */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>System health — {sh.overall.toUpperCase()}</strong>
        <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
          <tbody>
            <tr>
              <td>Outbox status</td>
              <td>
                <code>{sh.outbox_status}</code>
              </td>
              <td>Stale &gt; 5m</td>
              <td>
                <code>{sh.stale_outbox_5m}</code>
              </td>
            </tr>
            <tr>
              <td>Drill pass rate</td>
              <td>
                <strong
                  style={{
                    color:
                      sh.drill_pass_rate >= 0.95
                        ? '#393'
                        : sh.drill_pass_rate >= 0.8
                          ? '#c80'
                          : '#c33',
                  }}
                >
                  {(sh.drill_pass_rate * 100).toFixed(1)}%
                </strong>
              </td>
              <td>Drills failed</td>
              <td>
                <code>{sh.drill_failed}</code>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Council bottleneck signal — the §55.3 outcome */}
      <div
        className="card"
        style={{
          marginTop: 16,
          borderLeft: cs.bottleneck_active ? '4px solid #c33' : '4px solid #393',
        }}
      >
        <strong>Council bottleneck signal</strong>
        <p style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
          Per §55.3 outcome contract. apply_rate=
          <strong>{(cs.apply_rate * 100).toFixed(2)}%</strong>;{' '}
          {cs.bottleneck_active ? (
            <strong style={{ color: '#c33' }}>BOTTLENECK ACTIVE</strong>
          ) : (
            <strong style={{ color: '#393' }}>healthy</strong>
          )}
          .
        </p>
        <div style={{ fontSize: 13, marginTop: 6 }}>{cs.bottleneck_reason}</div>
        {cs.suggested_action && (
          <div style={{ marginTop: 8, fontSize: 12, padding: 8, background: '#fee', borderRadius: 4 }}>
            <strong>Action:</strong> {cs.suggested_action}
          </div>
        )}
      </div>

      {/* Approval engine — the §52 row 4 outcome */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>
          Approval engine{' '}
          <span style={{ fontSize: 12, color: '#666' }}>
            policy=<code>{ae.policy_version}</code>
          </span>
        </strong>
        <p style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
          Per §52 row 4 (operator API gap). Spam reduction:{' '}
          <strong>{ae.spam_reduction_pct}%</strong> of evaluated commands
          auto-approved or blocked (no operator prompt needed).
        </p>
        <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
          <tbody>
            <tr>
              <td>AUTO_APPROVE</td>
              <td align="right">
                <code>{ae.auto_count}</code>
              </td>
              <td>ASK</td>
              <td align="right">
                <code>{ae.ask_count}</code>
              </td>
              <td>BATCHED</td>
              <td align="right">
                <code>{ae.batched_count}</code>
              </td>
              <td>BLOCK</td>
              <td align="right">
                <code>{ae.blocked_count}</code>
              </td>
            </tr>
            <tr>
              <td>Cache active</td>
              <td align="right">
                <code>{ae.cache_active}</code>
              </td>
              <td>Cache hits</td>
              <td align="right">
                <code>{ae.cache_hits}</code>
              </td>
              <td>Queue depth</td>
              <td align="right">
                <code>{ae.queue_depth}</code>
              </td>
              <td>Queue due</td>
              <td align="right">
                <code>{ae.queue_is_due ? 'yes' : 'no'}</code>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Provider rollup — from v8 registry */}
      {providers.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <strong>Provider apply-rate rollup</strong>
          <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
            <thead>
              <tr>
                <th align="left">Provider</th>
                <th align="right">Attempted</th>
                <th align="right">Applied</th>
                <th align="right">Apply rate</th>
                <th align="right">Avg latency</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.provider}>
                  <td>
                    <code>{p.provider}</code>
                  </td>
                  <td align="right">{p.attempted}</td>
                  <td align="right">{p.applied}</td>
                  <td
                    align="right"
                    style={{
                      color:
                        p.attempted >= 10 && p.apply_rate < 0.1
                          ? '#c33'
                          : p.apply_rate >= 0.5
                            ? '#393'
                            : 'inherit',
                      fontWeight: 600,
                    }}
                  >
                    {(p.apply_rate * 100).toFixed(2)}%
                  </td>
                  <td align="right">
                    {p.avg_latency_s > 0 ? `${p.avg_latency_s.toFixed(1)}s` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Ops queue */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>Ops queue</strong>
        <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
          <tbody>
            <tr>
              <td>Tasks total</td>
              <td align="right">
                <code>{oq.tasks_total}</code>
              </td>
              <td>Completed</td>
              <td align="right">
                <code>{oq.tasks_completed}</code>
              </td>
              <td>Pending</td>
              <td align="right">
                <code>{oq.tasks_pending}</code>
              </td>
            </tr>
            <tr>
              <td>HITL pending</td>
              <td align="right">
                <code>{oq.hitl_pending}</code>
              </td>
              <td>Pending issues</td>
              <td align="right">
                <code>{oq.pending_issues_total}</code>
              </td>
              <td colSpan={2}></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Honest gaps */}
      {honest_gaps.length > 0 && (
        <div className="card" style={{ marginTop: 16, borderLeft: '4px solid #888' }}>
          <strong>Honest gaps</strong>
          <ul style={{ margin: '8px 0 0 16px', fontSize: 12, color: '#666' }}>
            {honest_gaps.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Links */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>Drill-down links</strong>
        <ul style={{ margin: '8px 0 0 16px', fontSize: 13 }}>
          {Object.entries(d.links).map(([label, href]) => (
            <li key={label}>
              <code>{label}</code> → <a href={href}>{href}</a>
            </li>
          ))}
        </ul>
      </div>

      <p style={{ marginTop: 16, fontSize: 11, color: '#888' }}>
        correlation_id=<code>{resp.correlation_id}</code> · generated_at=
        <code>{new Date(d.generated_at * 1000).toISOString()}</code>
      </p>
    </div>
  );
}
