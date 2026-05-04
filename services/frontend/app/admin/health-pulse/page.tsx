'use client';

/**
 * /admin/health-pulse — full-system live operational dashboard.
 *
 * Synthesizes audit logs from PolisAI / OpenClaw / Router / MCP Gateway /
 * Council / Apply-attempts into one auto-refreshing view. Auto-refresh
 * 5s; the dashboard is the operator's single live-pulse surface.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type LayerStats = {
  layer: string;
  audit_log: string;
  total: number;
  last_minute: number;
  last_hour: number;
  last_day: number;
  allow_rate: number | null;
  recent_5: { ts: number; summary: string }[];
};

type ApiPayload = {
  data: {
    layers: LayerStats[];
    totals: {
      total: number;
      last_minute: number;
      last_hour: number;
      last_day: number;
    };
    observed_at: number;
  };
  correlation_id: string;
};

function fmtAge(seconds: number): string {
  if (seconds < 0 || !Number.isFinite(seconds)) return '—';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function pulseColor(lastMinute: number): { bg: string; fg: string } {
  // High activity in last minute = green; idle = gray
  if (lastMinute > 5) return { bg: '#dff2dd', fg: '#1f8a4c' };
  if (lastMinute > 0) return { bg: '#fef3e1', fg: '#c47a1a' };
  return { bg: '#f0f0f0', fg: '#666' };
}

function allowRateColor(rate: number | null): string {
  if (rate === null) return '#666';
  if (rate >= 0.5) return '#1f8a4c';
  if (rate >= 0.1) return '#c47a1a';
  return '#a4262c';
}

export default function HealthPulsePage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/health-pulse', { cache: 'no-store' });
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
  const now = Date.now() / 1000;

  return (
    <div style={{ padding: '24px', maxWidth: 1400 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Health Pulse</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          live · 6 layers · auto-refresh 5s
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
            auto-refresh
          </label>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Synthesizes audit logs from <strong>6 layers</strong> into one
        operational view. Each layer's pulse-color reflects activity in
        the last minute (green = active, amber = recent, gray = idle).
        Allow-rate badges show authorization signal where applicable.
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
          {/* Totals headline */}
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
                Total events (all-time)
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{data.totals.total}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Last 1 minute
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{data.totals.last_minute}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Last 1 hour
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{data.totals.last_hour}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Last 1 day
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{data.totals.last_day}</div>
            </div>
          </section>

          {/* Per-layer cards */}
          {data.layers.map((layer) => {
            const pc = pulseColor(layer.last_minute);
            const ac = allowRateColor(layer.allow_rate);
            return (
              <section
                key={layer.layer}
                style={{
                  padding: 16,
                  border: '1px solid #ddd',
                  borderRadius: 4,
                  marginBottom: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <h3 style={{ margin: 0 }}>{layer.layer}</h3>
                  <span
                    style={{
                      background: pc.bg,
                      color: pc.fg,
                      padding: '2px 10px',
                      borderRadius: 3,
                      fontWeight: 600,
                      fontSize: '0.8rem',
                    }}
                  >
                    pulse: {layer.last_minute}/min
                  </span>
                  {layer.allow_rate !== null && (
                    <span
                      style={{
                        color: ac,
                        fontWeight: 600,
                        fontSize: '0.85rem',
                      }}
                    >
                      allow rate: {(layer.allow_rate * 100).toFixed(1)}%
                    </span>
                  )}
                  <code style={{ marginLeft: 'auto', fontSize: '0.75rem', color: '#999' }}>
                    .loop/{layer.audit_log}
                  </code>
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(4, auto) 1fr',
                    gap: 16,
                    fontSize: '0.85rem',
                    marginBottom: 8,
                  }}
                >
                  <div>
                    <span style={{ color: '#666' }}>Total: </span>
                    <strong>{layer.total}</strong>
                  </div>
                  <div>
                    <span style={{ color: '#666' }}>1min: </span>
                    <strong>{layer.last_minute}</strong>
                  </div>
                  <div>
                    <span style={{ color: '#666' }}>1hr: </span>
                    <strong>{layer.last_hour}</strong>
                  </div>
                  <div>
                    <span style={{ color: '#666' }}>1day: </span>
                    <strong>{layer.last_day}</strong>
                  </div>
                </div>

                {layer.recent_5.length > 0 && (
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ cursor: 'pointer', color: '#666', fontSize: '0.85rem' }}>
                      Last {layer.recent_5.length} events
                    </summary>
                    <table
                      style={{
                        width: '100%',
                        borderCollapse: 'collapse',
                        fontSize: '0.8rem',
                        marginTop: 4,
                      }}
                    >
                      <tbody>
                        {layer.recent_5.map((row, i) => (
                          <tr
                            key={`${row.ts}-${i}`}
                            style={{ borderBottom: '1px solid #eee' }}
                          >
                            <td style={{ padding: 4, color: '#666', whiteSpace: 'nowrap' }}>
                              {fmtAge(now - row.ts)} ago
                            </td>
                            <td style={{ padding: 4 }}>
                              <code>{row.summary}</code>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </details>
                )}
              </section>
            );
          })}

          {/* §49 footer */}
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
                <Link href="/admin/policy">PolisAI policy</Link> — drill into
                policy decisions when allow rate drops.
              </li>
              <li>
                <Link href="/admin/openclaw">OpenClaw</Link> — A2A dispatch
                detail when the OpenClaw row spikes.
              </li>
              <li>
                <Link href="/admin/agent-router">Agent Router</Link> — routing
                trace when intent classifications surge.
              </li>
              <li>
                <Link href="/admin/mcp-gateway">MCP Gateway</Link> — gateway
                drill-down when MCP calls spike.
              </li>
              <li>
                <Link href="/admin/paperclip">Paperclip</Link> — apply-rate
                detail (this page shows the headline; paperclip the table).
              </li>
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
