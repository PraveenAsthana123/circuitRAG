/**
 * BFF route — third-party integrations health.
 *
 * Probes every external observability / storage / mesh tool in the
 * circuitRAG stack and returns one JSON payload the operator UI
 * consumes. Single pane of glass per CLAUDE.md §47 (observability is
 * a first-class architectural surface).
 *
 * Status taxonomy (locked by drill_integrations_monitoring_page.py):
 *   HEALTHY        — HTTP probe returned 2xx
 *   DEGRADED       — HTTP probe returned 3xx/4xx (responding but not OK)
 *   UNREACHABLE    — HTTP probe failed (connection refused / timeout)
 *   NOT_CONFIGURED — env var unset and probe URL has no default
 *   TCP_ONLY       — protocol is TCP-only (Postgres / Redis / Kafka),
 *                    HTTP health probe is N/A here; rely on
 *                    /admin/mcp-fleet-health or the docker healthcheck
 *
 * Composes with (per §49):
 *   - /admin/monitoring (renders this)
 *   - /api/v1/mcp-fleet-health (covers circuitRAG OWN components)
 *   - /admin/health-pulse (covers audit-log layer pulses)
 *   - drill_integrations_monitoring_page.py (locks contract)
 *
 * Non-goals:
 *   - Probing TCP-only services here. That's mcp-fleet-health's job.
 *   - Auth pass-through to embedded UIs. We surface external links;
 *     SSO is a separate iteration.
 *
 * Per CLAUDE.md §44 (iter UI), §47, §50.5.3 (read-only), §51
 * (forensic substrate — generated_at carried), §57 (production-grade:
 * status taxonomy + parallel probe + timeout from day-1).
 */

import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PROBE_TIMEOUT_MS = 3_000;
const CACHE_TTL_MS = 30_000;

type Status =
  | "HEALTHY"
  | "DEGRADED"
  | "UNREACHABLE"
  | "NOT_CONFIGURED"
  | "TCP_ONLY";

type Category =
  | "observability"
  | "storage"
  | "telemetry"
  | "llm"
  | "mesh"
  | "circuitrag";

interface Probe {
  name: string;
  category: Category;
  ui_url: string; // operator's "Open" target
  health_url?: string; // empty = TCP_ONLY
  env_var?: string; // optional override of ui_url
  description: string;
}

interface ProbeResult {
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

// Canonical tool inventory. Adding a tool here: also add a matching
// entry in docs/runbooks/<tool>.md if it's the first time, and let
// the drill catch you if you skip it.
const PROBES: Probe[] = [
  // ── Observability ──────────────────────────────────────────────────
  {
    name: "Langfuse",
    category: "observability",
    ui_url: process.env.NEXT_PUBLIC_LANGFUSE_URL ?? "http://localhost:3002",
    health_url: "http://localhost:3002/api/public/health",
    env_var: "NEXT_PUBLIC_LANGFUSE_URL",
    description: "LLM trace + token + cost dashboard (per-prompt observability)",
  },
  {
    name: "Grafana",
    category: "observability",
    ui_url: process.env.NEXT_PUBLIC_GRAFANA_URL ?? "http://localhost:3001",
    health_url: "http://localhost:3001/api/health",
    env_var: "NEXT_PUBLIC_GRAFANA_URL",
    description: "Dashboards and time-series panels",
  },
  {
    name: "Prometheus",
    category: "observability",
    ui_url: process.env.NEXT_PUBLIC_PROMETHEUS_URL ?? "http://localhost:9090",
    health_url: "http://localhost:9090/-/healthy",
    env_var: "NEXT_PUBLIC_PROMETHEUS_URL",
    description: "Scrape targets, rules, raw metrics",
  },
  {
    name: "Jaeger",
    category: "observability",
    ui_url: process.env.NEXT_PUBLIC_JAEGER_URL ?? "http://localhost:16686",
    health_url: "http://localhost:16686/",
    env_var: "NEXT_PUBLIC_JAEGER_URL",
    description: "Trace search and span waterfall",
  },
  {
    name: "Alertmanager",
    category: "observability",
    ui_url: process.env.NEXT_PUBLIC_ALERTMANAGER_URL ?? "http://localhost:9093",
    health_url: "http://localhost:9093/-/healthy",
    env_var: "NEXT_PUBLIC_ALERTMANAGER_URL",
    description: "Alert grouping, routing, receiver inspection",
  },
  {
    name: "Kibana",
    category: "observability",
    ui_url: process.env.NEXT_PUBLIC_KIBANA_URL ?? "http://localhost:5601",
    health_url: "http://localhost:5601/api/status",
    env_var: "NEXT_PUBLIC_KIBANA_URL",
    description: "Log search and visualization (Elastic stack)",
  },

  // ── Mesh ───────────────────────────────────────────────────────────
  {
    name: "Kiali",
    category: "mesh",
    ui_url: process.env.NEXT_PUBLIC_KIALI_URL ?? "http://localhost:20001",
    health_url: "http://localhost:20001/healthz",
    env_var: "NEXT_PUBLIC_KIALI_URL",
    description: "Service-mesh visualization (Istio companion)",
  },

  // ── Storage ────────────────────────────────────────────────────────
  {
    name: "Qdrant",
    category: "storage",
    ui_url: process.env.NEXT_PUBLIC_QDRANT_URL ?? "http://localhost:6333",
    health_url: "http://localhost:6333/",
    env_var: "NEXT_PUBLIC_QDRANT_URL",
    description: "Vector database (HTTP)",
  },
  {
    name: "Neo4j Browser",
    category: "storage",
    ui_url: process.env.NEXT_PUBLIC_NEO4J_URL ?? "http://localhost:7474",
    health_url: "http://localhost:7474/",
    env_var: "NEXT_PUBLIC_NEO4J_URL",
    description: "Knowledge-graph browser (Bolt on 7687)",
  },
  {
    name: "MinIO Console",
    category: "storage",
    // Per docker-compose.yml port mapping: container 9000/9001 → host
    // 59000/59001 (the leading 5 namespaces this dev stack so it can
    // coexist with other stacks on the same host). The BFF runs on the
    // HOST so it must use the host-side ports.
    ui_url: process.env.NEXT_PUBLIC_MINIO_URL ?? "http://localhost:59001",
    health_url: "http://localhost:59000/minio/health/live",
    env_var: "NEXT_PUBLIC_MINIO_URL",
    description: "S3-compatible object store + console (host ports 59000/59001)",
  },
  {
    name: "Elasticsearch",
    category: "storage",
    ui_url: process.env.NEXT_PUBLIC_ELASTICSEARCH_URL ?? "http://localhost:9200",
    health_url: "http://localhost:9200/_cluster/health",
    env_var: "NEXT_PUBLIC_ELASTICSEARCH_URL",
    description: "Log indexing (Elastic stack)",
  },
  {
    name: "Postgres",
    category: "storage",
    ui_url: "tcp://localhost:5432",
    health_url: undefined, // TCP-only — see /admin/mcp-fleet-health for backend status
    description: "Relational store (TCP only — no HTTP probe)",
  },
  {
    name: "Redis",
    category: "storage",
    ui_url: "tcp://localhost:6379",
    health_url: undefined,
    description: "Cache + session store (TCP only)",
  },
  {
    name: "Kafka",
    category: "storage",
    ui_url: "tcp://localhost:9092",
    health_url: undefined,
    description: "Event backbone (TCP only)",
  },

  // ── LLM ────────────────────────────────────────────────────────────
  {
    name: "Ollama",
    category: "llm",
    ui_url: process.env.NEXT_PUBLIC_OLLAMA_URL ?? "http://localhost:11434",
    health_url: "http://localhost:11434/api/tags",
    env_var: "NEXT_PUBLIC_OLLAMA_URL",
    description: "Local LLM + embeddings runtime",
  },

  // ── Telemetry ──────────────────────────────────────────────────────
  {
    name: "OTel collector",
    category: "telemetry",
    // The collector listens on:
    //   :4317 (OTLP gRPC)  :4318 (OTLP HTTP)  :9464 (Prometheus exporter)
    //   :13133 (health_check extension — but NOT exposed to host in
    //   this docker-compose setup; only :4317/4318/9464 are mapped).
    // Probing 9464/ is the right test: it's the exporter port, reachable
    // from the host, returns 200 when the collector is alive.
    ui_url: process.env.NEXT_PUBLIC_OTEL_URL ?? "http://localhost:9464",
    health_url: "http://localhost:9464/",
    env_var: "NEXT_PUBLIC_OTEL_URL",
    description: "OTLP ingest + Prometheus re-export (probed on :9464)",
  },
  {
    name: "cAdvisor",
    category: "telemetry",
    ui_url: process.env.NEXT_PUBLIC_CADVISOR_URL ?? "http://localhost:8089",
    health_url: "http://localhost:8089/healthz",
    env_var: "NEXT_PUBLIC_CADVISOR_URL",
    description: "Container CPU/memory/filesystem metrics",
  },
  {
    name: "Node exporter",
    category: "telemetry",
    ui_url: process.env.NEXT_PUBLIC_NODE_EXPORTER_URL ?? "http://localhost:9100",
    health_url: "http://localhost:9100/",
    env_var: "NEXT_PUBLIC_NODE_EXPORTER_URL",
    description: "Host CPU/memory/filesystem/kernel metrics",
  },

  // ── circuitRAG own gateways (still external from the frontend's PoV) ─
  {
    name: "OpenClaw gateway",
    category: "circuitrag",
    ui_url: process.env.NEXT_PUBLIC_OPENCLAW_URL ?? "http://127.0.0.1:18789",
    health_url: "http://127.0.0.1:18789/",
    env_var: "NEXT_PUBLIC_OPENCLAW_URL",
    description: "OpenClaw coordinator gateway",
  },
];

interface CacheEntry {
  at: number;
  payload: { generated_at: string; tools: ProbeResult[] };
}

let _cache: CacheEntry | null = null;

async function probeOne(p: Probe): Promise<ProbeResult> {
  const base: ProbeResult = {
    name: p.name,
    category: p.category,
    ui_url: p.ui_url,
    description: p.description,
    status: "NOT_CONFIGURED",
    latency_ms: null,
  };
  if (!p.health_url) {
    return { ...base, status: "TCP_ONLY" };
  }

  const started = Date.now();
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), PROBE_TIMEOUT_MS);
  try {
    const r = await fetch(p.health_url, {
      method: "GET",
      signal: ctl.signal,
      cache: "no-store",
    });
    const elapsed = Date.now() - started;
    let status: Status;
    if (r.status >= 200 && r.status < 300) status = "HEALTHY";
    else if (r.status >= 300 && r.status < 500) status = "DEGRADED";
    else status = "UNREACHABLE";
    return {
      ...base,
      status,
      latency_ms: elapsed,
      http_status: r.status,
    };
  } catch (e: unknown) {
    const elapsed = Date.now() - started;
    const err = e as { name?: string; message?: string };
    return {
      ...base,
      status: "UNREACHABLE",
      latency_ms: elapsed,
      error: err.name === "AbortError" ? "timeout" : (err.message ?? "fetch_failed"),
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function GET() {
  const now = Date.now();
  if (_cache && now - _cache.at < CACHE_TTL_MS) {
    return NextResponse.json(_cache.payload, {
      headers: { "Cache-Control": "no-store", "X-Cache": "HIT" },
    });
  }

  // Parallel probe — never block on the slowest single tool.
  const results = await Promise.all(PROBES.map(probeOne));
  const payload = {
    generated_at: new Date().toISOString(),
    tools: results,
  };
  _cache = { at: now, payload };
  return NextResponse.json(payload, {
    headers: { "Cache-Control": "no-store", "X-Cache": "MISS" },
  });
}
