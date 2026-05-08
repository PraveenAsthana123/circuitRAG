#!/usr/bin/env python3
# RESOURCES: readonly
"""
Generator for the 15 Grafana dashboards Kiali deep-links to.

Why this is a generator, not 15 hand-written JSONs:
  - Kiali's `external_services.grafana.dashboards[].name` MUST match
    the Grafana dashboard `title` EXACTLY, character for character.
  - Maintaining 15 hand-written 200-line JSONs leaks drift: someone
    renames a panel, the title shifts, the deep-link 404s.
  - A generator + drill that compares Kiali's declared name list to
    the generator's title list locks the contract.

Output:
  infra/observability/grafana-dashboards/<uid>.json  (one per entry)

Each dashboard is minimal but real:
  - Title matches Kiali's external_services.grafana.dashboards[i].name
  - UID is the slug of the title (kebab-case, lowercased)
  - Tags: ["documind", "<category>"]
  - 2-4 panels per dashboard
  - Panel queries use REAL metrics where they're emitted today (per
    libs/py/documind_core, services/*-svc), and FORWARD-CONTRACT
    metrics declared in infra/kiali/kiali-cluster-config.yaml for
    components not yet emitting (clearly marked in the panel title
    suffix "(forward-contract)").

Drilled by mcp/tests/drill_grafana_dashboards.py.

Re-run via:
  python3 scripts/generate-grafana-dashboards.py

Per CLAUDE.md §43 (drill discipline), §47.6 (observability is
first-class), §57.7 (forward-contract metrics declared explicitly,
not silently absent).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "infra" / "observability" / "grafana-dashboards"

# Each dashboard: title MUST match the Kiali config entry exactly.
# Each panel: (title, expr) — Grafana wraps the rest. `forward` tag
# means the metric isn't emitted yet and the dashboard panel will
# render empty until the service starts emitting.
DASHBOARDS = [
    # 1 — Istio Service (real metrics emitted by Istio sidecars+ctrl plane)
    {
        "uid": "documind-istio-service",
        "title": "Documind / Istio Service",
        "tags": ["documind", "istio", "mesh"],
        "panels": [
            ("Requests per second by destination",
             'sum by (destination_service) (rate(istio_requests_total[5m]))', False),
            ("Request duration p95 (ms)",
             'histogram_quantile(0.95, sum by (le, destination_service) '
             '(rate(istio_request_duration_milliseconds_bucket[5m])))', False),
            ("HTTP error ratio (5xx)",
             'sum by (destination_service) (rate(istio_requests_total{response_code=~"5.."}[5m])) '
             '/ sum by (destination_service) (rate(istio_requests_total[5m]))', False),
            ("TCP connections opened",
             'sum by (destination_service) (rate(istio_tcp_connections_opened_total[5m]))', False),
        ],
    },
    # 2 — Istio Workload (mesh telemetry by source workload)
    {
        "uid": "documind-istio-workload",
        "title": "Documind / Istio Workload",
        "tags": ["documind", "istio", "mesh"],
        "panels": [
            ("Outbound requests by source workload",
             'sum by (source_workload) (rate(istio_requests_total{reporter="source"}[5m]))', False),
            ("Inbound requests by destination workload",
             'sum by (destination_workload) (rate(istio_requests_total{reporter="destination"}[5m]))', False),
            ("p99 request duration by workload (ms)",
             'histogram_quantile(0.99, sum by (le, destination_workload) '
             '(rate(istio_request_duration_milliseconds_bucket[5m])))', False),
        ],
    },
    # 3 — RAG Pipeline (forward-contract — circuitRAG services should emit these)
    {
        "uid": "documind-rag-pipeline",
        "title": "Documind / RAG Pipeline (LangChain + LangGraph)",
        "tags": ["documind", "rag", "langchain", "langgraph"],
        "panels": [
            ("RAG requests/s",
             'sum(rate(documind_rag_requests_total[5m]))', True),
            ("RAG latency p95 (ms)",
             'histogram_quantile(0.95, sum by (le) '
             '(rate(documind_rag_latency_ms_bucket[5m])))', True),
            ("Retrieval hit rate",
             'avg(documind_retrieval_hit_rate)', True),
            ("LangGraph node executions/s",
             'sum by (node) (rate(documind_langgraph_node_executions_total[5m]))', True),
        ],
    },
    # 4 — Vector DB Qdrant (some real metrics from /metrics endpoint)
    {
        "uid": "documind-vector-db",
        "title": "Documind / Vector DB (Qdrant)",
        "tags": ["documind", "vector-db", "qdrant"],
        "panels": [
            ("Vector queries/s",
             'sum(rate(documind_qdrant_queries_total[5m]))', True),
            ("Recall@k",
             'avg(documind_retrieval_recall_at_k)', True),
            ("Qdrant collection points",
             'qdrant_collection_points_count', False),
            ("Qdrant request duration p95 (ms)",
             'histogram_quantile(0.95, sum by (le) '
             '(rate(qdrant_request_duration_seconds_bucket[5m]))) * 1000', False),
        ],
    },
    # 5 — Cache Redis (real metrics from redis-exporter when present)
    {
        "uid": "documind-cache-db",
        "title": "Documind / Cache (Redis)",
        "tags": ["documind", "cache", "redis"],
        "panels": [
            ("Cache hits/s",
             'sum(rate(documind_cache_hits_total[5m]))', True),
            ("Cache hit ratio",
             'avg(documind_cache_hit_ratio)', True),
            ("Redis memory used (bytes)",
             'redis_memory_used_bytes', False),
            ("Redis ops/s",
             'sum(rate(redis_commands_processed_total[5m]))', False),
        ],
    },
    # 6 — Chunking Pipeline
    {
        "uid": "documind-chunking",
        "title": "Documind / Chunking Pipeline",
        "tags": ["documind", "chunking", "ingestion"],
        "panels": [
            ("Chunks produced/s",
             'sum(rate(documind_chunks_produced_total[5m]))', True),
            ("Chunk size p95 (tokens)",
             'histogram_quantile(0.95, sum by (le) '
             '(rate(documind_chunk_size_tokens_bucket[5m])))', True),
            ("Documents ingested/s",
             'sum(rate(documind_documents_ingested_total[5m]))', True),
        ],
    },
    # 7 — Output Evaluation (Ragas + Giskard + DeepEval)
    {
        "uid": "documind-output-eval",
        "title": "Documind / Output Evaluation (Ragas + Giskard + DeepEval)",
        "tags": ["documind", "evaluation", "ragas", "giskard", "deepeval"],
        "panels": [
            ("Ragas — Faithfulness",
             'avg(documind_eval_ragas_faithfulness)', True),
            ("Ragas — Answer Relevance",
             'avg(documind_eval_ragas_answer_relevance)', True),
            ("Giskard — Hallucination",
             'avg(documind_eval_giskard_hallucination)', True),
            ("DeepEval — Toxicity",
             'avg(documind_eval_deepeval_toxicity)', True),
        ],
    },
    # 8 — Circuit Breaker (REAL metrics — emitted by libs/py/documind_core)
    {
        "uid": "documind-circuit-breaker",
        "title": "Documind / Circuit Breaker",
        "tags": ["documind", "resilience", "circuit-breaker"],
        "panels": [
            ("Breaker state (0=closed,1=half-open,2=open)",
             'documind_circuit_breaker_state', False),
            ("Trips/min",
             'sum by (name) (rate(documind_circuit_breaker_failures_total[5m]) * 60)', False),
            ("Half-open success ratio",
             'avg(documind_breaker_half_open_success_ratio)', True),
            ("Cognitive breaker interrupts",
             'sum by (signal) (rate(documind_ccb_interrupts_total[5m]))', False),
        ],
    },
    # 9 — API Gateway + Load Balancer
    {
        "uid": "documind-api-gateway",
        "title": "Documind / API Gateway + Load Balancer",
        "tags": ["documind", "api-gateway", "load-balancer"],
        "panels": [
            ("Requests by status",
             'sum by (status) (rate(documind_gateway_requests_total[5m]))', True),
            ("Upstream latency p95 (ms)",
             'histogram_quantile(0.95, sum by (le) '
             '(rate(documind_gateway_upstream_latency_ms_bucket[5m])))', True),
            ("Active connections",
             'avg(documind_gateway_active_connections)', True),
            ("Istio gateway requests/s",
             'sum by (response_code) (rate(istio_requests_total{source_workload="istio-ingressgateway"}[5m]))', False),
        ],
    },
    # 10 — Hybrid Architect (Council Engine)
    {
        "uid": "documind-hybrid-architect",
        "title": "Documind / Hybrid Architect (Council Engine)",
        "tags": ["documind", "council", "hybrid-architect"],
        "panels": [
            ("Council rounds/s",
             'sum(rate(documind_council_rounds_total[5m]))', True),
            ("Apply rate (7d window)",
             'avg_over_time(documind_council_apply_rate[7d])', True),
            ("Author/reviewer/advisor failures",
             'sum by (role) (rate(documind_council_role_failures_total[5m]))', True),
        ],
    },
    # 11 — Paperclip MCP
    {
        "uid": "documind-paperclip-mcp",
        "title": "Documind / Paperclip (MCP)",
        "tags": ["documind", "mcp", "paperclip"],
        "panels": [
            ("MCP invocations/s by tool",
             'sum by (tool) (rate(documind_mcp_invocations_total[5m]))', True),
            ("Scope-deny events/s",
             'sum by (tool) (rate(documind_mcp_scope_denied_total[5m]))', True),
            ("MCP latency p95 (ms)",
             'histogram_quantile(0.95, sum by (le, tool) '
             '(rate(documind_mcp_latency_ms_bucket[5m])))', True),
        ],
    },
    # 12 — Polysai (multi-LLM router)
    {
        "uid": "documind-polysai",
        "title": "Documind / Polysai",
        "tags": ["documind", "polysai", "llm-routing"],
        "panels": [
            ("LLM requests/s by model",
             'sum by (model) (rate(documind_polysai_requests_total[5m]))', True),
            ("Token cost p95 (USD)",
             'histogram_quantile(0.95, sum by (le, model) '
             '(rate(documind_polysai_cost_usd_bucket[5m])))', True),
            ("Routing decision distribution",
             'sum by (decision) (rate(documind_polysai_routing_decisions_total[5m]))', True),
        ],
    },
    # 13 — OTel Collector (real metrics — collector self-reports)
    {
        "uid": "documind-otel-collector",
        "title": "Documind / OTel Collector",
        "tags": ["documind", "opentelemetry"],
        "panels": [
            ("Spans accepted/s",
             'sum(rate(otelcol_receiver_accepted_spans[5m]))', False),
            ("Spans refused/s",
             'sum(rate(otelcol_receiver_refused_spans[5m]))', False),
            ("Export send errors/s",
             'sum by (exporter) (rate(otelcol_exporter_send_failed_spans[5m]))', False),
            ("Metric points exported/s",
             'sum by (exporter) (rate(otelcol_exporter_sent_metric_points[5m]))', False),
        ],
    },
    # 14 — Logs (Elasticsearch / Kibana link)
    # Grafana doesn't natively render Elasticsearch logs without datasource
    # config; this dashboard surfaces the volume + a deep link to Kibana.
    {
        "uid": "documind-logs",
        "title": "Documind / Logs (Elasticsearch / Kibana link)",
        "tags": ["documind", "logs", "elasticsearch", "kibana"],
        "panels": [
            ("Elasticsearch index docs (count)",
             'elasticsearch_indices_docs', False),
            ("Elasticsearch index size (bytes)",
             'elasticsearch_indices_store_size_in_bytes', False),
            ("Filebeat harvested files (rate)",
             'sum(rate(filebeat_harvester_running[5m]))', False),
        ],
        "links": [
            {"title": "Open Kibana", "url": "http://localhost:5601",
             "type": "link", "targetBlank": True}
        ],
    },
    # 15 — Tempo Traces (when deployed) — placeholder dashboard
    {
        "uid": "documind-tempo",
        "title": "Documind / Tempo Traces (when deployed)",
        "tags": ["documind", "tempo", "tracing"],
        "panels": [
            ("Spans ingested/s (Tempo)",
             'sum(rate(tempo_distributor_spans_received_total[5m]))', True),
            ("Tempo ingester traces stored",
             'tempo_ingester_traces_created_total', True),
        ],
        "links": [
            {"title": "Open Jaeger (current trace UI)",
             "url": "http://localhost:16686", "type": "link", "targetBlank": True}
        ],
    },
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def panel_block(title: str, expr: str, forward: bool, x: int, y: int) -> dict:
    full_title = title + (" (forward-contract)" if forward else "")
    return {
        "type": "timeseries",
        "title": full_title,
        "gridPos": {"x": x, "y": y, "w": 12, "h": 7},
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "targets": [{"expr": expr, "refId": "A", "legendFormat": "{{__name__}}"}],
        "options": {"legend": {"displayMode": "table", "placement": "bottom"}},
    }


def build_dashboard(dash: dict) -> dict:
    panels = []
    for i, (title, expr, forward) in enumerate(dash["panels"]):
        x = (i % 2) * 12
        y = (i // 2) * 7
        panels.append(panel_block(title, expr, forward, x, y))
    out = {
        "title": dash["title"],
        "uid": dash["uid"],
        "schemaVersion": 39,
        "version": 1,
        "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"},
        "tags": dash["tags"],
        "_generator": "scripts/generate-grafana-dashboards.py",
        "_kiali_deep_link": dash["title"],
        "panels": panels,
    }
    if "links" in dash:
        out["links"] = dash["links"]
    return out


def main() -> int:
    if not OUT_DIR.exists():
        print(f"ERROR: dashboard dir does not exist: {OUT_DIR}", file=sys.stderr)
        return 1

    written = 0
    for dash in DASHBOARDS:
        path = OUT_DIR / f"{dash['uid']}.json"
        path.write_text(json.dumps(build_dashboard(dash), indent=2) + "\n", encoding="utf-8")
        written += 1
        print(f"  wrote {path.relative_to(REPO)}  title={dash['title']!r}")
    print(f"\nGenerated {written}/{len(DASHBOARDS)} dashboards into {OUT_DIR.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
