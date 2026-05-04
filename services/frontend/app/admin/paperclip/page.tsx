'use client';

/**
 * Paperclip Stage-1 admin page — sandbox manager-layer dashboard.
 *
 * Renders the read-only snapshot from /api/v1/paperclip. The page MUST
 * make the brutal-honesty signal (apply_rate) visually prominent —
 * that's the §55.3 outcome contract surfaced as the headline metric.
 * Composes per §49 with: council, policy, audit, outcome-eval.
 */
import { useCallback, useEffect, useState } from 'react';

type Snapshot = {
  stage: number;
  version: string;
  generated_at: number;
  council_batch: {
    total_attempted: number;
    unique_ids_run: number;
    total_elapsed_s: number;
    last_run_count: number;
  };
  apply_attempts: {
    window_days: number;
    total_attempts: number;
    applied: number;
    rejected: number;
    drill_failed: number;
    errored: number;
    apply_rate: number;
    honesty_signal: string;
  };
  audit_decisions: Array<{
    issue_id: string;
    lane: string;
    model: string;
    outcome: string;
    tokens_total: number;
    max_latency_s: number;
  }>;
  pending_issues: {
    total_pending: number;
    by_assignee: Record<string, number>;
    by_severity: Record<string, number>;
    by_difficulty: Record<string, number>;
  };
  council_outcomes: {
    by_outcome: Record<string, number>;
    total: number;
  };
};

type ApiResponse = { data: Snapshot; correlation_id: string };

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function honestyBadgeColor(rate: number): { bg: string; fg: string } {
  if (rate >= 0.5) return { bg: '#1f8a4c', fg: '#fff' };
  if (rate >= 0.1) return { bg: '#c47a1a', fg: '#fff' };
  return { bg: '#a4262c', fg: '#fff' }; // <10% — brutal-honesty red
}

export default function PaperclipPage() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/paperclip', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      const j = (await r.json()) as ApiResponse;
      setSnap(j.data);
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

  const honestyColor = snap
    ? honestyBadgeColor(snap.apply_attempts.apply_rate)
    : { bg: '#666', fg: '#fff' };

  return (
    <div style={{ padding: '24px', maxWidth: 1200 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Paperclip — sandbox manager-layer</h1>
        <span
          style={{
            fontSize: '0.75rem',
            padding: '2px 8px',
            background: '#444',
            color: '#fff',
            borderRadius: 4,
          }}
        >
          Stage 1 · read-only
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
        Read-only sandbox aggregator above the council substrate. Subscribes to{' '}
        <code>.loop/council_batch_summary.json</code>,{' '}
        <code>.loop/issue_audit.jsonl</code>,{' '}
        <code>.loop/agent_task_board_apply.jsonl</code>. Write verbs (push, dispatch, deploy) are §42-gated and refuse with exit code 2.
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

      {snap && (
        <>
          {/* Brutal-honesty headline */}
          <section
            style={{
              padding: 16,
              border: '2px solid #ddd',
              borderRadius: 8,
              marginBottom: 16,
              background: '#fafafa',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div
                style={{
                  background: honestyColor.bg,
                  color: honestyColor.fg,
                  padding: '8px 16px',
                  borderRadius: 4,
                  fontSize: '1.5rem',
                  fontWeight: 'bold',
                  minWidth: 80,
                  textAlign: 'center',
                }}
              >
                {pct(snap.apply_attempts.apply_rate)}
              </div>
              <div>
                <div style={{ fontSize: '0.85rem', color: '#666' }}>
                  Apply rate (last {snap.apply_attempts.window_days}d) — §55.3 brutal-honesty signal
                </div>
                <div style={{ fontWeight: 600 }}>{snap.apply_attempts.honesty_signal}</div>
                <div style={{ fontSize: '0.85rem', color: '#666', marginTop: 4 }}>
                  {snap.apply_attempts.applied} applied · {snap.apply_attempts.rejected} rejected ·{' '}
                  {snap.apply_attempts.drill_failed} drill-failed · {snap.apply_attempts.errored} errored
                </div>
              </div>
            </div>
          </section>

          {/* Council batch */}
          <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            <div style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4 }}>
              <h3 style={{ marginTop: 0 }}>Council batch</h3>
              <div>Total attempted: <strong>{snap.council_batch.total_attempted}</strong></div>
              <div>Unique IDs run: <strong>{snap.council_batch.unique_ids_run}</strong></div>
              <div>Total elapsed: <strong>{snap.council_batch.total_elapsed_s.toFixed(1)}s</strong></div>
              <div>Last run count: <strong>{snap.council_batch.last_run_count}</strong></div>
            </div>

            <div style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4 }}>
              <h3 style={{ marginTop: 0 }}>Council outcomes</h3>
              {Object.entries(snap.council_outcomes.by_outcome).map(([k, v]) => (
                <div key={k}>
                  <code>{k}</code>: <strong>{v}</strong>
                </div>
              ))}
              <div style={{ marginTop: 8, color: '#666', fontSize: '0.85rem' }}>
                Total: {snap.council_outcomes.total}
              </div>
            </div>
          </section>

          {/* Pending issues */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>
              Pending issues — total: {snap.pending_issues.total_pending}
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
              <div>
                <div style={{ fontSize: '0.85rem', color: '#666' }}>By assignee</div>
                {Object.entries(snap.pending_issues.by_assignee).map(([k, v]) => (
                  <div key={k}><code>{k}</code>: {v}</div>
                ))}
              </div>
              <div>
                <div style={{ fontSize: '0.85rem', color: '#666' }}>By severity</div>
                {Object.entries(snap.pending_issues.by_severity).map(([k, v]) => (
                  <div key={k}><code>{k}</code>: {v}</div>
                ))}
              </div>
              <div>
                <div style={{ fontSize: '0.85rem', color: '#666' }}>By difficulty</div>
                {Object.entries(snap.pending_issues.by_difficulty).map(([k, v]) => (
                  <div key={k}><code>{k}</code>: {v}</div>
                ))}
              </div>
            </div>
          </section>

          {/* Recent audit decisions */}
          <section style={{ padding: 16, border: '1px solid #ddd', borderRadius: 4, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Recent audit decisions (last 20)</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Issue ID</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Lane</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Model</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Outcome</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Tokens</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Max Lat (s)</th>
                </tr>
              </thead>
              <tbody>
                {snap.audit_decisions.map((row, idx) => (
                  <tr key={`${row.issue_id}-${idx}`} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: 6 }}><code>{row.issue_id}</code></td>
                    <td style={{ padding: 6 }}>{row.lane}</td>
                    <td style={{ padding: 6 }}>{row.model}</td>
                    <td style={{ padding: 6 }}>
                      <code style={{ color: row.outcome.startsWith('council') ? '#1f8a4c' : '#a4262c' }}>
                        {row.outcome}
                      </code>
                    </td>
                    <td style={{ padding: 6, textAlign: 'right' }}>{row.tokens_total}</td>
                    <td style={{ padding: 6, textAlign: 'right' }}>{row.max_latency_s.toFixed(2)}</td>
                  </tr>
                ))}
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
                <a href="/admin/local-models">Local models</a> — same Ollama
                council that generates the audit rows shown here.
              </li>
              <li>
                <a href="/admin/agentic">Agentic framework</a> — Paperclip
                sits in the sandbox layer of the orchestration architecture.
              </li>
              <li>
                <a href="/admin/checklist">Checklist</a> — the pending-issues
                list shown here is sourced from the same{' '}
                <code>.loop/issue_checklist.jsonl</code>.
              </li>
              <li>
                <a href="/admin/architect">Architect deep-dive</a> — Paperclip
                is sandbox-only per ADR-012; this page intentionally has no
                write authority.
              </li>
              <li>
                <a href="/admin/explainability">Explainability</a> — every audit
                decision row is the §48.4 evidence trail for what the council
                proposed.
              </li>
            </ul>
            <div style={{ marginTop: 8, color: '#666' }}>
              Stage-2 (propose-only) and Stage-3 (gated delegation via MCP scope
              tokens) compose on TOP of this contract — never by relaxing it.
              Snapshot version: <code>{snap.version}</code> · stage{' '}
              <code>{snap.stage}</code>.
            </div>
          </section>
        </>
      )}
    </div>
  );
}
