'use client';

/**
 * /admin/mcp-fleet-health — operator-visible 4-inventory health board.
 *
 * Reads /api/v1/mcp-fleet-health and renders four sections:
 *   1. MCP fleet (28 servers; status badges WORKING/DEGRADED/FAILING/SLEEPING/NOT_INSTALLED)
 *   2. Ollama models (15 installed; in-VRAM set highlighted)
 *   3. Council nodes (researcher/author/reviewer/advisor + 5-role aliases)
 *   4. Backend services (10 svcs with operations + descriptions)
 *
 * Auto-refreshes every 10s. The BFF caches for 30s so refreshes don't
 * fork a Python process per click.
 *
 * Per CLAUDE.md §44 (iter-73), §47 (observability is first-class),
 * §50.5.3 (read-only operator surface), §51 (forensic substrate).
 *
 * Drill: mcp/tests/drill_mcp_fleet_health_ui.py.
 */

import { useCallback, useEffect, useState } from 'react';

type ServerHealth = {
  namespace: string;
  status: 'WORKING' | 'DEGRADED' | 'FAILING' | 'SLEEPING' | 'NOT_INSTALLED';
  installed: boolean;
  url: string;
  url_env_var: string;
  reachable: boolean;
  tools_total: number;
  tools_read: number;
  tools_write: number;
  required_scopes: string[];
  tool_health?: {
    name: string;
    side_effects: string;
    status: string;
    note?: string;
    sample_input?: unknown;
  }[];
  notes: string[];
  missing_env_vars: string[];
  classified_at: string;
};

type FleetHealth = {
  generated_at: string;
  total_servers: number;
  by_status: Record<string, number>;
  servers: ServerHealth[];
  ollama?: {
    base_url: string;
    reachable: boolean;
    installed_models: { name: string; size_gb: number; family: string }[];
    loaded_models: string[];
    notes: string[];
  };
  council?: {
    nodes: {
      role: string;
      aliases: string[];
      model: string;
      ollama_available: boolean;
      notes: string[];
    }[];
  };
  backends?: {
    services: {
      name: string;
      url: string;
      url_env_var: string;
      reachable: boolean;
      status: string;
      operations: string[];
      description: string;
    }[];
  };
};

const STATUS_COLOR: Record<string, string> = {
  WORKING: '#22c55e',
  DEGRADED: '#f59e0b',
  FAILING: '#ef4444',
  SLEEPING: '#6b7280',
  NOT_INSTALLED: '#374151',
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLOR[status] ?? '#6b7280';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        color: '#fff',
        background: color,
        minWidth: 90,
        textAlign: 'center',
      }}
    >
      {status}
    </span>
  );
}

export default function McpFleetHealthPage() {
  const [data, setData] = useState<FleetHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<number>(0);

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/mcp-fleet-health', { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`HTTP ${r.status}: ${body.slice(0, 200)}`);
      }
      const j = (await r.json()) as FleetHealth;
      setData(j);
      setError(null);
      setLastRefresh(Date.now());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [load]);

  if (loading && !data) {
    return <div style={{ padding: 24 }}>Loading fleet health…</div>;
  }
  if (error && !data) {
    return (
      <div style={{ padding: 24, color: '#ef4444' }}>
        Failed to load fleet health: {error}
      </div>
    );
  }
  if (!data) return null;

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, marginBottom: 4 }}>MCP Fleet Health</h1>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
        generated_at: {data.generated_at} · auto-refresh 10s · last refresh{' '}
        {lastRefresh ? new Date(lastRefresh).toLocaleTimeString() : 'never'}
      </div>

      {/* Section 1 — MCP fleet */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>
          MCP servers ({data.total_servers})
        </h2>
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>
          {Object.entries(data.by_status).map(([s, n]) => (
            <span key={s} style={{ marginRight: 16 }}>
              <StatusBadge status={s} /> <strong>{n}</strong>
            </span>
          ))}
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f3f4f6', textAlign: 'left' }}>
              <th style={{ padding: 8 }}>Namespace</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Tools</th>
              <th style={{ padding: 8 }}>R/W</th>
              <th style={{ padding: 8 }}>Notes</th>
            </tr>
          </thead>
          <tbody>
            {data.servers.map((s) => (
              <tr key={s.namespace} style={{ borderBottom: '1px solid #e5e7eb' }}>
                <td style={{ padding: 8, fontFamily: 'monospace' }}>{s.namespace}</td>
                <td style={{ padding: 8 }}>
                  <StatusBadge status={s.status} />
                </td>
                <td style={{ padding: 8 }}>{s.tools_total}</td>
                <td style={{ padding: 8 }}>
                  <span style={{ color: '#22c55e' }}>{s.tools_read}r</span>
                  {' / '}
                  <span style={{ color: s.tools_write ? '#ef4444' : '#9ca3af' }}>
                    {s.tools_write}w
                  </span>
                </td>
                <td style={{ padding: 8, color: '#6b7280', fontSize: 12 }}>
                  {s.notes.slice(0, 2).join('; ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Section 2 — Ollama */}
      {data.ollama && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>
            Ollama models ({data.ollama.installed_models.length} installed,{' '}
            {data.ollama.loaded_models.length} in VRAM)
          </h2>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
            base_url: {data.ollama.base_url} ·{' '}
            {data.ollama.reachable ? '✓ reachable' : '✗ unreachable'}
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f3f4f6', textAlign: 'left' }}>
                <th style={{ padding: 8 }}>Model</th>
                <th style={{ padding: 8 }}>Family</th>
                <th style={{ padding: 8 }}>Size (GB)</th>
                <th style={{ padding: 8 }}>State</th>
              </tr>
            </thead>
            <tbody>
              {data.ollama.installed_models.map((m) => (
                <tr key={m.name} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 8, fontFamily: 'monospace' }}>{m.name}</td>
                  <td style={{ padding: 8 }}>{m.family}</td>
                  <td style={{ padding: 8 }}>{m.size_gb.toFixed(2)}</td>
                  <td style={{ padding: 8 }}>
                    <StatusBadge
                      status={
                        data.ollama!.loaded_models.includes(m.name)
                          ? 'WORKING'
                          : 'SLEEPING'
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Section 3 — Council */}
      {data.council && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>
            Council nodes ({data.council.nodes.length})
          </h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f3f4f6', textAlign: 'left' }}>
                <th style={{ padding: 8 }}>Role</th>
                <th style={{ padding: 8 }}>Aliases</th>
                <th style={{ padding: 8 }}>Model</th>
                <th style={{ padding: 8 }}>State</th>
              </tr>
            </thead>
            <tbody>
              {data.council.nodes.map((n) => (
                <tr key={n.role} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 8, fontWeight: 600 }}>{n.role}</td>
                  <td style={{ padding: 8, fontSize: 12, color: '#6b7280' }}>
                    {n.aliases.join(', ') || '—'}
                  </td>
                  <td style={{ padding: 8, fontFamily: 'monospace' }}>{n.model}</td>
                  <td style={{ padding: 8 }}>
                    <StatusBadge
                      status={n.ollama_available ? 'WORKING' : 'NOT_INSTALLED'}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Section 4 — Backend services */}
      {data.backends && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>
            Backend services ({data.backends.services.length})
          </h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f3f4f6', textAlign: 'left' }}>
                <th style={{ padding: 8 }}>Service</th>
                <th style={{ padding: 8 }}>State</th>
                <th style={{ padding: 8 }}>Operations</th>
                <th style={{ padding: 8 }}>Description</th>
              </tr>
            </thead>
            <tbody>
              {data.backends.services.map((s) => (
                <tr key={s.name} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 8, fontFamily: 'monospace', fontWeight: 600 }}>
                    {s.name}
                  </td>
                  <td style={{ padding: 8 }}>
                    <StatusBadge status={s.status} />
                  </td>
                  <td style={{ padding: 8, fontSize: 12 }}>
                    {s.operations.slice(0, 3).join(', ')}
                    {s.operations.length > 3 ? `… (+${s.operations.length - 3})` : ''}
                  </td>
                  <td style={{ padding: 8, color: '#6b7280', fontSize: 12 }}>
                    {s.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {error && (
        <div style={{ marginTop: 16, color: '#f59e0b', fontSize: 12 }}>
          last refresh failed: {error} (using cached snapshot)
        </div>
      )}
    </div>
  );
}
