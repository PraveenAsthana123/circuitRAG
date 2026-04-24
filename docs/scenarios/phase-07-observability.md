# Phase 7 — Observability, Audit, SLO, Chaos

**Status:** Stub — structure + concrete exit criteria.

## What "observability done" means

| Signal | Tool | Exit criterion |
| --- | --- | --- |
| **Logs** | ELK (Filebeat → Logstash → ES → Kibana) | every log line is JSON with `correlation_id`, `tenant_id`; Kibana KQL lookup by correlation-id returns every hop |
| **Traces** | OTel Collector → Jaeger | one user request shows 4+ spans in Jaeger (gateway → retrieval → inference → MCP); W3C `traceparent` propagated |
| **Metrics** | Prometheus → Grafana | dashboards per SLO; burn-rate alerts; CB state gauges per breaker |
| **Mesh telemetry** | Istio Telemetry v2 → Prometheus | `istio_requests_total` non-empty; Kiali renders mesh |

## SLO definitions (already seeded in `observability.slo_targets`)

| SLO | Target | Window |
| --- | --- | --- |
| Availability | 99.5% | 30d |
| Query latency p95 | < 3000ms | 30d |
| Retrieval precision@5 | > 80% | 7d |
| Answer faithfulness | > 90% | 7d |

## Observability Circuit Breaker (non-negotiable design rule)

Every OTel exporter wrapped in inverted-polarity breaker: **dead telemetry NEVER blocks user requests**. Collector outage → skip export silently + local alert. Classic pattern most teams skip, causing "telemetry took down the app" incidents.

Code: `libs/py/documind_core/breakers.py::ObservabilityCircuitBreaker`.

## Chaos drill library

| Drill | How | Expected |
| --- | --- | --- |
| Kill Qdrant | `docker compose kill qdrant` | Retrieval CB opens; fallback to BM25; p95 spike; no 5xx |
| Slow Ollama | `docker compose pause ollama` for 30s | Inference CB opens; smaller model fallback; degraded=true in response |
| Break Kafka | `docker compose kill kafka` | Ingestion sagas accumulate in outbox; relay resumes on recovery; zero event loss |
| Kill OTel collector | `docker compose kill otel-collector` | Observability CB opens; no user-facing impact; logs show "export skipped" |
| Kill Redis | `docker compose kill redis` | Cache miss path executes; p95 spike; no 5xx |
| Saturate PG | `pgbench -c 100 -T 60` | Gateway rate-limits; no connection exhaustion |

## Phase-7 exit criteria

- [ ] `make chaos` target runs all 6 drills and asserts expected behaviours.
- [ ] Dashboards committed to `infra/grafana/dashboards/`:
  - [ ] `api-gateway.json` (latency / error rate / RPS / 429s per tenant)
  - [ ] `circuit-breakers.json` (state per breaker + failures + opens + rejections)
  - [ ] `slo-burn.json` (multi-window burn-rate for every SLO)
  - [ ] `cost-per-tenant.json` (tokens + $ per tenant per day)
- [ ] One end-to-end Jaeger trace screenshot committed to `docs/observability/trace-example.png`.
- [ ] Runbook linked from every alert: `runbook_url` annotation in `infra/prometheus/alerts.yaml`.
