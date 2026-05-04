'use client';

/**
 * /admin/techstack-audit — empirical install verification surface.
 *
 * Per §56 gate 4 (empirical install verification). Renders the
 * scripts/techstack_audit.py JSON output as an operator dashboard.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type CheckResult = {
  name: string;
  check: string;
  criticality: 'critical' | 'high' | 'medium' | 'low' | 'todo' | 'rejected';
  installed: boolean;
};

type ApiPayload = {
  data: {
    summary: {
      installed: number;
      missing: number;
      by_criticality: Record<
        string,
        { installed: number; missing: number }
      >;
    };
    sections: Record<string, CheckResult[]>;
  };
  correlation_id: string;
};

const CRITICALITY_STYLE: Record<string, { bg: string; fg: string; order: number }> = {
  critical: { bg: '#a4262c', fg: '#fff', order: 1 },
  high:     { bg: '#fdeaea', fg: '#a4262c', order: 2 },
  medium:   { bg: '#fef3e1', fg: '#c47a1a', order: 3 },
  low:      { bg: '#dff2dd', fg: '#1f8a4c', order: 4 },
  todo:     { bg: '#e0e7ff', fg: '#0061a4', order: 5 },
  rejected: { bg: '#f0f0f0', fg: '#666',    order: 6 },
};

export default function TechstackAuditPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'missing' | 'installed'>('all');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/techstack-audit', { cache: 'no-store' });
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
  const total = data ? data.summary.installed + data.summary.missing : 0;
  const pctInstalled = total > 0 ? (data!.summary.installed / total) * 100 : 0;

  // Build filtered view
  const filteredSections: Record<string, CheckResult[]> = {};
  if (data) {
    for (const [sec, items] of Object.entries(data.sections)) {
      const filtered = items.filter((i) => {
        if (filter === 'all') return true;
        if (filter === 'missing') return !i.installed;
        return i.installed;
      });
      if (filtered.length > 0) {
        filteredSections[sec] = filtered;
      }
    }
  }

  const criticalMissingItems: CheckResult[] = data
    ? Object.values(data.sections).flat().filter(
        (i) => i.criticality === 'critical' && !i.installed,
      )
    : [];

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Techstack Audit — empirical install state</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          §56 gate 4 · live verification
        </span>
        <div style={{ marginLeft: 'auto' }}>
          <button onClick={refresh} disabled={loading}>
            {loading ? 'auditing…' : 'refresh'}
          </button>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Empirical install verification per §56 (techstack-additions policy
        gate 4). Backend: <code>scripts/techstack_audit.py --json</code>.
        Each row is verified live: <code>importlib.util.find_spec</code> for
        Python deps, <code>shutil.which</code> for binaries, <code>package.json</code>{' '}
        scan for npm deps, file-presence for MCP servers.
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
                Total tools
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{total}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Installed
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#1f8a4c' }}>
                {data.summary.installed}{' '}
                <span style={{ fontSize: '0.85rem', color: '#666' }}>
                  ({pctInstalled.toFixed(1)}%)
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Missing
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#a4262c' }}>
                {data.summary.missing}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Critical missing
              </div>
              <div
                style={{
                  fontWeight: 600,
                  fontSize: '1.5rem',
                  color: criticalMissingItems.length > 0 ? '#a4262c' : '#1f8a4c',
                }}
              >
                {criticalMissingItems.length === 0 ? '✓ none' : criticalMissingItems.length}
              </div>
            </div>
          </section>

          {/* By-criticality breakdown */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>By criticality</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {Object.entries(data.summary.by_criticality)
                .sort(
                  ([a], [b]) =>
                    (CRITICALITY_STYLE[a]?.order || 99) -
                    (CRITICALITY_STYLE[b]?.order || 99),
                )
                .map(([crit, stats]) => {
                  const style = CRITICALITY_STYLE[crit] || {
                    bg: '#666',
                    fg: '#fff',
                    order: 99,
                  };
                  const t = stats.installed + stats.missing;
                  return (
                    <div
                      key={crit}
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
                          padding: '1px 6px',
                          borderRadius: 3,
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          marginRight: 6,
                        }}
                      >
                        {crit}
                      </span>
                      <strong>{stats.installed}</strong> / {t} installed
                    </div>
                  );
                })}
            </div>
          </section>

          {/* Filter */}
          <section style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <strong>Filter:</strong>
            {(['all', 'missing', 'installed'] as const).map((opt) => (
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
          </section>

          {/* Sections */}
          {Object.entries(filteredSections).map(([secName, items]) => (
            <section
              key={secName}
              style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 12 }}
            >
              <h3 style={{ marginTop: 0 }}>
                {secName.replace(/_/g, ' ')} ({items.length})
              </h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    <th style={{ textAlign: 'left', padding: 4 }}>Tool</th>
                    <th style={{ textAlign: 'left', padding: 4 }}>Check</th>
                    <th style={{ textAlign: 'left', padding: 4 }}>Criticality</th>
                    <th style={{ textAlign: 'left', padding: 4 }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const style = CRITICALITY_STYLE[item.criticality] || {
                      bg: '#666',
                      fg: '#fff',
                      order: 99,
                    };
                    return (
                      <tr key={item.name} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: 4, fontWeight: 600 }}>{item.name}</td>
                        <td style={{ padding: 4, fontSize: '0.8rem', color: '#666' }}>
                          <code>{item.check}</code>
                        </td>
                        <td style={{ padding: 4 }}>
                          <span
                            style={{
                              background: style.bg,
                              color: style.fg,
                              padding: '1px 6px',
                              borderRadius: 3,
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            {item.criticality}
                          </span>
                        </td>
                        <td style={{ padding: 4 }}>
                          {item.installed ? (
                            <span style={{ color: '#1f8a4c', fontWeight: 600 }}>✓ installed</span>
                          ) : (
                            <span style={{ color: '#a4262c', fontWeight: 600 }}>✗ missing</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          ))}

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
                <Link href="/admin/enterprise-architecture">Enterprise architecture</Link>{' '}
                — documents intended state; this page verifies actual state.
              </li>
              <li>
                <Link href="/admin/adapters">Adapter inventory</Link> — when a Stage-1
                adapter shows installed=true here, its adapter status flips green.
              </li>
              <li>
                <Link href="/admin/tool-evaluation">Tool evaluation</Link> — verdicts
                here drive the criticality assignments shown above (rejected tools
                must NEVER appear with installed=true).
              </li>
              <li>
                <Link href="/admin/eval-harness">Eval harness</Link> — surfaces the
                Stage-1 scaffolds for ragas/guardrails/deepeval/snyk that this audit
                checks.
              </li>
              <li>
                <Link href="/admin/local-models">Local models</Link> — Ollama binary
                + model availability is part of this audit.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Per §56 gate 4: this is the empirical verification step. Any new tool
              addition must appear here with installed=true before the dep is pinned.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
