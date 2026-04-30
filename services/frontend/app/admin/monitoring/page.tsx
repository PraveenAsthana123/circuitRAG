'use client';

import Link from 'next/link';
import { useEffect, useState, type CSSProperties } from 'react';

import {
  type AgenticRole,
  type AgenticTask,
  api,
  ApiError,
  type FrontendBuildInfoResponse,
  type HealthDetailedResponse,
  type HealthToolsResponse,
  type HealthUpstreamsResponse,
  type RuntimeStatusResponse,
} from '../../../lib/api';

const REFRESH_INTERVAL_MS = 10_000;
const MONITORING_LINKS = [
  {
    label: 'Grafana',
    href: process.env.NEXT_PUBLIC_GRAFANA_URL ?? 'http://localhost:3001',
    note: 'Dashboards and time-series panels.',
  },
  {
    label: 'Prometheus',
    href: process.env.NEXT_PUBLIC_PROMETHEUS_URL ?? 'http://localhost:9090',
    note: 'Scrape targets, rules, and raw metrics.',
  },
  {
    label: 'Jaeger',
    href: process.env.NEXT_PUBLIC_JAEGER_URL ?? 'http://localhost:16686',
    note: 'Trace search and span waterfall.',
  },
  {
    label: 'Alertmanager',
    href: process.env.NEXT_PUBLIC_ALERTMANAGER_URL ?? 'http://localhost:9093',
    note: 'Alert grouping, routing, and receiver inspection.',
  },
];
const LOCAL_STACK = [
  { name: 'Postgres', port: '55432', role: 'primary relational store with schema-per-service + RLS' },
  { name: 'Redis', port: '56379', role: 'cache, sessions, and rate-limit counters' },
  { name: 'Kafka', port: '59092 / 9094', role: 'event backbone and external listener' },
  { name: 'MinIO', port: '59000 / 59001', role: 'S3-compatible document/blob storage + console' },
  { name: 'Qdrant', port: '6333 / 6334', role: 'vector database HTTP + gRPC' },
  { name: 'Neo4j', port: '7474 / 7687', role: 'knowledge graph browser + bolt' },
  { name: 'Ollama', port: '51134', role: 'local LLM and embeddings runtime on this dev host' },
  { name: 'OTel collector', port: '4317 / 4318 / 9464', role: 'OTLP ingest and Prometheus re-export' },
  { name: 'Node exporter', port: '9100', role: 'host CPU, memory, filesystem, and kernel metrics' },
  { name: 'cAdvisor', port: '8089', role: 'container CPU, memory, filesystem, and saturation metrics' },
  { name: 'Prometheus', port: '9090', role: 'metrics scraping and rules engine' },
  { name: 'Alertmanager', port: '9093', role: 'alert grouping and receiver routing' },
  { name: 'Grafana', port: '3001', role: 'dashboards and visualization' },
  { name: 'Jaeger', port: '16686', role: 'trace UI and OTLP trace sink' },
  { name: 'NGINX', port: '80 / 443', role: 'edge, TLS termination, cache, and rate limiting' },
  { name: 'Elasticsearch + Kibana', port: '9200 / 5601', role: 'log indexing and UI' },
  { name: 'Kiali', port: '20001', role: 'service-mesh visualization companion' },
];
const OPERATION_SURFACES = [
  {
    name: 'Operator dashboard',
    href: '/admin',
    note: 'Live health, breakers, prompts, tools, upstream probes, and agentic summary.',
  },
  {
    name: 'Monitoring + health',
    href: '/admin/monitoring',
    note: 'This page: technical operations map plus live status.',
  },
  {
    name: 'Sidecar telemetry',
    href: '/admin/sidecar/telemetry',
    note: 'Council histogram, filter stats, verdict chain, and telemetry UI.',
  },
  {
    name: 'Forensics',
    href: '/admin/forensics',
    note: 'Trace → draft → audit → HITL reconstruction path.',
  },
  {
    name: 'Agentic control plane',
    href: '/admin/agentic/control-plane',
    note: 'Project plan rows, task runs, approvals, and memories.',
  },
];
const AUTOMATIONS = [
  {
    name: 'Loop status',
    command: 'python3 scripts/loop_status.py',
    note: 'One-shot operator health report across advisor.db, drills, watcher log, council log, and Ollama.',
  },
  {
    name: 'Readonly drill status refresh',
    command: 'python3 scripts/write_drill_status.py --only-readonly',
    note: 'Refreshes the canonical drill snapshot used by watcher and pre-commit.',
  },
  {
    name: 'Council stats snapshot',
    command: 'python3 scripts/council_stats_snapshot.py',
    note: 'Writes daily council telemetry snapshot.',
  },
  {
    name: 'Filter pipeline',
    command: 'scripts/run_filter_pipeline.sh --prometheus-out <file>',
    note: 'Snapshot + Prometheus export + alert/webhook pipeline.',
  },
  {
    name: 'Drill runner',
    command: 'python3 scripts/run_drills.py --parallel 4',
    note: 'Primary readonly drill execution path.',
  },
];
const DATA_PATHS = [
  '.loop/ — watcher log, council logs, drill snapshot, rendered dashboard',
  'advisor.db — sidecar advisor events, memory, council runs, ratings',
  'data/prometheus — Prometheus TSDB',
  'data/grafana — Grafana state and dashboards',
  'data/nginx-* — TLS, cache, and access/error logs',
  'data/minio, data/postgres, data/qdrant, data/neo4j, data/kafka, data/redis — local persistence',
];
const CIRCUIT_BREAKER_IMPLEMENTATIONS = [
  {
    name: 'Base circuit breaker',
    codePath: 'libs/py/documind_core/circuit_breaker.py',
    protects: 'generic dependency calls with CLOSED / HALF_OPEN / OPEN state transitions',
  },
  {
    name: 'RetrievalCircuitBreaker',
    codePath: 'libs/py/documind_core/breakers.py',
    protects: 'retrieval quality drift and mostly-empty result sets before they silently degrade answers',
  },
  {
    name: 'TokenBudgetCircuitBreaker',
    codePath: 'libs/py/documind_core/breakers.py',
    protects: 'per-request and daily token budget overruns before expensive generation starts',
  },
  {
    name: 'AgentLoopCircuitBreaker',
    codePath: 'libs/py/documind_core/breakers.py',
    protects: 'runaway agent/tool loops, max-step overruns, and tool-budget blowups',
  },
  {
    name: 'ObservabilityCircuitBreaker',
    codePath: 'libs/py/documind_core/breakers.py',
    protects: 'OTel / exporter outages so telemetry failure does not cascade into app failure',
  },
  {
    name: 'CognitiveCircuitBreaker',
    codePath: 'libs/py/documind_core/breakers.py',
    protects: 'unsafe or self-contradictory generation trajectories based on warning/interrupt signals',
  },
  {
    name: 'Embedder client breaker',
    codePath: 'services/retrieval-svc/app/services/embedder_client.py',
    protects: 'embedding dependency failures inside retrieval service',
  },
  {
    name: 'Hybrid retriever vector/graph breakers',
    codePath: 'services/retrieval-svc/app/services/hybrid_retriever.py',
    protects: 'vector and graph retrieval dependency paths plus quality-aware retrieval fallback',
  },
];
const IDENTITY_SURFACES = [
  {
    name: 'API gateway + tenant headers',
    href: '/tools/api-gateway',
    note: 'Ingress, request routing, correlation IDs, and tenant-aware API entry.',
  },
  {
    name: 'RBAC + ABAC',
    href: '/admin/rbac/deep',
    note: 'Authorization model and role/policy enforcement surface.',
  },
  {
    name: 'SSO',
    href: '/admin/sso/deep',
    note: 'OIDC / SAML login integration design surface.',
  },
  {
    name: 'LDAP',
    href: '/admin/ldap/deep',
    note: 'Enterprise directory sync and identity-source integration.',
  },
];
const OPERATIONS_STATUS = {
  done: [
    'Admin monitoring route and left-menu entry exist at /admin/monitoring.',
    'Live service health, circuit breakers, upstream reachability, and tool traffic are visible in-app.',
    'Sidecar telemetry, forensics, and agentic control-plane surfaces are already linked and reachable.',
    'Prometheus, Alertmanager, Grafana, Jaeger, OTel collector, ELK, and Kiali are defined in local compose.',
    'Node exporter and cAdvisor are defined in local compose for host and container metrics.',
    'Loop automation paths exist: loop_status, drill refresh, council snapshots, and filter pipeline.',
    'Grafana dashboard provisioning is automatic and Prometheus loads local alert rules.',
    'Alertmanager receiver routing is now configurable from compose env without hand-editing the config file.',
  ],
  inProgress: [
    'Monitoring page is now acting as the central operations map, but it still depends on downstream health endpoints for live data.',
    'Alertmanager is local-first: the shared receiver contract exists, but real delivery depends on a supplied webhook URL and receiver selection.',
    'Tracking is current-state-heavy; trends and incident timelines are not yet persisted in this UI.',
  ],
  pending: [
    'A real shared-environment webhook/notification secret wired into Alertmanager at deployment time.',
    'Historical tracking for alerts, scraper failures, and upstream flapping.',
    'Operator acknowledgements, issue ownership, and resolved-state workflow.',
  ],
};
const PIPELINE_FLOW = [
  {
    name: 'Input',
    items: [
      'Operator/admin requests through the frontend and API gateway.',
      'MCP tool calls and tenant-aware API traffic.',
      'OTLP telemetry into the collector.',
      'Loop artifacts: watcher log, council log, drill snapshot, advisor.db.',
    ],
  },
  {
    name: 'Process',
    items: [
      'Health APIs aggregate readiness, breakers, prompt registry, tools, and upstream probes.',
      'Prometheus scrapes node-exporter, cAdvisor, OTel, and application /metrics targets, then forwards firing rules into Alertmanager.',
      'Sidecar advisor records events, ratings, council runs, and memory.',
      'Loop automation refreshes drill state, council telemetry, and watcher verdicts.',
    ],
  },
  {
    name: 'Output',
    items: [
      'In-app operator pages: monitoring, forensics, sidecar telemetry, agentic control plane.',
      'External observability UIs: Grafana, Prometheus, Alertmanager, Jaeger, Kibana, Kiali.',
      'Persistent audit/state artifacts in .loop/, advisor.db, and data/* stores.',
      'Operational decisions: approvals, ratings, drill outcomes, and trace evidence.',
    ],
  },
];

function fmtWhen(value: string): string {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

function fmtUptime(value: number): string {
  if (value < 60) return `${Math.floor(value)}s`;
  if (value < 3600) return `${Math.floor(value / 60)}m ${Math.floor(value % 60)}s`;
  return `${Math.floor(value / 3600)}h ${Math.floor((value % 3600) / 60)}m`;
}

function statusTone(ok: boolean): CSSProperties {
  return {
    color: ok ? '#166534' : '#991b1b',
    background: ok ? '#dcfce7' : '#fee2e2',
    borderRadius: 999,
    padding: '2px 10px',
    fontSize: 12,
    fontWeight: 700,
    display: 'inline-block',
  };
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

export default function MonitoringPage() {
  const [health, setHealth] = useState<HealthDetailedResponse | null>(null);
  const [upstreams, setUpstreams] = useState<HealthUpstreamsResponse | null>(null);
  const [tools, setTools] = useState<HealthToolsResponse | null>(null);
  const [buildInfo, setBuildInfo] = useState<FrontendBuildInfoResponse | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatusResponse | null>(null);
  const [agentRoles, setAgentRoles] = useState<AgenticRole[]>([]);
  const [agentTasks, setAgentTasks] = useState<AgenticTask[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [healthResp, upstreamsResp, toolsResp, buildResp, runtimeResp, rolesResp, tasksResp] = await Promise.all([
          api.healthDetailed(),
          api.healthUpstreams(),
          api.healthTools(),
          api.frontendBuildInfo(),
          api.frontendRuntimeStatus(),
          api.agenticListAgents(),
          api.agenticListTasks({ limit: 25 }),
        ]);
        if (cancelled) return;
        setHealth(healthResp);
        setUpstreams(upstreamsResp);
        setTools(toolsResp);
        setBuildInfo(buildResp);
        setRuntime(runtimeResp);
        setAgentRoles(rolesResp);
        setAgentTasks(tasksResp);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const timer = setInterval(() => {
      void load();
    }, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const readiness = health ? Object.entries(health.readiness) : [];
  const readyCount = readiness.filter(([, state]) => state === 'ready').length;
  const totalUpstreams = upstreams?.upstreams.length ?? 0;
  const reachableUpstreams = upstreams?.upstreams.filter((row) => row.reachable).length ?? 0;
  const unreachableNamespaces = tools?.unreachable.length ?? 0;
  const totalToolCalls = tools?.tools.reduce(
    (sum, row) => sum + Object.values(row.calls).reduce((acc, value) => acc + value, 0),
    0,
  ) ?? 0;
  const readinessScore = readiness.length === 0 ? null : clampScore((readyCount / readiness.length) * 100);
  const upstreamScore = totalUpstreams === 0 ? null : clampScore((reachableUpstreams / totalUpstreams) * 100);
  const toolFreshnessScore = tools
    ? clampScore(((Math.max(tools.tools.length - unreachableNamespaces, 0)) / Math.max(tools.tools.length, 1)) * 100)
    : null;
  const overallScore = [readinessScore, upstreamScore, toolFreshnessScore]
    .filter((value): value is number => value != null)
    .reduce((sum, value, _idx, arr) => sum + value / arr.length, 0);
  const overallStatus =
    error ? 'degraded'
      : overallScore >= 95 ? 'healthy'
      : overallScore >= 75 ? 'watch'
      : 'critical';
  const activeTaskStatuses = new Set([
    'pending',
    'running',
    'waiting_for_approval',
    'waiting_for_plan_approval',
    'approved',
    'in_progress',
  ]);
  const activeTasks = agentTasks.filter((task) => activeTaskStatuses.has(task.status));
  const runningServices = runtime?.services.filter((row) => row.state === 'running') ?? [];
  const notRunningServices = runtime?.services.filter((row) => row.state !== 'running') ?? [];
  const activeServiceRows = runningServices.slice(0, 12).map((row) => ({
    name: row.service,
    kind: row.source,
    status: row.health === 'unhealthy' ? 'degraded' : 'running',
    detail: `${row.status}${row.cpu_percent ? ` · cpu=${row.cpu_percent}` : ''}${row.mem_usage ? ` · mem=${row.mem_usage}` : ''}`,
  }));

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Monitoring + health</h1>
          <p className="page-subtitle">
            Live operator view for service health, upstream reachability, MCP/tool traffic, and the
            external observability UIs already wired in the local stack.
          </p>
        </div>
        <div className="page-actions">
          <Link className="btn" href="/admin">
            Open operator dashboard
          </Link>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div
        style={{
          display: 'grid',
          gap: 12,
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          marginBottom: 24,
        }}
      >
        <div className="surface-muted">
          <div className="result-meta">Overall score</div>
          <strong style={{ fontSize: 24 }}>
            {health || upstreams || tools ? `${clampScore(overallScore)}/100` : loading ? '…' : 'n/a'}
          </strong>
          <div className="field-help">current operational score</div>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Current status</div>
          <strong style={{ fontSize: 24 }}>{health || upstreams || tools ? overallStatus : loading ? '…' : 'n/a'}</strong>
          <div className="field-help">healthy · watch · degraded · critical</div>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Services running</div>
          <strong style={{ fontSize: 24 }}>{runtime ? runtime.totals.running : loading ? '…' : 'n/a'}</strong>
          <div className="field-help">compose services currently running</div>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Agents active</div>
          <strong style={{ fontSize: 24 }}>{loading ? '…' : activeTasks.length}</strong>
          <div className="field-help">in-flight agentic tasks</div>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Core health</div>
          <strong style={{ fontSize: 24 }}>
            {health ? `${readyCount}/${readiness.length}` : loading ? '…' : 'n/a'}
          </strong>
          <div className="field-help">ready checks passing</div>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Upstreams</div>
          <strong style={{ fontSize: 24 }}>
            {upstreams ? `${reachableUpstreams}/${totalUpstreams}` : loading ? '…' : 'n/a'}
          </strong>
          <div className="field-help">reachable probes</div>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Tool calls</div>
          <strong style={{ fontSize: 24 }}>{tools ? totalToolCalls : loading ? '…' : 'n/a'}</strong>
          <div className="field-help">aggregated MCP requests</div>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Stale namespaces</div>
          <strong style={{ fontSize: 24 }}>
            {tools ? unreachableNamespaces : loading ? '…' : 'n/a'}
          </strong>
          <div className="field-help">metrics scrapes failing</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Score and current status</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          }}
        >
          <div className="surface-muted">
            <strong>Readiness score</strong>
            <div style={{ marginTop: 10, fontSize: 24, fontWeight: 700 }}>
              {readinessScore != null ? `${readinessScore}/100` : 'n/a'}
            </div>
            <div className="field-help" style={{ marginTop: 8 }}>
              derived from service readiness checks
            </div>
          </div>
          <div className="surface-muted">
            <strong>Upstream score</strong>
            <div style={{ marginTop: 10, fontSize: 24, fontWeight: 700 }}>
              {upstreamScore != null ? `${upstreamScore}/100` : 'n/a'}
            </div>
            <div className="field-help" style={{ marginTop: 8 }}>
              reachable dependency probes
            </div>
          </div>
          <div className="surface-muted">
            <strong>Metrics freshness score</strong>
            <div style={{ marginTop: 10, fontSize: 24, fontWeight: 700 }}>
              {toolFreshnessScore != null ? `${toolFreshnessScore}/100` : 'n/a'}
            </div>
            <div className="field-help" style={{ marginTop: 8 }}>
              tool namespaces with working scrapes
            </div>
          </div>
          <div className="surface-muted">
            <strong>Current interpretation</strong>
            <div style={{ marginTop: 10, fontSize: 24, fontWeight: 700 }}>
              {overallStatus}
            </div>
            <div className="field-help" style={{ marginTop: 8 }}>
              computed from live page data, not manual labels
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>System monitoring theme</h2>
        <div className="field-help" style={{ marginBottom: 12 }}>
          The repo already splits operations into five layers: infra containers, app health APIs,
          sidecar telemetry, agentic control-plane state, and offline drill/audit automation.
          This page is the technical map tying those surfaces together.
        </div>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          }}
        >
          {OPERATION_SURFACES.map((item) => (
            <Link
              key={item.href}
              className="surface-muted"
              href={item.href}
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <strong>{item.name}</strong>
              <div className="field-help" style={{ marginTop: 8 }}>{item.note}</div>
              <div style={{ marginTop: 10 }}>
                <code>{item.href}</code>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Input, process, output</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          }}
        >
          {PIPELINE_FLOW.map((section) => (
            <div key={section.name} className="surface-muted">
              <strong>{section.name}</strong>
              <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                {section.items.map((item) => (
                  <div key={item} className="field-help">{item}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Tracking, login, and observability map</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            marginBottom: 16,
          }}
        >
          {IDENTITY_SURFACES.map((item) => (
            <Link
              key={item.href}
              className="surface-muted"
              href={item.href}
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <strong>{item.name}</strong>
              <div className="field-help" style={{ marginTop: 8 }}>{item.note}</div>
              <div style={{ marginTop: 10 }}>
                <code>{item.href}</code>
              </div>
            </Link>
          ))}
        </div>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          }}
        >
          <div className="surface-muted">
            <strong>Done</strong>
            <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
              {OPERATIONS_STATUS.done.map((item) => (
                <div key={item} className="field-help">{item}</div>
              ))}
            </div>
          </div>
          <div className="surface-muted">
            <strong>Work in progress</strong>
            <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
              {OPERATIONS_STATUS.inProgress.map((item) => (
                <div key={item} className="field-help">{item}</div>
              ))}
            </div>
          </div>
          <div className="surface-muted">
            <strong>Pending</strong>
            <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
              {OPERATIONS_STATUS.pending.map((item) => (
                <div key={item} className="field-help">{item}</div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Monitoring UIs</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          }}
        >
          {MONITORING_LINKS.map((item) => (
            <a
              key={item.label}
              className="surface-muted"
              href={item.href}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <strong>{item.label}</strong>
              <div className="field-help" style={{ marginTop: 8 }}>{item.note}</div>
              <div style={{ marginTop: 10 }}>
                <code>{item.href}</code>
              </div>
            </a>
          ))}
          <Link className="surface-muted" href="/admin/sidecar/telemetry" style={{ textDecoration: 'none', color: 'inherit' }}>
            <strong>Sidecar telemetry</strong>
            <div className="field-help" style={{ marginTop: 8 }}>
              Council histogram and verdict-log telemetry inside the app.
            </div>
            <div style={{ marginTop: 10 }}>
              <code>/admin/sidecar/telemetry</code>
            </div>
          </Link>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Active or running services</h2>
        <div className="field-help" style={{ marginBottom: 12 }}>
          Runtime state from local compose plus `docker stats`, with Ollama status checked via
          `systemctl is-active`.
        </div>
        {runtime?.warnings.length ? (
          <div className="error" style={{ marginBottom: 12 }}>
            {runtime.warnings.join(' · ')}
          </div>
        ) : null}
        <div style={{ display: 'grid', gap: 10 }}>
          {activeServiceRows.map((row) => (
            <div key={`${row.kind}:${row.name}`} className="surface-muted">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <div>
                  <strong>{row.name}</strong>{' '}
                  <span className="field-help">({row.kind})</span>
                </div>
                <span style={statusTone(row.status === 'running')}>{row.status}</span>
              </div>
              <div className="field-help" style={{ marginTop: 8 }}>{row.detail}</div>
            </div>
          ))}
          {activeServiceRows.length === 0 && (
            <div className="field-help">{loading ? 'Loading service activity…' : 'No live activity rows available.'}</div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Services not running or unhealthy</h2>
        <div style={{ display: 'grid', gap: 10 }}>
          {runtime ? (
            <>
              <div className="surface-muted">
                <strong>Ollama</strong>
                <div className="field-help" style={{ marginTop: 8 }}>
                  state={runtime.ollama.state} · active={String(runtime.ollama.active)}
                </div>
              </div>
              {runtime.services
                .filter((row) => row.state !== 'running' || row.health === 'unhealthy')
                .map((row) => (
                  <div key={row.name} className="surface-muted">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                      <strong>{row.service}</strong>
                      <span style={statusTone(false)}>
                        {row.state !== 'running' ? row.state : row.health ?? 'unhealthy'}
                      </span>
                    </div>
                    <div className="field-help" style={{ marginTop: 8 }}>
                      {row.status}{row.ports ? ` · ports=${row.ports}` : ''}
                    </div>
                  </div>
                ))}
              {notRunningServices.length === 0 && runtime.services.every((row) => row.health !== 'unhealthy') && (
                <div className="field-help">No compose services currently show non-running or unhealthy state.</div>
              )}
            </>
          ) : (
            <div className="field-help">{loading ? 'Loading runtime status…' : 'No runtime status loaded.'}</div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Agent activity</h2>
        <div className="field-help" style={{ marginBottom: 12 }}>
          This shows configured agent roles plus in-flight agentic tasks. It is task-level activity,
          not per-model thread occupancy.
        </div>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            marginBottom: 16,
          }}
        >
          <div className="surface-muted">
            <div className="result-meta">Configured roles</div>
            <strong style={{ fontSize: 24 }}>{agentRoles.length}</strong>
            <div className="field-help">available agent role bindings</div>
          </div>
          <div className="surface-muted">
            <div className="result-meta">Active tasks</div>
            <strong style={{ fontSize: 24 }}>{activeTasks.length}</strong>
            <div className="field-help">non-terminal agentic workflows</div>
          </div>
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          {activeTasks.slice(0, 10).map((task) => (
            <div key={task.task_id} className="surface-muted">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <strong>{task.goal}</strong>
                <span style={statusTone(task.status === 'running' || task.status === 'approved')}>
                  {task.status}
                </span>
              </div>
              <div className="field-help" style={{ marginTop: 8 }}>
                risk={task.risk_level} · tool={task.tool_namespace ?? 'n/a'}.{task.tool_name ?? 'n/a'}
              </div>
              {(task.next_action || task.advisor_summary) && (
                <div className="field-help" style={{ marginTop: 8 }}>
                  doing: {task.next_action ?? task.advisor_summary}
                </div>
              )}
            </div>
          ))}
          {activeTasks.length === 0 && (
            <div className="field-help">{loading ? 'Loading agent activity…' : 'No active agentic tasks right now.'}</div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Resource consumers</h2>
        <div className="field-help" style={{ marginBottom: 12 }}>
          Top local compose consumers from `docker stats --no-stream`.
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          {runtime?.top_consumers.map((row) => (
            <div key={row.name} className="surface-muted">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <strong>{row.service}</strong>
                <code>{row.cpu_percent ?? 'n/a'}</code>
              </div>
              <div className="field-help" style={{ marginTop: 8 }}>
                mem={row.mem_usage ?? 'n/a'} ({row.mem_percent ?? 'n/a'}) · net={row.net_io ?? 'n/a'} · pids={row.pids ?? 'n/a'}
              </div>
            </div>
          )) ?? null}
          {!runtime?.top_consumers.length && (
            <div className="field-help">{loading ? 'Loading resource usage…' : 'No docker stats rows available.'}</div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Local stack inventory</h2>
        <div className="field-help" style={{ marginBottom: 12 }}>
          Captures what is actually wired in `docker-compose.yml` and `docker-compose.override.yml`
          on this machine, including the non-default dev ports.
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          {LOCAL_STACK.map((item) => (
            <div key={item.name} className="surface-muted">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <strong>{item.name}</strong>
                <code>{item.port}</code>
              </div>
              <div className="field-help" style={{ marginTop: 8 }}>{item.role}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Circuit breaker implementations</h2>
        <div className="field-help" style={{ marginBottom: 12 }}>
          This is the implementation inventory, not just the live state. Use it when the question is
          “what breakers do we actually have in code?” rather than “which one is open right now?”
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          {CIRCUIT_BREAKER_IMPLEMENTATIONS.map((item) => (
            <div key={item.name} className="surface-muted">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <strong>{item.name}</strong>
                <code>{item.codePath}</code>
              </div>
              <div className="field-help" style={{ marginTop: 8 }}>{item.protects}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Service health</h2>
        {health ? (
          <>
            <div className="field-help" style={{ marginBottom: 12 }}>
              Observed {fmtWhen(health.observed_at)} · uptime {fmtUptime(health.uptime_s)}
            </div>
            <div
              style={{
                display: 'grid',
                gap: 12,
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              }}
            >
              {readiness.map(([name, state]) => {
                const ok = state === 'ready';
                return (
                  <div key={name} className="surface-muted">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <strong>{name}</strong>
                      <span style={statusTone(ok)}>{state}</span>
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: 16 }}>
              <h3 style={{ marginBottom: 8 }}>Circuit breakers</h3>
              <div style={{ display: 'grid', gap: 10 }}>
                {health.breakers.map((breaker) => {
                  const ok = breaker.state === 'closed';
                  return (
                    <div key={breaker.name} className="surface-muted">
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                        <strong>{breaker.name}</strong>
                        <span style={statusTone(ok)}>{breaker.state}</span>
                      </div>
                      <div className="field-help" style={{ marginTop: 8 }}>
                        failures={breaker.failures ?? 'n/a'} · recovery_timeout_s={breaker.recovery_timeout_s ?? 'n/a'}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        ) : (
          <div className="field-help">{loading ? 'Loading health status…' : 'No health payload loaded.'}</div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Upstream reachability</h2>
        {upstreams ? (
          <div style={{ display: 'grid', gap: 10 }}>
            {upstreams.upstreams.map((row) => (
              <div key={row.name} className="surface-muted">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                  <div>
                    <strong>{row.name}</strong>{' '}
                    <span className="field-help">({row.kind})</span>
                  </div>
                  <span style={statusTone(row.reachable)}>
                    {row.reachable ? 'reachable' : 'down'}
                  </span>
                </div>
                <div className="field-help" style={{ marginTop: 8 }}>
                  <code>{row.url}</code>
                </div>
                <div className="field-help" style={{ marginTop: 4 }}>
                  status={row.status ?? 'n/a'} · latency_ms={row.latency_ms ?? 'n/a'} · version={row.version ?? 'n/a'}
                </div>
                {row.error && <div className="error" style={{ marginTop: 8 }}>{row.error}</div>}
              </div>
            ))}
          </div>
        ) : (
          <div className="field-help">{loading ? 'Loading upstream probes…' : 'No upstream data loaded.'}</div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Tool traffic</h2>
        {tools ? (
          <>
            <div className="field-help" style={{ marginBottom: 12 }}>
              Observed {fmtWhen(tools.observed_at)} · unreachable namespaces: {tools.unreachable.join(', ') || 'none'}
            </div>
            <div style={{ display: 'grid', gap: 10 }}>
              {tools.tools.slice(0, 12).map((tool) => (
                <div key={`${tool.namespace}:${tool.tool}`} className="surface-muted">
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                    <strong>{tool.namespace}.{tool.tool}</strong>
                    <span className="field-help">
                      calls={Object.values(tool.calls).reduce((sum, value) => sum + value, 0)}
                    </span>
                  </div>
                  <div className="field-help" style={{ marginTop: 8 }}>
                    avg_latency_s={tool.latency.avg_seconds?.toFixed(3) ?? 'n/a'} ·
                    errors={tool.calls.error ?? 0} · denials={Object.values(tool.denials).reduce((sum, value) => sum + value, 0)}
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="field-help">{loading ? 'Loading tool metrics…' : 'No tool metrics loaded.'}</div>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginBottom: 12 }}>Automations, files, and operator commands</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            marginBottom: 16,
          }}
        >
          {AUTOMATIONS.map((item) => (
            <div key={item.name} className="surface-muted">
              <strong>{item.name}</strong>
              <div style={{ marginTop: 10 }}>
                <code>{item.command}</code>
              </div>
              <div className="field-help" style={{ marginTop: 8 }}>{item.note}</div>
            </div>
          ))}
        </div>
        <div className="surface-muted" style={{ marginBottom: 16 }}>
          <strong>Persistent and audit-relevant paths</strong>
          <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
            {DATA_PATHS.map((item) => (
              <code key={item}>{item}</code>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginBottom: 12 }}>Build + operator surfaces</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          }}
        >
          <div className="surface-muted">
            <strong>Frontend build</strong>
            <div className="field-help" style={{ marginTop: 8 }}>
              build_id={buildInfo?.build_id ?? 'n/a'}
            </div>
            <div className="field-help">git_sha={buildInfo?.git_sha ?? 'n/a'}</div>
            <div className="field-help">generated_at={buildInfo ? fmtWhen(buildInfo.generated_at) : 'n/a'}</div>
          </div>
          <Link className="surface-muted" href="/admin/client-errors" style={{ textDecoration: 'none', color: 'inherit' }}>
            <strong>Client errors</strong>
            <div className="field-help" style={{ marginTop: 8 }}>
              Browser error intake and deep-link into forensics.
            </div>
          </Link>
          <Link className="surface-muted" href="/admin/forensics" style={{ textDecoration: 'none', color: 'inherit' }}>
            <strong>Forensics</strong>
            <div className="field-help" style={{ marginTop: 8 }}>
              Trace → draft → audit → HITL reconstruction.
            </div>
          </Link>
        </div>
      </div>
    </>
  );
}
