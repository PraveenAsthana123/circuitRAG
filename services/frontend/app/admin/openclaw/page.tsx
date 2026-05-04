'use client';

/**
 * /admin/openclaw — Layer 11 surface (heavy-autonomy A2A coordinator).
 *
 * Renders the agent registry + recent dispatch decisions. Stage-1 is
 * gate-only — every dispatch default-denies until Stage-2 adds rules.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type AgentInfo = {
  capabilities: string[];
  required_scope: string;
  endpoint: string;
};

type DispatchRow = {
  type: string;
  decision: {
    allow: boolean;
    rule_matched: string;
    reason: string;
    requesting_agent: string;
    target_agent: string;
    capability: string;
    timestamp: number;
    dispatch_id: string;
    missing_scopes: string[];
  };
  envelope: unknown;
};

type ApiPayload = {
  data: {
    stage: number;
    agent_count: number;
    agents: Record<string, AgentInfo>;
    recent_dispatches: DispatchRow[];
    stats: {
      total: number;
      allow: number;
      deny: number;
      allow_rate: number;
      by_target: Record<string, number>;
    };
  };
  correlation_id: string;
};

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function effectColor(allow: boolean): { bg: string; fg: string } {
  return allow ? { bg: '#dff2dd', fg: '#1f8a4c' } : { bg: '#fdeaea', fg: '#a4262c' };
}

function fmtTimestamp(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function OpenClawPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/openclaw?limit=100', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      setPayload((await r.json()) as ApiPayload);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [autoRefresh, refresh]);

  const data = payload?.data;

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>OpenClaw — A2A Coordinator</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · gate-only · default-deny
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={refresh} disabled={loading}>
            {loading ? 'refreshing…' : 'refresh'}
          </button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            auto-refresh 5s
          </label>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Layer 11 of the 11-layer architecture — heavy-autonomy A2A
        coordinator. Stage-1 ships gate + envelope contract ONLY; actual
        Dispatch RPC is comment-only in the proto until Stage-2 lands rules
        + drill update. The OPPOSITE of Paperclip (which is read-only sandbox).
        Both go through PolisAI first.
      </p>

      {error && (
        <div
          style={{
            background: '#fdeaea',
            color: '#a4262c',
            padding: 12,
            border: '1px solid #a4262c',
            borderRadius: 4,
            marginBottom: 16,
          }}
        >
          <strong>Error:</strong> {error}
        </div>
      )}

      {data && (
        <>
          {/* Stats headline */}
          <section
            style={{
              padding: 16,
              border: '2px solid #ddd',
              borderRadius: 8,
              marginBottom: 16,
              background: '#fafafa',
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 16,
            }}
          >
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Agents in registry
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{data.agent_count}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Dispatches logged
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{data.stats.total}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Allow rate
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {fmtPct(data.stats.allow_rate)}
                <span style={{ fontSize: '0.85rem', color: '#666', marginLeft: 8 }}>
                  {data.stats.allow}/{data.stats.total}
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Posture
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem', color: '#a4262c' }}>
                default-deny
              </div>
            </div>
          </section>

          {/* Agents registry */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Agent registry ({data.agent_count})</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Agent</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Capabilities</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Required scope</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Endpoint</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.agents).map(([name, info]) => (
                  <tr key={name} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: 6 }}><code>{name}</code></td>
                    <td style={{ padding: 6 }}>
                      {info.capabilities.map((c) => (
                        <span
                          key={c}
                          style={{
                            display: 'inline-block',
                            padding: '1px 6px',
                            margin: '1px 4px 1px 0',
                            background: '#eef',
                            borderRadius: 3,
                            fontSize: '0.8rem',
                          }}
                        >
                          <code>{c}</code>
                        </span>
                      ))}
                    </td>
                    <td style={{ padding: 6 }}><code>{info.required_scope}</code></td>
                    <td style={{ padding: 6, fontSize: '0.8rem', color: '#666' }}>
                      <code>{info.endpoint}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* Recent dispatches */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Recent dispatch attempts ({data.recent_dispatches.length})</h3>
            {data.recent_dispatches.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    <th style={{ textAlign: 'left', padding: 6 }}>Time</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Effect</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>From</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>To</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Capability</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Rule</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Missing scopes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_dispatches.map((d, i) => {
                    const c = effectColor(d.decision.allow);
                    return (
                      <tr key={`${d.decision.dispatch_id}-${i}`} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: 6 }}>{fmtTimestamp(d.decision.timestamp)}</td>
                        <td style={{ padding: 6 }}>
                          <span
                            style={{
                              background: c.bg,
                              color: c.fg,
                              padding: '2px 8px',
                              borderRadius: 3,
                              fontWeight: 600,
                            }}
                          >
                            {d.decision.allow ? 'allow' : 'deny'}
                          </span>
                        </td>
                        <td style={{ padding: 6 }}><code>{d.decision.requesting_agent}</code></td>
                        <td style={{ padding: 6 }}><code>{d.decision.target_agent}</code></td>
                        <td style={{ padding: 6 }}><code>{d.decision.capability}</code></td>
                        <td style={{ padding: 6 }}><code>{d.decision.rule_matched}</code></td>
                        <td style={{ padding: 6 }}>
                          {d.decision.missing_scopes && d.decision.missing_scopes.length > 0
                            ? d.decision.missing_scopes.join(', ')
                            : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#666', fontStyle: 'italic' }}>
                No dispatch attempts yet. Stage-1 sample:{' '}
                <code>python scripts/openclaw_coordinator.py dispatch --from council:author --to council:reviewer --capability critique_proposal</code>
              </p>
            )}
          </section>

          {/* §49 compose footer */}
          <section
            style={{
              padding: 16,
              border: '1px dashed #999',
              borderRadius: 4,
              background: '#f8f8f8',
              fontSize: '0.85rem',
            }}
          >
            <strong>Composes with</strong> (per §49):
            <ul style={{ marginTop: 8 }}>
              <li>
                <Link href="/admin/policy">PolisAI policy</Link> — every
                dispatch goes through PolisAI BEFORE the envelope is built.
              </li>
              <li>
                <Link href="/admin/paperclip">Paperclip</Link> — the OPPOSITE
                of OpenClaw (read-only sandbox vs heavy-autonomy A2A).
              </li>
              <li>
                <Link href="/admin/agent-router">Agent Router</Link> — the
                router classifies before Council; the Council can then dispatch
                via OpenClaw.
              </li>
              <li>
                <Link href="/admin/agentic">Agentic framework</Link> —
                OpenClaw is Layer 11 of the 11-layer architecture.
              </li>
              <li>
                <Link href="/admin/explainability">Explainability</Link> —
                every dispatch decision is part of the §48.4 audit trail.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Stage-2 will add the Dispatch RPC (currently comment-only in{' '}
              <code>proto/openclaw/v1/openclaw.proto</code>) + per-pair circuit
              breaker. Stage-3 wires multi-agent task graph with parallel
              fan-out + reduce + HITL escalation on conflict.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
