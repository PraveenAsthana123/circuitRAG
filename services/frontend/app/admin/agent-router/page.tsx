'use client';

/**
 * /admin/agent-router — Layer 3 surface (intent + risk classifier).
 *
 * Renders the heuristic patterns + recent classifications. §49 footer.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type Pattern = {
  regex: string;
  intent: string;
  actor: string;
  tool: string;
};

type Classification = {
  intent: string;
  risk: 'low' | 'medium' | 'high' | 'unknown';
  recommended_actor: string;
  recommended_tool: string;
  confidence: number;
  reasons: string[];
  timestamp: number;
};

type ApiPayload = {
  data: {
    stage: number;
    high_risk_count: number;
    medium_risk_count: number;
    low_risk_count: number;
    patterns: { high: Pattern[]; medium: Pattern[]; low: Pattern[] };
    recent_classifications: Classification[];
    stats: {
      total: number;
      by_risk: Record<string, number>;
      by_intent: Record<string, number>;
    };
  };
  correlation_id: string;
};

function riskColor(risk: string): { bg: string; fg: string } {
  if (risk === 'high' || risk === 'unknown') return { bg: '#fdeaea', fg: '#a4262c' };
  if (risk === 'medium') return { bg: '#fef3e1', fg: '#c47a1a' };
  return { bg: '#dff2dd', fg: '#1f8a4c' };
}

function fmtTimestamp(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function AgentRouterPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/agent-router?limit=100', { cache: 'no-store' });
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
  const totalPatterns = data
    ? data.high_risk_count + data.medium_risk_count + data.low_risk_count
    : 0;

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Agent Router</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · heuristic · conservative-default
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
        Layer 3 of the 11-layer architecture. Heuristic intent + risk classifier.
        Source: <code>scripts/agent_router.py</code> · audit:{' '}
        <code>.loop/agent_router_audit.jsonl</code>. Stage-2 swaps the
        heuristic body for an Ollama call (qwen2.5) with the same contract.
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
              gridTemplateColumns: 'repeat(5, 1fr)',
              gap: 16,
            }}
          >
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Patterns
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{totalPatterns}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                High-risk patterns
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem', color: '#a4262c' }}>
                {data.high_risk_count}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Decisions logged
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{data.stats.total}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Of those, high-risk
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem', color: '#a4262c' }}>
                {data.stats.by_risk.high || 0}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Conservative default
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {data.stats.by_risk.unknown || 0}
              </div>
            </div>
          </section>

          {/* Patterns table */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Heuristic patterns ({totalPatterns})</h3>
            {(['high', 'medium', 'low'] as const).map((tier) => (
              <div key={tier} style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', fontSize: '0.85rem' }}>
                  {tier} risk ({data.patterns[tier].length})
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ background: '#f0f0f0' }}>
                      <th style={{ textAlign: 'left', padding: 4 }}>Regex</th>
                      <th style={{ textAlign: 'left', padding: 4 }}>Intent</th>
                      <th style={{ textAlign: 'left', padding: 4 }}>Recommended actor</th>
                      <th style={{ textAlign: 'left', padding: 4 }}>Recommended tool</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.patterns[tier].map((p, i) => (
                      <tr key={`${tier}-${i}`} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: 4 }}><code>{p.regex}</code></td>
                        <td style={{ padding: 4 }}>{p.intent}</td>
                        <td style={{ padding: 4 }}><code>{p.actor}</code></td>
                        <td style={{ padding: 4 }}><code>{p.tool}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </section>

          {/* Recent classifications */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Recent classifications ({data.recent_classifications.length})</h3>
            {data.recent_classifications.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    <th style={{ textAlign: 'left', padding: 6 }}>Time</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Risk</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Intent</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Actor</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Tool</th>
                    <th style={{ textAlign: 'right', padding: 6 }}>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_classifications.map((c, i) => {
                    const col = riskColor(c.risk);
                    return (
                      <tr key={`${c.timestamp}-${i}`} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: 6 }}>{fmtTimestamp(c.timestamp)}</td>
                        <td style={{ padding: 6 }}>
                          <span
                            style={{
                              background: col.bg,
                              color: col.fg,
                              padding: '2px 8px',
                              borderRadius: 3,
                              fontWeight: 600,
                            }}
                          >
                            {c.risk}
                          </span>
                        </td>
                        <td style={{ padding: 6 }}><code>{c.intent}</code></td>
                        <td style={{ padding: 6 }}><code>{c.recommended_actor}</code></td>
                        <td style={{ padding: 6 }}><code>{c.recommended_tool}</code></td>
                        <td style={{ padding: 6, textAlign: 'right' }}>
                          {c.confidence.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#666', fontStyle: 'italic' }}>
                No classifications yet — invoke <code>bash scripts/run.sh fix</code>{' '}
                or call agent_router from the council to populate.
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
                router-recommended actor/tool pair must exist as a PolisAI rule.
              </li>
              <li>
                <Link href="/admin/local-models">Local models</Link> — Stage-2
                swaps the heuristic body for a qwen2.5 Ollama call.
              </li>
              <li>
                <Link href="/admin/checklist">Checklist</Link> — issue messages
                from the checklist flow through this classifier.
              </li>
              <li>
                <Link href="/admin/paperclip">Paperclip</Link> — disagreement
                between router + upstream lane assignment lands in the snapshot.
              </li>
              <li>
                <Link href="/admin/explainability">Explainability</Link> — the
                router decision is part of the §48.4 audit row.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Stage-1 contract: cross-check, not gate. Council still runs even
              when router recommends operator:human; disagreement is logged to
              the audit row.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
