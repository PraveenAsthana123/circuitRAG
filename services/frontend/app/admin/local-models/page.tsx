'use client';

import { useEffect, useState, useCallback } from 'react';

type ModelInfo = { name: string; size_bytes?: number; size_vram?: number; modified?: string; expires?: string };
type AuditRow = {
  ts?: string;
  id?: string;
  lane?: string;
  outcome?: string;
  model?: string;
  tokens?: number;
  latency_s?: number;
  chain?: Record<string, { model: string; tokens: number; latency_s: number }>;
};
type ProviderRow = {
  provider: string;
  attempted: number;
  applied: number;
  apply_rate: number;
  avg_latency_s: number;
  latency_samples?: number;
  note?: string;
};
type ProviderComparison = {
  version: string;
  generated_at: number;
  window_days: number;
  providers: ProviderRow[];
  totals: { attempted: number; applied: number; apply_rate: number };
  honest_gaps: string[];
  bottleneck_signal: {
    signal_active: boolean;
    reason: string;
    suggested_action?: string;
    policy_ref?: string;
  };
};
type Snapshot = {
  data: {
    installed: ModelInfo[];
    loaded: ModelInfo[];
    installed_count: number;
    loaded_count: number;
    recent_audit: AuditRow[];
    checklist_summary: { total: number; by_difficulty: Record<string, number>; by_assignee: Record<string, number> };
    council_batch_summary: unknown;
    provider_comparison: ProviderComparison;
    ollama_base: string;
  };
  correlation_id: string;
};

function fmtBytes(n?: number): string {
  if (!n) return '—';
  const gb = n / 1024 / 1024 / 1024;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(n / 1024 / 1024).toFixed(0)} MB`;
}

function fmtTime(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString();
}

export default function LocalModelsPage() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/local-models', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setSnap(j);
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
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [autoRefresh, refresh]);

  if (error) return <div style={{ padding: 20, color: '#c33' }}>Error: {error}</div>;
  if (!snap) return <div style={{ padding: 20 }}>Loading…</div>;

  const d = snap.data;
  const auditWithChain = d.recent_audit.filter((a) => a.chain);
  const auditSingle = d.recent_audit.filter((a) => !a.chain);

  return (
    <div style={{ padding: 20 }}>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Local models — operator dashboard</h1>
          <p className="page-subtitle">
            Live view of Ollama installed + loaded models, recent local-model
            invocations, council batch state, and issue checklist breakdown.
            Backed by <code>/api/v1/local-models</code>. Auto-refresh every 5s.
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

      {d.provider_comparison && (
        <div
          className="card"
          style={{
            marginTop: 16,
            borderLeft: d.provider_comparison.bottleneck_signal.signal_active
              ? '4px solid #c33'
              : '4px solid #393',
          }}
        >
          <strong>
            Provider comparison — apply-rate by provider (last{' '}
            {d.provider_comparison.window_days}d)
          </strong>
          <p style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
            Per CLAUDE.md §55.3 outcome contract: this is the brutal-honesty
            signal that shows which provider lane is actually closing issues
            vs running theatrical loops. Source:{' '}
            <code>scripts/agent_task_registry.py</code>.
          </p>
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
              {d.provider_comparison.providers.map((p) => (
                <tr key={p.provider}>
                  <td>
                    <code>{p.provider}</code>
                    {p.note && (
                      <div style={{ fontSize: 11, color: '#888' }}>{p.note}</div>
                    )}
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
                    {p.latency_samples && p.latency_samples > 0
                      ? `${p.avg_latency_s.toFixed(1)}s (n=${p.latency_samples})`
                      : '—'}
                  </td>
                </tr>
              ))}
              <tr style={{ borderTop: '1px solid #ccc', fontWeight: 600 }}>
                <td>TOTAL</td>
                <td align="right">{d.provider_comparison.totals.attempted}</td>
                <td align="right">{d.provider_comparison.totals.applied}</td>
                <td align="right">
                  {(d.provider_comparison.totals.apply_rate * 100).toFixed(2)}%
                </td>
                <td>—</td>
              </tr>
            </tbody>
          </table>
          <div
            style={{
              marginTop: 12,
              padding: 8,
              background: d.provider_comparison.bottleneck_signal.signal_active
                ? '#fee'
                : '#efe',
              borderRadius: 4,
              fontSize: 12,
            }}
          >
            <strong>
              Bottleneck signal:{' '}
              {d.provider_comparison.bottleneck_signal.signal_active
                ? 'ACTIVE'
                : 'inactive'}
            </strong>
            <div>{d.provider_comparison.bottleneck_signal.reason}</div>
            {d.provider_comparison.bottleneck_signal.suggested_action && (
              <div style={{ marginTop: 4 }}>
                <strong>Action:</strong>{' '}
                {d.provider_comparison.bottleneck_signal.suggested_action}
              </div>
            )}
            {d.provider_comparison.bottleneck_signal.policy_ref && (
              <div style={{ marginTop: 2, color: '#666' }}>
                Reference:{' '}
                <code>{d.provider_comparison.bottleneck_signal.policy_ref}</code>
              </div>
            )}
          </div>
          {d.provider_comparison.honest_gaps.length > 0 && (
            <div style={{ marginTop: 8, fontSize: 11, color: '#888' }}>
              <strong>Honest gaps:</strong>
              <ul style={{ margin: '4px 0 0 16px' }}>
                {d.provider_comparison.honest_gaps.map((gap, i) => (
                  <li key={i}>{gap}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <strong>Models in VRAM right now ({d.loaded_count})</strong>
        {d.loaded_count === 0 ? (
          <p style={{ marginTop: 8, color: '#666' }}>(no model currently loaded; will load on next invocation)</p>
        ) : (
          <table style={{ width: '100%', marginTop: 8 }}>
            <thead>
              <tr><th align="left">Model</th><th align="right">VRAM</th><th align="left">Expires</th></tr>
            </thead>
            <tbody>
              {d.loaded.map((m) => (
                <tr key={m.name}>
                  <td><code>{m.name}</code></td>
                  <td align="right">{fmtBytes(m.size_vram)}</td>
                  <td>{m.expires || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <strong>Installed models ({d.installed_count}) — Ollama base: <code>{d.ollama_base}</code></strong>
        <table style={{ width: '100%', marginTop: 8 }}>
          <thead>
            <tr><th align="left">Model</th><th align="right">Size</th><th align="left">Modified</th></tr>
          </thead>
          <tbody>
            {d.installed.map((m) => (
              <tr key={m.name}>
                <td><code>{m.name}</code></td>
                <td align="right">{fmtBytes(m.size_bytes)}</td>
                <td>{fmtTime(m.modified)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <strong>Issue checklist — {d.checklist_summary.total} total</strong>
        <div style={{ display: 'flex', gap: 24, marginTop: 8 }}>
          <div>
            <div style={{ fontWeight: 600 }}>By difficulty</div>
            {Object.entries(d.checklist_summary.by_difficulty).map(([k, v]) => (
              <div key={k}><code>{k}</code>: {v}</div>
            ))}
          </div>
          <div>
            <div style={{ fontWeight: 600 }}>By assignee</div>
            {Object.entries(d.checklist_summary.by_assignee).map(([k, v]) => (
              <div key={k}><code>{k}</code>: {v}</div>
            ))}
          </div>
        </div>
      </div>

      {auditWithChain.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <strong>Recent council runs ({auditWithChain.length})</strong>
          <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
            <thead>
              <tr>
                <th align="left">When</th>
                <th align="left">Issue</th>
                <th align="left">Author</th>
                <th align="left">Reviewer</th>
                <th align="left">Advisor</th>
                <th align="left">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {auditWithChain.slice(-10).reverse().map((a, idx) => (
                <tr key={idx}>
                  <td>{fmtTime(a.ts)}</td>
                  <td><code>{a.id?.slice(0, 40)}…</code></td>
                  <td>{a.chain?.author?.tokens ?? '—'}t / {a.chain?.author?.latency_s ?? '—'}s</td>
                  <td>{a.chain?.reviewer?.tokens ?? '—'}t / {a.chain?.reviewer?.latency_s ?? '—'}s</td>
                  <td>{a.chain?.advisor?.tokens ?? '—'}t / {a.chain?.advisor?.latency_s ?? '—'}s</td>
                  <td>{a.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {auditSingle.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <strong>Recent single-model proposals ({auditSingle.length})</strong>
          <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
            <thead>
              <tr><th align="left">When</th><th align="left">Issue</th><th align="left">Lane</th><th align="right">Tokens</th><th align="right">Latency</th><th align="left">Outcome</th></tr>
            </thead>
            <tbody>
              {auditSingle.slice(-10).reverse().map((a, idx) => (
                <tr key={idx}>
                  <td>{fmtTime(a.ts)}</td>
                  <td><code>{a.id?.slice(0, 40)}…</code></td>
                  <td>{a.lane}</td>
                  <td align="right">{a.tokens ?? '—'}</td>
                  <td align="right">{a.latency_s ? `${a.latency_s}s` : '—'}</td>
                  <td>{a.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {d.council_batch_summary !== null && (
        <div className="card" style={{ marginTop: 16 }}>
          <strong>Latest council batch summary</strong>
          <pre style={{ marginTop: 8, fontSize: 12, overflow: 'auto', maxHeight: 300 }}>
            {JSON.stringify(d.council_batch_summary, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
