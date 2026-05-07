'use client';

/**
 * /admin/production-readiness — the "is it production grade?" UI.
 *
 * Aggregates §38 + §47 + §52 + §53 + §55 evidence into a single
 * scorecard. The user asked "all must be 100% working, production
 * grade readiness with UI report, visualization." This page is the
 * answer.
 *
 * Visualizations:
 *   - Overall radial gauge (0-100)
 *   - Per-dimension horizontal bars vs threshold
 *   - Pass/fail badge per dimension
 *   - Gap list per dimension (named, not vibes)
 *   - §55 brutal-rule banner if outcome score < 50
 *
 * Auto-refreshes every 30s (matches BFF cache TTL). Per CLAUDE.md §44.
 *
 * Drill: mcp/tests/drill_production_readiness_ui.py.
 */

import { useCallback, useEffect, useState } from 'react';

type Dimension = {
  score: number;
  gaps?: string[];
  [k: string]: unknown;
};

type Scorecard = {
  generated_at: string;
  overall_score: number;
  production_grade: boolean;
  dimensions: {
    G1_governance_38: Dimension;
    G2_architecture_47: Dimension;
    G3_tool_reviews_52: Dimension;
    G4_maturity_53: Dimension;
    G5_outcome_55: Dimension;
  };
  thresholds: Record<string, number>;
};

const DIMENSION_TITLES: Record<string, string> = {
  G1_governance_38: 'AI Production Governance (§38) — 15 gates',
  G2_architecture_47: 'Architecture & Design (§47) — 7 surfaces',
  G3_tool_reviews_52: 'Tool Reviews & Catalogs (§52)',
  G4_maturity_53: 'Enterprise AI Maturity Stack (§53) — 14 items',
  G5_outcome_55: 'Outcome Contract (§55) — apply rate / regression / cost',
};

function colorForScore(score: number, threshold: number): string {
  if (score >= threshold + 20) return '#22c55e';
  if (score >= threshold) return '#84cc16';
  if (score >= threshold - 20) return '#f59e0b';
  return '#ef4444';
}

function ScoreBar({ score, threshold }: { score: number; threshold: number }) {
  const color = colorForScore(score, threshold);
  return (
    <div style={{ width: '100%', position: 'relative' }}>
      <div
        style={{
          width: '100%',
          height: 16,
          background: '#e5e7eb',
          borderRadius: 4,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${score}%`,
            height: '100%',
            background: color,
            transition: 'width 0.4s ease-out',
          }}
        />
      </div>
      {/* Threshold marker */}
      <div
        style={{
          position: 'absolute',
          left: `${threshold}%`,
          top: -2,
          width: 2,
          height: 20,
          background: '#1f2937',
        }}
        title={`threshold: ${threshold}`}
      />
    </div>
  );
}

function RadialGauge({ score }: { score: number }) {
  const size = 180;
  const stroke = 16;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (score / 100) * circumference;
  const color =
    score >= 80 ? '#22c55e' :
    score >= 60 ? '#84cc16' :
    score >= 40 ? '#f59e0b' :
    '#ef4444';
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke="#e5e7eb" strokeWidth={stroke}
      />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${circumference - dash}`}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 0.6s ease-out' }}
      />
      <text
        x={size / 2} y={size / 2}
        textAnchor="middle" dominantBaseline="central"
        fontSize={36} fontWeight={700} fill="#1f2937"
        style={{ transform: 'rotate(90deg)', transformOrigin: 'center' }}
      >
        {score}
      </text>
    </svg>
  );
}

export default function ProductionReadinessPage() {
  const [data, setData] = useState<Scorecard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/production-readiness', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`HTTP ${r.status}: ${body.slice(0, 200)}`);
      }
      setData((await r.json()) as Scorecard);
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
    return <div style={{ padding: 24 }}>Loading production readiness scorecard…</div>;
  }
  if (error && !data) {
    return (
      <div style={{ padding: 24, color: '#ef4444' }}>
        Failed to load scorecard: {error}
      </div>
    );
  }
  if (!data) return null;

  const dimEntries = Object.entries(data.dimensions) as [
    keyof Scorecard['dimensions'], Dimension
  ][];

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ fontSize: 26, marginBottom: 4 }}>Production Readiness</h1>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
        Aggregates §38 + §47 + §52 + §53 + §55 · generated_at: {data.generated_at} ·
        auto-refresh 30s
      </div>

      {/* Top: overall gauge + verdict */}
      <div
        style={{
          display: 'flex',
          gap: 24,
          alignItems: 'center',
          padding: 24,
          background: data.production_grade ? '#f0fdf4' : '#fef2f2',
          border: `2px solid ${data.production_grade ? '#22c55e' : '#ef4444'}`,
          borderRadius: 12,
          marginBottom: 24,
        }}
      >
        <RadialGauge score={data.overall_score} />
        <div>
          <div style={{ fontSize: 14, color: '#6b7280', marginBottom: 4 }}>
            Overall production-grade verdict
          </div>
          <div
            style={{
              fontSize: 32,
              fontWeight: 800,
              color: data.production_grade ? '#15803d' : '#b91c1c',
              marginBottom: 8,
            }}
          >
            {data.production_grade ? 'PRODUCTION GRADE' : 'NOT YET PRODUCTION GRADE'}
          </div>
          <div style={{ fontSize: 13, color: '#374151' }}>
            {data.production_grade
              ? 'All 5 dimensions cleared their thresholds. §38 + §47 + §52 + §53 + §55 evidence holds.'
              : `${
                  dimEntries.filter(
                    ([k, d]) => d.score < (data.thresholds[k] ?? 0)
                  ).length
                } of 5 dimensions below threshold. See per-dimension gaps below.`}
          </div>
        </div>
      </div>

      {/* §55 brutal-rule banner if outcome low */}
      {data.dimensions.G5_outcome_55.score < 50 && (
        <div
          style={{
            padding: 12,
            background: '#fee2e2',
            border: '1px solid #ef4444',
            borderRadius: 6,
            fontSize: 12,
            marginBottom: 16,
          }}
        >
          <strong style={{ color: '#b91c1c' }}>§55 brutal-rule fire.</strong>{' '}
          The outcome score is below 50. Per global CLAUDE.md §55: "A fix-bot at
          0% apply rate is not a fix-bot — it's a logging system that pretends
          to fix things." Investigate council reject reasons in{' '}
          <code>.loop/agent_task_board_apply.jsonl</code>.
        </div>
      )}

      {/* Per-dimension cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {dimEntries.map(([key, dim]) => {
          const threshold = data.thresholds[key] ?? 0;
          const passed = dim.score >= threshold;
          const color = colorForScore(dim.score, threshold);
          return (
            <div
              key={key}
              style={{
                border: '1px solid #e5e7eb',
                borderLeft: `5px solid ${color}`,
                borderRadius: 8,
                padding: 16,
                background: '#fff',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 12,
                }}
              >
                <strong style={{ fontSize: 15 }}>
                  {DIMENSION_TITLES[key] ?? key}
                </strong>
                <span
                  style={{
                    padding: '4px 12px',
                    borderRadius: 4,
                    fontSize: 12,
                    fontWeight: 700,
                    color: '#fff',
                    background: passed ? '#22c55e' : '#ef4444',
                  }}
                >
                  {dim.score}/100 {passed ? 'PASS' : 'FAIL'}
                </span>
              </div>
              <ScoreBar score={dim.score} threshold={threshold} />
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                Threshold: {threshold} (vertical bar)
              </div>
              {Array.isArray(dim.gaps) && dim.gaps.length > 0 && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: '#fef3c7',
                    borderRadius: 4,
                    fontSize: 12,
                  }}
                >
                  <strong>Named gaps ({dim.gaps.length}):</strong>
                  <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                    {dim.gaps.slice(0, 8).map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                    {dim.gaps.length > 8 && (
                      <li style={{ color: '#6b7280' }}>
                        … +{dim.gaps.length - 8} more
                      </li>
                    )}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {error && (
        <div style={{ marginTop: 16, color: '#f59e0b', fontSize: 12 }}>
          last refresh failed: {error} (using cached snapshot)
        </div>
      )}

      <div
        style={{
          marginTop: 32,
          padding: 12,
          background: '#f3f4f6',
          borderRadius: 6,
          fontSize: 11,
          color: '#6b7280',
        }}
      >
        Click-through evidence: <a href="/admin/agent-readiness">/admin/agent-readiness</a>{' '}
        (7-dim probe), <a href="/admin/mcp-fleet-health">/admin/mcp-fleet-health</a>{' '}
        (28 servers + 15 models + 4 council nodes). Run{' '}
        <code>python3 scripts/production_readiness_scorecard.py</code> locally
        to re-derive this report.
      </div>
    </div>
  );
}
