'use client';

/**
 * /admin/mcp-gateway — operator surface for the MCP Gateway.
 *
 * Per §47 + §56. Renders allowlist + recent decisions + risk
 * breakdown. Read-only — adding servers is the §56 process, not HTTP.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type AllowlistServer = {
  name: string;
  module: string;
  risk: 'low' | 'medium' | 'high' | 'critical';
  approved_actors: string[];
  max_calls_per_minute: number;
  rationale: string;
};

type GatewayDecision = {
  allow: boolean;
  reason: string;
  actor: string;
  server: string;
  tool: string;
  risk: string;
  rule_matched: string;
  timestamp: number;
  request_id: string;
};

type ApiPayload = {
  data: {
    status: {
      stage: number;
      enabled: boolean;
      server_count: number;
      by_risk: Record<string, number>;
      audit_log: string;
      allowlist_path: string;
      note: string;
    };
    allowlist: {
      policy_version: string;
      default_decision: string;
      servers: AllowlistServer[];
    };
    recent_decisions: GatewayDecision[];
    stats: {
      total: number;
      allow: number;
      deny: number;
      allow_rate: number;
      by_server: Record<string, number>;
    };
  };
  correlation_id: string;
};

const RISK_STYLE: Record<string, { bg: string; fg: string }> = {
  critical: { bg: '#a4262c', fg: '#fff' },
  high:     { bg: '#fdeaea', fg: '#a4262c' },
  medium:   { bg: '#fef3e1', fg: '#c47a1a' },
  low:      { bg: '#dff2dd', fg: '#1f8a4c' },
};

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function fmtTimestamp(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function MCPGatewayPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/mcp-gateway', { cache: 'no-store' });
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
  const enabledColor = data?.status.enabled
    ? { bg: '#dff2dd', fg: '#1f8a4c' }
    : { bg: '#fef3e1', fg: '#c47a1a' };

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>MCP Gateway</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · default-deny · 4-layer defense
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
        Per the brutal rule: <strong>do not allow direct MCP access</strong>.
        Every MCP call goes through this gateway: feature-flag check + server
        allowlist + approved-actor check + PolisAI gate + rate-limit + audit.
        4-layer defense in depth.
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
          {/* Headline */}
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
                MCP_GATEWAY_ENABLED
              </div>
              <div>
                <span
                  style={{
                    background: enabledColor.bg,
                    color: enabledColor.fg,
                    padding: '4px 12px',
                    borderRadius: 3,
                    fontWeight: 600,
                    fontSize: '1.1rem',
                  }}
                >
                  {data.status.enabled ? 'enabled' : 'disabled (Stage-1 default)'}
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Allowlist servers
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>
                {data.status.server_count}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Decisions logged
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>
                {data.stats.total}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Allow rate
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>
                {fmtPct(data.stats.allow_rate)}
              </div>
            </div>
          </section>

          {/* By-risk breakdown */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Server count by risk tier</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {(['critical', 'high', 'medium', 'low'] as const).map((tier) => {
                const count = data.status.by_risk[tier] || 0;
                const style = RISK_STYLE[tier];
                return (
                  <div
                    key={tier}
                    style={{
                      padding: '6px 12px',
                      border: `2px solid ${style.bg}`,
                      borderRadius: 4,
                      background: '#fff',
                    }}
                  >
                    <span
                      style={{
                        background: style.bg,
                        color: style.fg,
                        padding: '1px 8px',
                        borderRadius: 3,
                        fontWeight: 600,
                        fontSize: '0.8rem',
                        marginRight: 6,
                      }}
                    >
                      {tier}
                    </span>
                    <strong>{count}</strong>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Allowlist table */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>
              Allowlist ({data.allowlist.servers.length} servers · default:{' '}
              <code>{data.allowlist.default_decision}</code>)
            </h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Server</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Risk</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Approved actors</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Rate / min</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Rationale</th>
                </tr>
              </thead>
              <tbody>
                {data.allowlist.servers.map((s) => {
                  const style = RISK_STYLE[s.risk];
                  return (
                    <tr key={s.name} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: 6, fontWeight: 600 }}>{s.name}</td>
                      <td style={{ padding: 6 }}>
                        <span
                          style={{
                            background: style.bg,
                            color: style.fg,
                            padding: '2px 8px',
                            borderRadius: 3,
                            fontWeight: 600,
                            fontSize: '0.8rem',
                          }}
                        >
                          {s.risk}
                        </span>
                      </td>
                      <td style={{ padding: 6, fontSize: '0.8rem' }}>
                        {s.approved_actors.map((a) => (
                          <code
                            key={a}
                            style={{
                              display: 'inline-block',
                              padding: '1px 4px',
                              margin: '1px 4px 1px 0',
                              background: '#eef',
                              borderRadius: 3,
                            }}
                          >
                            {a}
                          </code>
                        ))}
                      </td>
                      <td style={{ padding: 6, textAlign: 'right' }}>{s.max_calls_per_minute}</td>
                      <td style={{ padding: 6, fontSize: '0.8rem', color: '#666' }}>
                        {s.rationale}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Recent decisions */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>
              Recent gateway decisions ({data.recent_decisions.length})
            </h3>
            {data.recent_decisions.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    <th style={{ textAlign: 'left', padding: 6 }}>Time</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Effect</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Actor</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Server</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Tool</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Risk</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Rule</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_decisions.map((d, i) => {
                    const c = d.allow
                      ? { bg: '#dff2dd', fg: '#1f8a4c' }
                      : { bg: '#fdeaea', fg: '#a4262c' };
                    const r = RISK_STYLE[d.risk] || { bg: '#f0f0f0', fg: '#666' };
                    return (
                      <tr key={`${d.request_id}-${i}`} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: 6 }}>{fmtTimestamp(d.timestamp)}</td>
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
                            {d.allow ? 'allow' : 'deny'}
                          </span>
                        </td>
                        <td style={{ padding: 6 }}><code>{d.actor}</code></td>
                        <td style={{ padding: 6 }}><code>{d.server}</code></td>
                        <td style={{ padding: 6 }}><code>{d.tool || '—'}</code></td>
                        <td style={{ padding: 6 }}>
                          <span
                            style={{
                              background: r.bg,
                              color: r.fg,
                              padding: '1px 6px',
                              borderRadius: 3,
                              fontSize: '0.8rem',
                              fontWeight: 600,
                            }}
                          >
                            {d.risk}
                          </span>
                        </td>
                        <td style={{ padding: 6, fontSize: '0.8rem' }}><code>{d.rule_matched}</code></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#666', fontStyle: 'italic' }}>
                No gateway decisions yet. Set <code>MCP_GATEWAY_ENABLED=1</code>{' '}
                and route MCP calls through <code>scripts/mcp_gateway.py check</code>.
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
                <Link href="/admin/policy">PolisAI policy</Link> — gateway fires
                PolisAI gate as part of its 4-layer defense.
              </li>
              <li>
                <Link href="/admin/enterprise-architecture">Enterprise architecture</Link>{' '}
                — this gateway closes 3 of the 17 missing items the page identified.
              </li>
              <li>
                <Link href="/admin/openclaw">OpenClaw</Link> — same
                allowlist+gate+audit pattern, applied to A2A dispatches.
              </li>
              <li>
                <Link href="/admin/techstack-audit">Techstack audit</Link> —
                MCP server modules tracked here are also empirically verified.
              </li>
              <li>
                <Link href="/admin/explainability">Explainability</Link> — every
                gateway decision is part of the §48.4 audit trail.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Stage-2 wires the real RPC dispatch (gateway becomes the single MCP
              ingress). Stage-3 moves rate-limit to Redis-backed for multi-process
              correctness + narrows to PolisAI-rule-only.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
