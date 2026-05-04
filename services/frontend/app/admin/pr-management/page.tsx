'use client';

/**
 * /admin/pr-management — push-queue surface.
 *
 * Shows unpushed-commit count + per-type breakdown + recent commits.
 * Read-only — pushing/creating PRs are §42-gated CLI operations.
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type CommitRow = {
  sha: string;
  short_sha: string;
  subject: string;
  type: string;
  age_seconds: number;
  iso_date: string;
};

type ApiPayload = {
  data: {
    unpushed_count: number;
    head_branch: string;
    last_push_age_s: number;
    recent_unpushed_commits: CommitRow[];
    by_type: Record<string, number>;
    push_command: string;
    push_warning: string;
  };
  correlation_id: string;
};

const TYPE_COLORS: Record<string, string> = {
  feat: '#1f8a4c',
  fix: '#a4262c',
  docs: '#0061a4',
  test: '#7e57c2',
  chore: '#666',
  refactor: '#c47a1a',
  unknown: '#999',
};

function fmtAge(seconds: number): string {
  if (seconds < 0) return '—';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

export default function PRManagementPage() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/pr-management', { cache: 'no-store' });
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
  // Pressure indicator: >50 unpushed = red, 10-50 = amber, <10 = green
  const pressureColor = data
    ? data.unpushed_count > 50
      ? { bg: '#fdeaea', fg: '#a4262c' }
      : data.unpushed_count > 10
      ? { bg: '#fef3e1', fg: '#c47a1a' }
      : { bg: '#dff2dd', fg: '#1f8a4c' }
    : { bg: '#666', fg: '#fff' };

  return (
    <div style={{ padding: '24px', maxWidth: 1300 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>PR Management — push queue</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          §42 gated · read-only surface
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
            auto-refresh 30s
          </label>
        </div>
      </header>

      <p style={{ color: '#666', marginTop: 0 }}>
        Read-only push-queue surface. Pushing is §42-gated{' '}
        (<strong>operator-gated</strong>) — operator runs{' '}
        <code>bash scripts/run.sh push --confirm</code>{' '}
        OR <code>python scripts/pr_management.py create --confirm</code>.
        This page never pushes; it just makes the queue visible so the
        operator's push decision is data-driven.
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
                Unpushed commits
              </div>
              <div>
                <span
                  style={{
                    background: pressureColor.bg,
                    color: pressureColor.fg,
                    padding: '4px 16px',
                    borderRadius: 3,
                    fontWeight: 600,
                    fontSize: '1.5rem',
                  }}
                >
                  {data.unpushed_count}
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Branch
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                <code>{data.head_branch}</code>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Last push age
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {fmtAge(data.last_push_age_s)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
                Commit types
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                {Object.keys(data.by_type).length}
              </div>
            </div>
          </section>

          {/* By-type breakdown */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Commits by type</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {Object.entries(data.by_type)
                .sort(([, a], [, b]) => b - a)
                .map(([type, count]) => {
                  const color = TYPE_COLORS[type] || TYPE_COLORS.unknown;
                  return (
                    <div
                      key={type}
                      style={{
                        padding: '6px 12px',
                        border: `2px solid ${color}`,
                        borderRadius: 4,
                        background: '#fff',
                      }}
                    >
                      <strong style={{ color }}>{type}</strong>:{' '}
                      <span style={{ fontWeight: 600 }}>{count}</span>
                    </div>
                  );
                })}
            </div>
          </section>

          {/* Push gate (operator instructions) */}
          <section
            style={{
              padding: 16,
              border: '1px solid #c47a1a',
              borderRadius: 4,
              background: '#fef3e1',
              marginBottom: 16,
            }}
          >
            <h3 style={{ marginTop: 0, color: '#c47a1a' }}>§42 push gate</h3>
            <p style={{ margin: '8px 0' }}>
              <strong>{data.push_warning}</strong>
            </p>
            <p style={{ margin: '8px 0', fontSize: '0.9rem' }}>
              Run from terminal:
            </p>
            <pre
              style={{
                background: '#fff',
                padding: 8,
                fontSize: '0.85rem',
                overflow: 'auto',
                margin: '4px 0',
              }}
            >
              {data.push_command}
            </pre>
            <p style={{ margin: '8px 0', fontSize: '0.85rem', color: '#666' }}>
              OR for PR creation (gh CLI required + double-gated per §42):
            </p>
            <pre
              style={{
                background: '#fff',
                padding: 8,
                fontSize: '0.85rem',
                overflow: 'auto',
                margin: '4px 0',
              }}
            >
              python scripts/pr_management.py preview     # dry-run; show body
              {'\n'}python scripts/pr_management.py create --confirm   # actual PR
            </pre>
          </section>

          {/* Recent commits table */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>
              Recent unpushed commits (last {data.recent_unpushed_commits.length})
            </h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Age</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>SHA</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Type</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Subject</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_unpushed_commits.map((c) => {
                  const color = TYPE_COLORS[c.type] || TYPE_COLORS.unknown;
                  return (
                    <tr key={c.sha} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: 6, color: '#666' }}>{fmtAge(c.age_seconds)}</td>
                      <td style={{ padding: 6 }}>
                        <code style={{ fontSize: '0.8rem' }}>{c.short_sha}</code>
                      </td>
                      <td style={{ padding: 6 }}>
                        <span style={{ color, fontWeight: 600 }}>{c.type}</span>
                      </td>
                      <td style={{ padding: 6 }}>{c.subject}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
                <Link href="/admin/paperclip">Paperclip</Link> — apply-rate
                signal informs whether commits are landing real fixes.
              </li>
              <li>
                <Link href="/admin/policy">PolisAI policy</Link> — every push
                requires the <code>operator:write + git:push + confirm:42</code>
                {' '}scope triple.
              </li>
              <li>
                <Link href="/admin/checklist">Checklist</Link> — issues that the
                committed work resolves are tracked here.
              </li>
              <li>
                <Link href="/admin/explainability">Explainability</Link> — every
                commit carries §51 forensic substrate (Location · Approach ·
                Policies · Verification).
              </li>
              <li>
                <Link href="/admin/architect">Architect</Link> — push affects
                the production blast radius; architect gate applies for
                arch-level changes.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              The §42 boundary is non-negotiable: this page never pushes.
              Operator runs the CLI command after reviewing the queue.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
