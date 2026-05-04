'use client';

/**
 * /admin/adapters — unified surface for the Stage-1 adapter ecosystem.
 *
 * Per §44 + §47. Each adapter follows the same shape (is_available /
 * feature flag / lazy import / drill-locked contract). This page
 * shows them in one place with status + swap target + drill path.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type AdapterStatus = {
  stage: number;
  available: boolean;
  feature_flag: boolean;
  installed: boolean;
  note: string;
};

type AdapterRow = {
  name: string;
  source_path: string;
  drill_path: string;
  feature_flag_env: string;
  source_layer: string;
  swap_target: string;
  status?: AdapterStatus;
  status_error?: string;
};

type ApiPayload = {
  data: {
    adapter_count: number;
    adapters: AdapterRow[];
    all_stage1_present: boolean;
    any_enabled_in_dev: boolean;
  };
  correlation_id: string;
};

function statusBadge(a: AdapterRow): { bg: string; fg: string; label: string } {
  if (a.status_error) return { bg: '#fdeaea', fg: '#a4262c', label: 'error' };
  if (a.status?.available) return { bg: '#dff2dd', fg: '#1f8a4c', label: 'enabled' };
  if (a.status?.installed) return { bg: '#fef3e1', fg: '#c47a1a', label: 'installed · flag off' };
  return { bg: '#f0f0f0', fg: '#666', label: 'Stage-1 stub' };
}

export default function AdaptersPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/adapters', { cache: 'no-store' });
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

  const data = payload?.data;

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Adapter inventory</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · opt-in · drill-locked
        </span>
        <div style={{ marginLeft: 'auto' }}>
          <button onClick={refresh} disabled={loading}>
            {loading ? 'refreshing…' : 'refresh'}
          </button>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Stage-1 adapter ecosystem. Each adapter follows the same shape:
        feature flag (env var) + lazy import + dual exception types
        (Unavailable / runtime error) + drill-locked contract.
        Stage-1 ships the contract; Stage-2 wires the swap as a
        fallback inside the originating layer.
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
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 16,
            }}
          >
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Adapters
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{data.adapter_count}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Stage-1 contracts present
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {data.all_stage1_present ? '✓ all' : '⚠ partial'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Enabled in dev
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {data.any_enabled_in_dev ? '✓ ≥1' : '— none (default)'}
              </div>
            </div>
          </section>

          {/* Adapter cards */}
          {data.adapters.map((a) => {
            const sb = statusBadge(a);
            return (
              <section
                key={a.name}
                style={{
                  padding: 16,
                  border: '1px solid #ddd',
                  borderRadius: 4,
                  marginBottom: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <h3 style={{ margin: 0 }}>{a.name}</h3>
                  <span
                    style={{
                      background: sb.bg,
                      color: sb.fg,
                      padding: '4px 12px',
                      borderRadius: 3,
                      fontWeight: 600,
                    }}
                  >
                    {sb.label}
                  </span>
                  <span
                    style={{
                      fontSize: '0.85rem',
                      color: '#666',
                      marginLeft: 'auto',
                    }}
                  >
                    {a.source_layer}
                  </span>
                </div>

                <div style={{ marginBottom: 8 }}>
                  <strong>Swap target:</strong> {a.swap_target}
                </div>

                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <tbody>
                    <tr>
                      <td style={{ padding: 4, color: '#666', width: 200 }}>Source</td>
                      <td style={{ padding: 4 }}><code>{a.source_path}</code></td>
                    </tr>
                    <tr>
                      <td style={{ padding: 4, color: '#666' }}>Drill</td>
                      <td style={{ padding: 4 }}><code>{a.drill_path}</code></td>
                    </tr>
                    <tr>
                      <td style={{ padding: 4, color: '#666' }}>Feature flag</td>
                      <td style={{ padding: 4 }}>
                        <code>{a.feature_flag_env}=1</code>
                      </td>
                    </tr>
                    <tr>
                      <td style={{ padding: 4, color: '#666' }}>Status</td>
                      <td style={{ padding: 4 }}>
                        {a.status_error ? (
                          <span style={{ color: '#a4262c' }}>ERROR: {a.status_error}</span>
                        ) : a.status ? (
                          <>
                            stage <strong>{a.status.stage}</strong> · available{' '}
                            <strong>{a.status.available ? 'true' : 'false'}</strong> ·{' '}
                            flag <strong>{a.status.feature_flag ? 'on' : 'off'}</strong> ·{' '}
                            installed <strong>{a.status.installed ? 'yes' : 'no'}</strong>
                          </>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                    {a.status?.note && (
                      <tr>
                        <td style={{ padding: 4, color: '#666', verticalAlign: 'top' }}>Note</td>
                        <td style={{ padding: 4, fontSize: '0.8rem', color: '#666' }}>
                          {a.status.note}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </section>
            );
          })}

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
                <Link href="/admin/local-models">Local models</Link> — LiteLLM
                replaces direct curl-to-Ollama on this layer.
              </li>
              <li>
                <Link href="/admin/policy">PolisAI policy</Link> — every adapter
                preserves the PolisAI gate ordering invariant.
              </li>
              <li>
                <Link href="/admin/kafka-events">Kafka events</Link> — the
                event_publisher adapter publishes audit rows when enabled.
              </li>
              <li>
                <Link href="/admin/tool-evaluation">Tool evaluation</Link> —
                LiteLLM + PydanticAI were the #1 + #2 actionable
                recommendations from this analysis.
              </li>
              <li>
                <Link href="/admin/pr-management">PR management</Link> — adapter
                Stage-2 wirings ship as their own commits in the queue.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Stage-3 promotions: empirical eval → flip default for the
              winning path. Each adapter has its own Stage-3 plan in its
              source-file docstring.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
