'use client';

/**
 * /admin/tools-launcher — left-nav + right-grid tool launcher.
 *
 * Pure directory + status dashboard for every external tool circuitRAG
 * integrates with. Reuses the /api/v1/integrations-health BFF (shipped
 * in e68e0da) so live status (HEALTHY / DEGRADED / UNREACHABLE / NOT_
 * CONFIGURED / TCP_ONLY) shows as a traffic-light dot per tool.
 *
 * Layout:
 *   ┌─────────────┬────────────────────────────────────────┐
 *   │ All (n)     │  [Tool Card] [Tool Card] [Tool Card]   │
 *   │ Observability│ ●  Langfuse              Open ↗       │
 *   │ Mesh        │  ●  Grafana               Open ↗       │
 *   │ Storage     │  ●  Prometheus            Open ↗       │
 *   │ LLM         │  ●  Jaeger                Open ↗       │
 *   │ Telemetry   │  ●  Alertmanager          Open ↗       │
 *   │ circuitRAG  │  ...                                    │
 *   └─────────────┴────────────────────────────────────────┘
 *
 * Auto-refresh 10s. Click a left-nav category to filter the right grid.
 *
 * Per CLAUDE.md §47.6 (observability is first-class), §49 (composes
 * with /admin/monitoring IntegrationsHealth + the same BFF route),
 * §57.1 production-grade-by-default. Locked by
 * mcp/tests/drill_tools_launcher_page.py.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

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
  | 'mesh'
  | 'storage'
  | 'llm'
  | 'telemetry'
  | 'circuitrag';

interface Tool {
  name: string;
  category: Category;
  ui_url: string;
  status: Status;
  latency_ms: number | null;
  error?: string;
  http_status?: number;
  description: string;
}

interface Payload {
  generated_at: string;
  tools: Tool[];
}

const TRAFFIC_LIGHT: Record<Status, { dot: string; label: string; bg: string; fg: string }> = {
  HEALTHY:        { dot: '#1f7a3a', label: 'GREEN — healthy',       bg: '#dff5e0', fg: '#1f7a3a' },
  DEGRADED:       { dot: '#9a6b16', label: 'YELLOW — degraded',     bg: '#fef5d8', fg: '#9a6b16' },
  UNREACHABLE:    { dot: '#a52424', label: 'RED — unreachable',     bg: '#fbe0e0', fg: '#a52424' },
  NOT_CONFIGURED: { dot: '#888888', label: 'GRAY — not configured', bg: '#eaeaea', fg: '#555' },
  TCP_ONLY:       { dot: '#2c5aa0', label: 'BLUE — TCP only',       bg: '#e1ecfb', fg: '#2c5aa0' },
};

const CATEGORY_LABEL: Record<Category, string> = {
  observability: 'Observability',
  mesh:          'Service mesh',
  storage:       'Storage',
  llm:           'LLM runtime',
  telemetry:     'Telemetry agents',
  circuitrag:    'circuitRAG gateways',
};

const CATEGORY_ORDER: Category[] = [
  'observability',
  'mesh',
  'llm',
  'storage',
  'telemetry',
  'circuitrag',
];

function StatusDot({ status }: { status: Status }) {
  const t = TRAFFIC_LIGHT[status];
  return (
    <span
      title={t.label}
      style={{
        display: 'inline-block',
        width: 12,
        height: 12,
        borderRadius: '50%',
        background: t.dot,
        marginRight: 8,
        verticalAlign: 'middle',
        boxShadow: '0 0 0 2px rgba(0,0,0,0.05)',
      }}
    />
  );
}

function StatusPill({ status }: { status: Status }) {
  const t = TRAFFIC_LIGHT[status];
  return (
    <span
      style={{
        background: t.bg,
        color: t.fg,
        padding: '2px 8px',
        borderRadius: 12,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 0.3,
        whiteSpace: 'nowrap',
      }}
    >
      {status}
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
        padding: 14,
        background: '#fff',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        minHeight: 130,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <StatusDot status={tool.status} />
          <strong style={{ fontSize: 14 }}>{tool.name}</strong>
        </div>
        <StatusPill status={tool.status} />
      </div>
      <div style={{ fontSize: 11, color: '#555', minHeight: 28 }}>{tool.description}</div>
      <div style={{ fontSize: 11, color: '#666', display: 'flex', gap: 12 }}>
        {tool.latency_ms !== null && tool.status !== 'TCP_ONLY' && (
          <span>{tool.latency_ms}ms</span>
        )}
        {tool.http_status !== undefined && <span>HTTP {tool.http_status}</span>}
        {tool.error && <span style={{ color: '#a52424' }}>err: {tool.error}</span>}
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
          <span style={{ fontSize: 11, color: '#888', fontFamily: 'monospace' }}>
            {tool.ui_url}
          </span>
        )}
      </div>
    </div>
  );
}

export default function ToolsLauncherPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Category | 'all'>('all');

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

  // Per-category counts for the left nav
  const counts = useMemo(() => {
    const out: Record<string, number> = { all: 0 };
    for (const cat of CATEGORY_ORDER) out[cat] = 0;
    if (data) {
      out.all = data.tools.length;
      for (const t of data.tools) {
        out[t.category] = (out[t.category] ?? 0) + 1;
      }
    }
    return out;
  }, [data]);

  // Aggregate traffic-light counts (overall stack health)
  const lights = useMemo(() => {
    const out: Record<Status, number> = {
      HEALTHY: 0,
      DEGRADED: 0,
      UNREACHABLE: 0,
      NOT_CONFIGURED: 0,
      TCP_ONLY: 0,
    };
    if (data) for (const t of data.tools) out[t.status]++;
    return out;
  }, [data]);

  const visibleTools = useMemo(() => {
    if (!data) return [];
    if (filter === 'all') return data.tools;
    return data.tools.filter((t) => t.category === filter);
  }, [data, filter]);

  if (loading && !data) {
    return (
      <div style={{ padding: 24 }}>
        <h1>Tools launcher</h1>
        <p style={{ color: '#666' }}>Loading…</p>
      </div>
    );
  }
  if (error && !data) {
    return (
      <div style={{ padding: 24 }}>
        <h1>Tools launcher</h1>
        <p style={{ color: '#a52424' }}>Error: {error}</p>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div style={{ padding: 16, maxWidth: 1400, margin: '0 auto' }}>
      <header style={{ marginBottom: 16 }}>
        <h1 style={{ margin: '0 0 4px 0' }}>Tools launcher</h1>
        <p style={{ color: '#555', margin: 0, fontSize: 13 }}>
          Live status of every external tool circuitRAG integrates with.
          Click a category in the left rail to filter. Each card opens in
          a new tab. Auto-refresh every 10s.
        </p>
        <div
          style={{
            marginTop: 10,
            fontSize: 12,
            color: '#444',
            display: 'flex',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <span><StatusDot status="HEALTHY" /><strong>{lights.HEALTHY}</strong> green</span>
          <span><StatusDot status="DEGRADED" /><strong>{lights.DEGRADED}</strong> yellow</span>
          <span><StatusDot status="UNREACHABLE" /><strong>{lights.UNREACHABLE}</strong> red</span>
          <span><StatusDot status="TCP_ONLY" /><strong>{lights.TCP_ONLY}</strong> tcp-only</span>
          <span><StatusDot status="NOT_CONFIGURED" /><strong>{lights.NOT_CONFIGURED}</strong> not configured</span>
          <span style={{ color: '#888' }}>
            refreshed {new Date(data.generated_at).toLocaleTimeString()}
          </span>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 16 }}>
        {/* LEFT — category nav */}
        <nav
          aria-label="tool categories"
          style={{
            background: '#f8f8fb',
            border: '1px solid #ececec',
            borderRadius: 8,
            padding: 8,
            position: 'sticky',
            top: 12,
            alignSelf: 'start',
          }}
        >
          <button
            onClick={() => setFilter('all')}
            style={navBtnStyle(filter === 'all')}
          >
            All <span style={{ color: '#888', fontSize: 11 }}>({counts.all})</span>
          </button>
          {CATEGORY_ORDER.map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              style={navBtnStyle(filter === cat)}
            >
              {CATEGORY_LABEL[cat]}{' '}
              <span style={{ color: '#888', fontSize: 11 }}>({counts[cat] ?? 0})</span>
            </button>
          ))}
        </nav>

        {/* RIGHT — tool grid */}
        <section>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: 12,
            }}
          >
            {visibleTools.map((t) => (
              <ToolCard key={t.name} tool={t} />
            ))}
          </div>
          {visibleTools.length === 0 && (
            <div style={{ color: '#888', fontStyle: 'italic', padding: 16 }}>
              No tools in this category.
            </div>
          )}
        </section>
      </div>

      <footer
        style={{
          marginTop: 24,
          fontSize: 12,
          color: '#666',
          paddingTop: 12,
          borderTop: '1px solid #eee',
        }}
      >
        Composes with: <a href="/admin/monitoring">/admin/monitoring</a> ·{' '}
        <a href="/admin/mcp-fleet-health">/admin/mcp-fleet-health</a> ·{' '}
        <a href="/admin/health-pulse">/admin/health-pulse</a>. Backed by
        the same <code>/api/v1/integrations-health</code> BFF route.
      </footer>
    </div>
  );
}

function navBtnStyle(active: boolean): React.CSSProperties {
  return {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '8px 12px',
    margin: '2px 0',
    background: active ? '#1a5fb4' : 'transparent',
    color: active ? '#fff' : '#222',
    border: 0,
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: active ? 600 : 400,
  };
}
