'use client';

import { useEffect, useState, useCallback } from 'react';

type Snapshot = {
  data: {
    as_of: string;
    infrastructure: {
      ollama_installed: { name: string; size_bytes: number }[];
      ollama_loaded: { name: string; size_vram?: number }[];
      ollama_count: number;
    };
    agents: {
      orchestrator_roles: string[];
      experts_registry: string[];
      mcp_servers: string[];
    };
    drills: { total: number; recent: string[] };
    council: {
      total_runs: number;
      unique_issues: number;
      most_recent: {
        ts?: string;
        id?: string;
        chain?: Record<string, { model: string; tokens: number; latency_s: number }>;
      }[];
    };
    fixtures: { name: string; size: number }[];
  };
  correlation_id: string;
};

function fmtBytes(n?: number): string {
  if (!n) return '—';
  const gb = n / 1024 / 1024 / 1024;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(n / 1024 / 1024).toFixed(0)} MB`;
}

function fmtTime(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 12,
        background: color,
        color: '#fff',
        fontSize: 11,
        fontWeight: 600,
        marginRight: 6,
      }}
    >
      {label}
    </span>
  );
}

export default function SimulationHub() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/simulation', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setSnap(j);
      setError(null);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(refresh, 10000);
    return () => clearInterval(id);
  }, [autoRefresh, refresh]);

  if (error) return <div style={{ padding: 20, color: '#c33' }}>Error: {error}</div>;
  if (!snap) return <div style={{ padding: 20 }}>Loading…</div>;

  const d = snap.data;

  return (
    <div style={{ padding: 20 }}>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">🛰 Simulation hub — live agent + tool state</h1>
          <p className="page-subtitle">
            Real-data view of the agentic stack: MCP servers, agent roles,
            experts registry, recent council runs, drill catalog, Ollama
            inventory, multimodal fixtures. Backed by{' '}
            <code>/api/v1/simulation</code>. Auto-refresh every 10s.
            <br />
            <strong>As of:</strong> <code>{fmtTime(d.as_of)}</code> ·{' '}
            <strong>correlation_id:</strong>{' '}
            <code>{snap.correlation_id.slice(0, 12)}…</code>
          </p>
        </div>
        <label style={{ float: 'right' }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />{' '}
          Auto-refresh
        </label>
      </div>

      {/* INFRASTRUCTURE */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>🖥 Infrastructure — Ollama runtime</strong>
        <div style={{ display: 'flex', gap: 24, marginTop: 8 }}>
          <div>
            <div style={{ fontWeight: 600 }}>Installed ({d.infrastructure.ollama_count})</div>
            <ul style={{ paddingLeft: 18, marginTop: 4, fontSize: 13 }}>
              {d.infrastructure.ollama_installed.map((m) => (
                <li key={m.name}>
                  <code>{m.name}</code> · {fmtBytes(m.size_bytes)}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div style={{ fontWeight: 600 }}>Loaded in VRAM</div>
            {d.infrastructure.ollama_loaded.length === 0 ? (
              <p style={{ color: '#666', fontSize: 13 }}>(none — model loads on next call)</p>
            ) : (
              <ul style={{ paddingLeft: 18, marginTop: 4, fontSize: 13 }}>
                {d.infrastructure.ollama_loaded.map((m) => (
                  <li key={m.name}>
                    <code>{m.name}</code> · {fmtBytes(m.size_vram)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {/* AGENTS */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>🤖 Agents — what's wired</strong>
        <div style={{ display: 'flex', gap: 24, marginTop: 8, fontSize: 13 }}>
          <div>
            <div style={{ fontWeight: 600 }}>
              Orchestrator roles ({d.agents.orchestrator_roles.length})
            </div>
            <ul style={{ paddingLeft: 18 }}>
              {d.agents.orchestrator_roles.map((r) => (
                <li key={r}>
                  <Pill label={r} color="#1e3a8a" />
                </li>
              ))}
            </ul>
            <p style={{ color: '#666', fontSize: 11 }}>
              Source: <code>services/agent-orchestrator-svc/app/agent_registry.py</code>
            </p>
          </div>
          <div>
            <div style={{ fontWeight: 600 }}>
              Experts ({d.agents.experts_registry.length})
            </div>
            <ul style={{ paddingLeft: 18 }}>
              {d.agents.experts_registry.map((e) => (
                <li key={e}>
                  <Pill label={e} color="#0f766e" />
                </li>
              ))}
            </ul>
            <p style={{ color: '#666', fontSize: 11 }}>
              Source: <code>~/.claude/scripts/experts.py</code> (global)
            </p>
          </div>
          <div>
            <div style={{ fontWeight: 600 }}>
              MCP servers ({d.agents.mcp_servers.length})
            </div>
            <ul style={{ paddingLeft: 18 }}>
              {d.agents.mcp_servers.map((m) => (
                <li key={m}>
                  <Pill label={m} color="#92400e" />
                </li>
              ))}
            </ul>
            <p style={{ color: '#666', fontSize: 11 }}>
              Source: <code>mcp/server_*.py</code>
            </p>
          </div>
        </div>
      </div>

      {/* COUNCIL */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>
          🏛 Council — empirically-validated multi-model fix proposals
        </strong>
        <div style={{ marginTop: 8, fontSize: 13 }}>
          <p>
            <strong>Total council audit rows:</strong> {d.council.total_runs} ·{' '}
            <strong>Unique issues exercised:</strong> {d.council.unique_issues}
          </p>
          {d.council.most_recent.length > 0 && (
            <table style={{ width: '100%', marginTop: 8, fontSize: 12 }}>
              <thead>
                <tr>
                  <th align="left">When</th>
                  <th align="left">Issue</th>
                  <th align="left">Author tokens</th>
                  <th align="left">Reviewer tokens</th>
                  <th align="left">Advisor tokens</th>
                </tr>
              </thead>
              <tbody>
                {d.council.most_recent
                  .slice()
                  .reverse()
                  .map((r, idx) => (
                    <tr key={idx}>
                      <td>{fmtTime(r.ts)}</td>
                      <td>
                        <code>{r.id?.slice(0, 40)}…</code>
                      </td>
                      <td>{r.chain?.author?.tokens ?? '—'}</td>
                      <td>{r.chain?.reviewer?.tokens ?? '—'}</td>
                      <td>{r.chain?.advisor?.tokens ?? '—'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* DRILLS */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>
          🔬 Drill catalog — regression contracts ({d.drills.total} total)
        </strong>
        <div style={{ marginTop: 8, fontSize: 13 }}>
          <p>
            Each drill runs on the real stack (no mocks per ADR-011) with at
            least one NEGATIVE marker. Run all via{' '}
            <code>scripts/run_drills.py --parallel 4</code>.
          </p>
          <details>
            <summary>10 most-recent drill files</summary>
            <ul style={{ paddingLeft: 18, marginTop: 6 }}>
              {d.drills.recent.map((dr) => (
                <li key={dr}>
                  <code>{dr}</code>
                </li>
              ))}
            </ul>
          </details>
        </div>
      </div>

      {/* FIXTURES */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>📁 Multi-modal test fixtures</strong>
        <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
          <thead>
            <tr>
              <th align="left">File</th>
              <th align="right">Size</th>
              <th align="left">Use</th>
            </tr>
          </thead>
          <tbody>
            {d.fixtures.map((f) => (
              <tr key={f.name}>
                <td>
                  <code>tests/fixtures/multimodal/{f.name}</code>
                </td>
                <td align="right">{f.size} B</td>
                <td>
                  {f.name.endsWith('.txt')
                    ? 'unique phrase: blue elephant'
                    : f.name.endsWith('.csv')
                      ? 'unique phrase: orange porcupine'
                      : f.name.endsWith('.json')
                        ? 'unique phrase: yellow zebra'
                        : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* OPERATIONAL ENTRY POINTS */}
      <div className="card" style={{ marginTop: 16 }}>
        <strong>⚡ Operator commands</strong>
        <table style={{ width: '100%', marginTop: 8, fontSize: 13 }}>
          <tbody>
            <tr>
              <td>Verify every component</td>
              <td>
                <code>bash scripts/verify-stack.sh</code>
              </td>
            </tr>
            <tr>
              <td>Load test (smoke / 15s)</td>
              <td>
                <code>bash scripts/load-test.sh smoke</code>
              </td>
            </tr>
            <tr>
              <td>Load test (full / 22 min)</td>
              <td>
                <code>bash scripts/load-test.sh full</code>
              </td>
            </tr>
            <tr>
              <td>Issue scan + dispatch</td>
              <td>
                <code>python3 scripts/issue_scanner.py --include-mypy --include-bandit --include-eslint</code>
              </td>
            </tr>
            <tr>
              <td>Council on one issue</td>
              <td>
                <code>python3 scripts/issue_dispatcher.py --council --id &lt;issue-id&gt;</code>
              </td>
            </tr>
            <tr>
              <td>Bring up Istio (minikube)</td>
              <td>
                <code>bash scripts/istio-up.sh</code>
              </td>
            </tr>
            <tr>
              <td>Run all drills</td>
              <td>
                <code>python3 scripts/run_drills.py --parallel 4</code>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p style={{ marginTop: 16, color: '#666', fontSize: 12 }}>
        Composes with: <code>/admin/local-models</code>,{' '}
        <code>/admin/agentic/control-plane</code>,{' '}
        <code>/admin/agent-registry/deep</code>,{' '}
        <code>/admin/forensics</code>. See{' '}
        <code>docs/STATUS.md</code> + <code>docs/MISSING.md</code> +{' '}
        <code>docs/runbooks/component-trust.md</code> for canonical state.
      </p>
    </div>
  );
}
