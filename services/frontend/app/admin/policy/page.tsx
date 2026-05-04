'use client';

/**
 * /admin/policy — PolisAI policy engine surface.
 *
 * Renders the read-only output from /api/v1/policy. Per §49 compose
 * footer pattern. Auto-refresh every 5s when toggled.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type PolicyRule = {
  rule_id: string;
  actor: string;
  tool: string;
  scope_required: string[];
  effect: 'allow' | 'deny';
};

type PolicyDecision = {
  allow: boolean;
  rule_matched: string;
  reason: string;
  actor: string;
  tool: string;
  scope_required: string[];
  scope_granted: string[];
  missing_scopes: string[];
  policy_version: string;
  timestamp: number;
};

type ApiPayload = {
  data: {
    policy_id: string;
    policy_version: string;
    default_effect: 'allow' | 'deny';
    rule_count: number;
    rules: PolicyRule[];
    recent_decisions: PolicyDecision[];
    decision_stats: {
      total: number;
      allow: number;
      deny: number;
      allow_rate: number;
      by_rule: Record<string, number>;
    };
  };
  correlation_id: string;
};

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function effectColor(effect: string): { bg: string; fg: string } {
  if (effect === 'allow') return { bg: '#dff2dd', fg: '#1f8a4c' };
  return { bg: '#fdeaea', fg: '#a4262c' };
}

function fmtTimestamp(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function PolicyPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [filter, setFilter] = useState<'all' | 'allow' | 'deny'>('all');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/policy?limit=100', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      const j = (await r.json()) as ApiPayload;
      setPayload(j);
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

  const filteredDecisions = payload?.data.recent_decisions.filter((d) => {
    if (filter === 'all') return true;
    if (filter === 'allow') return d.allow;
    return !d.allow;
  });

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>PolisAI Policy</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · default-deny · §38 audit
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
        Layer 4 of the 11-layer architecture. Default-deny policy engine
        gating every (actor, tool, scopes) triple. Source:{' '}
        <code>config/policies/agent_dispatch.json</code> · audit:{' '}
        <code>.loop/policy_audit.jsonl</code>.
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

      {payload && (
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
                Policy version
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {payload.data.policy_version}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Rules
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {payload.data.rule_count} ·{' '}
                <span style={{ fontSize: '0.85rem', color: '#a4262c' }}>
                  default-{payload.data.default_effect}
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Decisions logged
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {payload.data.decision_stats.total}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Allow rate
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {fmtPct(payload.data.decision_stats.allow_rate)} ·{' '}
                <span style={{ fontSize: '0.85rem', color: '#666' }}>
                  {payload.data.decision_stats.allow}/{payload.data.decision_stats.total}
                </span>
              </div>
            </div>
          </section>

          {/* Rules catalog */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Rules ({payload.data.rule_count})</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Rule ID</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Actor</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Tool</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Scopes Required</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Effect</th>
                </tr>
              </thead>
              <tbody>
                {payload.data.rules.map((r) => {
                  const c = effectColor(r.effect);
                  return (
                    <tr key={r.rule_id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: 6 }}><code>{r.rule_id}</code></td>
                      <td style={{ padding: 6 }}><code>{r.actor}</code></td>
                      <td style={{ padding: 6 }}><code>{r.tool}</code></td>
                      <td style={{ padding: 6 }}>
                        {r.scope_required.map((s) => (
                          <span
                            key={s}
                            style={{
                              display: 'inline-block',
                              padding: '1px 6px',
                              margin: '1px 4px 1px 0',
                              background: '#eef',
                              borderRadius: 3,
                              fontSize: '0.8rem',
                            }}
                          >
                            <code>{s}</code>
                          </span>
                        ))}
                      </td>
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
                          {r.effect}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Recent decisions */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>
                Recent decisions ({filteredDecisions?.length ?? 0})
              </h3>
              <div style={{ display: 'flex', gap: 4 }}>
                {(['all', 'allow', 'deny'] as const).map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setFilter(opt)}
                    style={{
                      background: filter === opt ? '#444' : '#fff',
                      color: filter === opt ? '#fff' : '#444',
                      border: '1px solid #ccc',
                      padding: '4px 10px',
                      borderRadius: 3,
                      cursor: 'pointer',
                    }}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
            {filteredDecisions && filteredDecisions.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    <th style={{ textAlign: 'left', padding: 6 }}>Time</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Effect</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Actor</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Tool</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Rule</th>
                    <th style={{ textAlign: 'left', padding: 6 }}>Missing scopes</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDecisions.map((d, i) => {
                    const c = effectColor(d.allow ? 'allow' : 'deny');
                    return (
                      <tr key={`${d.timestamp}-${i}`} style={{ borderBottom: '1px solid #eee' }}>
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
                        <td style={{ padding: 6 }}><code>{d.tool}</code></td>
                        <td style={{ padding: 6 }}><code>{d.rule_matched}</code></td>
                        <td style={{ padding: 6 }}>
                          {d.missing_scopes && d.missing_scopes.length > 0
                            ? d.missing_scopes.join(', ')
                            : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#666', fontStyle: 'italic' }}>No decisions match the filter.</p>
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
                <Link href="/admin/paperclip">Paperclip</Link> — every snapshot
                read goes through the <code>snapshot:read</code> rule.
              </li>
              <li>
                <Link href="/admin/local-models">Local models</Link> — every
                Ollama council call goes through{' '}
                <code>council:*-ollama-generate</code> rules.
              </li>
              <li>
                <Link href="/admin/agentic">Agentic framework</Link> — PolisAI is
                the policy gate of the 11-layer architecture.
              </li>
              <li>
                <Link href="/admin/explainability">Explainability</Link> — every
                policy decision row is part of the §48.4 audit trail.
              </li>
              <li>
                <Link href="/admin/vectorless-elasticsearch">Vectorless RAG</Link>{' '}
                — the <code>retrieve:vectorless</code> scope (Stage-2) gates
                this retrieval mode.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Stage-2 will swap the Python evaluator for OPA + Rego (Tier 6
              #6.1); the audit row schema stays — drill enforces the contract,
              not the implementation.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
