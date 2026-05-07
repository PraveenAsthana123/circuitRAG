'use client';

/**
 * /admin/agent-readiness — empirical answer to "is the agent fleet
 * actually working?"
 *
 * Reads /api/v1/agent-readiness which proxies the JSON written by
 * scripts/agent_readiness_check.py at iter-76. Shows 7 dimensions:
 *
 *   A. models work        — all Ollama models pass /api/generate
 *   B. orchestrator up    — agent-orchestrator-svc /health
 *   C. council active     — recent council runs in stats
 *   D. apply rate         — fraction of diffs that landed (§55)
 *   E. work assignable    — can issue_dispatcher route work
 *   F. mcp fleet          — server files installed + drills server up
 *   G. council nodes      — 4 canonical models in Ollama
 *
 * Auto-refreshes every 30s (matches BFF cache TTL).
 *
 * Per CLAUDE.md §44 (iter-77), §38 (verifiable claims), §51 (forensic
 * substrate).
 *
 * Drill: mcp/tests/drill_agent_readiness_ui.py.
 */

import { useCallback, useEffect, useState } from 'react';

type Probe = {
  status: 'YES' | 'NO' | 'MIXED' | 'UNKNOWN';
  evidence: string;
  notes: string;
};

type Report = {
  generated_at: string;
  by_status: Record<string, number>;
  results: Record<string, Probe>;
};

const PROBE_TITLES: Record<string, string> = {
  A_models_work: 'Models work — all Ollama models functioning',
  B_orchestrator_up: 'Orchestrator up — agent-orchestrator-svc /health',
  C_council_active: 'Council active — recent runs in stats',
  D_apply_rate: 'Apply rate — fraction of diffs that landed (§55)',
  E_work_assignable: 'Work assignable — issue_dispatcher CLI healthy',
  F_mcp_fleet: 'MCP fleet — server files + drills server reachable',
  G_council_nodes: 'Council nodes — 4 canonical models installed',
};

const STATUS_COLOR: Record<string, string> = {
  YES: '#22c55e',
  NO: '#ef4444',
  MIXED: '#f59e0b',
  UNKNOWN: '#6b7280',
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLOR[status] ?? '#6b7280';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 700,
        color: '#fff',
        background: color,
        minWidth: 80,
        textAlign: 'center',
      }}
    >
      {status}
    </span>
  );
}

export default function AgentReadinessPage() {
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/agent-readiness', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`HTTP ${r.status}: ${body.slice(0, 200)}`);
      }
      const j = (await r.json()) as Report;
      setData(j);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  if (loading && !data) {
    return <div style={{ padding: 24 }}>Loading agent readiness report…</div>;
  }
  if (error && !data) {
    return (
      <div style={{ padding: 24, color: '#ef4444' }}>
        Failed to load readiness report: {error}
      </div>
    );
  }
  if (!data) return null;

  const order = [
    'A_models_work',
    'B_orchestrator_up',
    'C_council_active',
    'D_apply_rate',
    'E_work_assignable',
    'F_mcp_fleet',
    'G_council_nodes',
  ];

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, marginBottom: 4 }}>Agent Readiness</h1>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
        7-dimension empirical probe · generated_at: {data.generated_at} ·
        auto-refresh 30s
      </div>

      <div
        style={{
          display: 'flex',
          gap: 12,
          marginBottom: 16,
          flexWrap: 'wrap',
        }}
      >
        {Object.entries(data.by_status).map(([s, n]) => (
          <span key={s}>
            <StatusBadge status={s} /> <strong>{n}</strong>
          </span>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {order.map((key) => {
          const r = data.results[key];
          if (!r) return null;
          return (
            <div
              key={key}
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                padding: 16,
                borderLeft: `4px solid ${STATUS_COLOR[r.status] ?? '#6b7280'}`,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 8,
                }}
              >
                <strong style={{ fontSize: 14 }}>
                  {PROBE_TITLES[key] ?? key}
                </strong>
                <StatusBadge status={r.status} />
              </div>
              <div style={{ fontSize: 13, color: '#1f2937', marginBottom: 4 }}>
                <strong>evidence: </strong>
                {r.evidence}
              </div>
              {r.notes && (
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  <strong>notes: </strong>
                  {r.notes}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div
        style={{
          marginTop: 24,
          padding: 12,
          background: '#fef3c7',
          border: '1px solid #f59e0b',
          borderRadius: 6,
          fontSize: 12,
        }}
      >
        <strong>§55 reminder.</strong> Apply rate is the §55.3
        outcome-based contract metric. A fix-bot at 0% apply rate is a
        logging system pretending to fix things. If row D is NO, the
        operator should investigate council reject reasons in{' '}
        <code>.loop/agent_task_board_apply.jsonl</code>.
      </div>

      {error && (
        <div style={{ marginTop: 16, color: '#f59e0b', fontSize: 12 }}>
          last refresh failed: {error} (using cached snapshot)
        </div>
      )}
    </div>
  );
}
