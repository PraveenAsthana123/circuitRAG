'use client';

/**
 * /admin/monitoring — IntegrationsHealth panel.
 *
 * Live single-pane-of-glass for every external observability /
 * storage / mesh tool circuitRAG integrates with. Auto-refresh 10s
 * matches mcp-fleet-health convention; BFF caches 30s so refreshes
 * don't hammer the third-party UIs.
 *
 * Per CLAUDE.md §47 (observability is first-class), §49 (compose
 * with mcp-fleet-health + health-pulse), §57.1 (production-grade:
 * status taxonomy + parallel probe + timeout from day-1).
 */

import { useCallback, useEffect, useState } from 'react';

const REFRESH_INTERVAL_MS = 10_000;
const BFF = '/api/v1/integrations-health';

type Status =
  | 'HEALTHY'
  | 'DEGRADED'
  | 'UNREACHABLE'
  | 'NOT_CONFIGURED'
  | 'TCP_ONLY';

type Category =
  | 'observability'
  | 'storage'
  | 'telemetry'
  | 'llm'
  | 'mesh'
  | 'circuitrag';

interface Tool {
  name: string;
  category: Category;
  ui_url: string;
  status: Status;
  latency_ms: number | null;
  error?: string;
  http_status?: number;
  version?: string;
  description: string;
}

interface Payload {
  generated_at: string;
  tools: Tool[];
}

const STATUS_COLOR: Record<Status, { bg: string; fg: string; label: string }> = {
  HEALTHY: { bg: '#dff5e0', fg: '#1f7a3a', label: 'HEALTHY' },
  DEGRADED: { bg: '#fef5d8', fg: '#9a6b16', label: 'DEGRADED' },
  UNREACHABLE: { bg: '#fbe0e0', fg: '#a52424', label: 'UNREACHABLE' },
  NOT_CONFIGURED: { bg: '#eaeaea', fg: '#555', label: 'NOT CONFIGURED' },
  TCP_ONLY: { bg: '#e1ecfb', fg: '#2c5aa0', label: 'TCP ONLY' },
};

const CATEGORY_LABEL: Record<Category, string> = {
  observability: 'Observability',
  mesh: 'Service mesh',
  storage: 'Storage',
  llm: 'LLM runtime',
  telemetry: 'Telemetry agents',
  circuitrag: 'circuitRAG gateways',
};

function StatusBadge({ status }: { status: Status }) {
  const c = STATUS_COLOR[status];
  return (
    <span
      style={{
        background: c.bg,
        color: c.fg,
        padding: '2px 8px',
        borderRadius: 12,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 0.3,
        whiteSpace: 'nowrap',
      }}
    >
      {c.label}
    </span>
  );
}

function ToolCard({ tool }: { tool: Tool }) {
  const isOpenable =
    tool.status !== 'NOT_CONFIGURED' && !tool.ui_url.startsWith('tcp://');
  return (
    <div
      style={{
        border: '1px solid #e3e3e3',
        borderRadius: 8,
        padding: 12,
        background: '#fff',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        minHeight: 110,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong style={{ fontSize: 14 }}>{tool.name}</strong>
        <StatusBadge status={tool.status} />
      </div>
      <div style={{ fontSize: 11, color: '#555', minHeight: 28 }}>
        {tool.description}
      </div>
      <div style={{ fontSize: 11, color: '#666', display: 'flex', gap: 12 }}>
        {tool.latency_ms !== null && tool.status !== 'TCP_ONLY' && (
          <span>{tool.latency_ms}ms</span>
        )}
        {tool.http_status !== undefined && <span>HTTP {tool.http_status}</span>}
        {tool.error && (
          <span style={{ color: '#a52424' }}>err: {tool.error}</span>
        )}
      </div>
      <div style={{ marginTop: 'auto' }}>
        {isOpenable ? (
          <a
            href={tool.ui_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 12,
              color: '#1a5fb4',
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            Open ↗
          </a>
        ) : (
          <span style={{ fontSize: 11, color: '#888' }}>{tool.ui_url}</span>
        )}
      </div>
    </div>
  );
}

export default function IntegrationsHealth() {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchHealth = useCallback(async () => {
    try {
      const r = await fetch(BFF, { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const json = (await r.json()) as Payload;
      setData(json);
      setError(null);
    } catch (e: unknown) {
      const err = e as Error;
      setError(err.message || 'fetch failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    void fetchHealth();
    timer = setInterval(() => {
      if (!cancelled) void fetchHealth();
    }, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [fetchHealth]);

  if (loading && !data) {
    return (
      <section style={{ padding: 16 }}>
        <h2 style={{ marginTop: 0 }}>Integrations health</h2>
        <p style={{ color: '#666' }}>Loading…</p>
      </section>
    );
  }
  if (error && !data) {
    return (
      <section style={{ padding: 16 }}>
        <h2 style={{ marginTop: 0 }}>Integrations health</h2>
        <p style={{ color: '#a52424' }}>Error: {error}</p>
      </section>
    );
  }
  if (!data) return null;

  // Group by category
  const byCat: Partial<Record<Category, Tool[]>> = {};
  for (const t of data.tools) {
    if (!byCat[t.category]) byCat[t.category] = [];
    byCat[t.category]!.push(t);
  }

  // Tally summary
  const counts: Record<Status, number> = {
    HEALTHY: 0,
    DEGRADED: 0,
    UNREACHABLE: 0,
    NOT_CONFIGURED: 0,
    TCP_ONLY: 0,
  };
  for (const t of data.tools) counts[t.status]++;

  return (
    <section
      style={{
        padding: 16,
        background: '#fafafa',
        border: '1px solid #ececec',
        borderRadius: 10,
        marginBottom: 24,
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <h2 style={{ margin: 0 }}>Integrations health</h2>
        <div style={{ fontSize: 12, color: '#666', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span>
            <strong style={{ color: '#1f7a3a' }}>{counts.HEALTHY}</strong> healthy
          </span>
          <span>
            <strong style={{ color: '#9a6b16' }}>{counts.DEGRADED}</strong> degraded
          </span>
          <span>
            <strong style={{ color: '#a52424' }}>{counts.UNREACHABLE}</strong> unreachable
          </span>
          <span>
            <strong style={{ color: '#2c5aa0' }}>{counts.TCP_ONLY}</strong> TCP-only
          </span>
          <span>refreshed {new Date(data.generated_at).toLocaleTimeString()}</span>
        </div>
      </header>

      {(['observability', 'mesh', 'llm', 'storage', 'telemetry', 'circuitrag'] as Category[]).map(
        (cat) => {
          const items = byCat[cat];
          if (!items || items.length === 0) return null;
          return (
            <div key={cat} style={{ marginBottom: 16 }}>
              <h3 style={{ fontSize: 13, color: '#444', margin: '6px 0 8px 0' }}>
                {CATEGORY_LABEL[cat]}
              </h3>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                  gap: 12,
                }}
              >
                {items.map((t) => (
                  <ToolCard key={t.name} tool={t} />
                ))}
              </div>
            </div>
          );
        },
      )}
    </section>
  );
}
