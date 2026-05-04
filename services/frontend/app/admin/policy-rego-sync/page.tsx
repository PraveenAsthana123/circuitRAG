'use client';

/**
 * /admin/policy-rego-sync — JSON ↔ Rego drift detector.
 *
 * Per §43 + §47. PolisAI Stage-2 ships JSON + Rego; this page is the
 * operator surface that flags drift between them. Auto-refresh 30s.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type ApiPayload = {
  data: {
    json_rule_count: number;
    rego_rule_count: number;
    in_sync: boolean;
    json_only: [string, string, string[]][];
    rego_only: [string, string, string[]][];
    exit_code: number;
  };
  correlation_id: string;
};

export default function PolicyRegoSyncPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/policy-rego-sync', { cache: 'no-store' });
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
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, [autoRefresh, refresh]);

  const data = payload?.data;
  const syncColor = data?.in_sync
    ? { bg: '#dff2dd', fg: '#1f8a4c' }
    : { bg: '#fdeaea', fg: '#a4262c' };

  return (
    <div style={{ padding: '24px', maxWidth: 1200 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Policy JSON ↔ Rego Sync</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          PolisAI Stage-2 · drift detector
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={refresh} disabled={loading}>
            {loading ? 'checking…' : 'refresh'}
          </button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            auto-refresh 30s
          </label>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Verifies that <code>config/policies/agent_dispatch.json</code>{' '}
        (runtime source-of-truth) and{' '}
        <code>config/policies/agent_dispatch.rego</code>{' '}
        (Stage-3 OPA-ready scaffold) stay in semantic sync. Drift here =
        Stage-3 OPA swap will produce different decisions than Stage-1
        Python evaluator. Drill <code>drill_rego_sync.py</code> enforces
        sync at CI time; this page surfaces it visually.
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
          {/* Sync verdict headline */}
          <section
            style={{
              padding: 16,
              border: '2px solid #ddd',
              borderRadius: 8,
              marginBottom: 16,
              background: '#fafafa',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                  Sync verdict
                </div>
                <span
                  style={{
                    background: syncColor.bg,
                    color: syncColor.fg,
                    padding: '6px 16px',
                    borderRadius: 3,
                    fontWeight: 600,
                    fontSize: '1.5rem',
                  }}
                >
                  {data.in_sync ? '✓ in sync' : '✗ DRIFT'}
                </span>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                  JSON rules
                </div>
                <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{data.json_rule_count}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                  Rego rules
                </div>
                <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{data.rego_rule_count}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                  Sync exit code
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    fontSize: '1rem',
                    color: data.exit_code === 0 ? '#1f8a4c' : '#a4262c',
                  }}
                >
                  {data.exit_code} ({data.exit_code === 0 ? 'sync' : data.exit_code === 1 ? 'drift' : 'file missing'})
                </div>
              </div>
            </div>
          </section>

          {/* Drift detail (only when in_sync=false) */}
          {!data.in_sync && (data.json_only.length > 0 || data.rego_only.length > 0) && (
            <section
              style={{
                padding: 16,
                border: '2px solid #a4262c',
                borderRadius: 4,
                background: '#fdeaea',
                marginBottom: 16,
              }}
            >
              <h3 style={{ marginTop: 0, color: '#a4262c' }}>Drift detail</h3>

              {data.json_only.length > 0 && (
                <>
                  <h4>Rules in JSON but missing from Rego</h4>
                  <ul style={{ fontSize: '0.85rem' }}>
                    {data.json_only.map((r, i) => (
                      <li key={`j-${i}`}>
                        actor=<code>{r[0]}</code> · tool=<code>{r[1]}</code> ·
                        scopes=<code>{JSON.stringify(r[2])}</code>
                      </li>
                    ))}
                  </ul>
                  <p style={{ fontSize: '0.85rem' }}>
                    <strong>Fix:</strong> add matching <code>allow {`{`}</code> blocks to
                    <code> config/policies/agent_dispatch.rego</code>.
                  </p>
                </>
              )}

              {data.rego_only.length > 0 && (
                <>
                  <h4>Rules in Rego but missing from JSON</h4>
                  <ul style={{ fontSize: '0.85rem' }}>
                    {data.rego_only.map((r, i) => (
                      <li key={`r-${i}`}>
                        actor=<code>{r[0]}</code> · tool=<code>{r[1]}</code> ·
                        scopes=<code>{JSON.stringify(r[2])}</code>
                      </li>
                    ))}
                  </ul>
                  <p style={{ fontSize: '0.85rem' }}>
                    <strong>Fix:</strong> add matching JSON entries to
                    <code> config/policies/agent_dispatch.json</code>.
                  </p>
                </>
              )}
            </section>
          )}

          {/* Files referenced */}
          <section
            style={{
              padding: 16,
              border: '1px solid #ddd',
              borderRadius: 4,
              marginBottom: 16,
            }}
          >
            <h3 style={{ marginTop: 0 }}>Source-of-truth files</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>File</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Role</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Rule count</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: 6 }}>
                    <code>config/policies/agent_dispatch.json</code>
                  </td>
                  <td style={{ padding: 6 }}>Runtime source (Stage-1 evaluator reads this)</td>
                  <td style={{ padding: 6, textAlign: 'right' }}>
                    <strong>{data.json_rule_count}</strong>
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: 6 }}>
                    <code>config/policies/agent_dispatch.rego</code>
                  </td>
                  <td style={{ padding: 6 }}>Stage-3 scaffold (OPA-ready)</td>
                  <td style={{ padding: 6, textAlign: 'right' }}>
                    <strong>{data.rego_rule_count}</strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </section>

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
                <Link href="/admin/policy">PolisAI policy</Link> — runtime
                evaluator that reads the JSON file (Stage-3 will read Rego).
              </li>
              <li>
                <Link href="/admin/stage-promotions">Stage promotions</Link> —
                PolisAI Stage-2 = this scaffold + sync check.
              </li>
              <li>
                <Link href="/admin/enterprise-architecture">Enterprise architecture</Link>{' '}
                — Layer 4 (PolisAI) Stage-3 plan.
              </li>
              <li>
                <Link href="/admin/health-pulse">Health pulse</Link> — Policy
                decisions live; this page checks the rules behind them.
              </li>
              <li>
                <Link href="/admin/techstack-audit">Techstack audit</Link> —
                OPA binary install status (Stage-3 unblocks when present).
              </li>
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
