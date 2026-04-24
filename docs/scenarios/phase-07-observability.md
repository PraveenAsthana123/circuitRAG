# Phase 7 — Observability, Audit, SLO, Chaos

**Status:** Specified. OTel SDK wired in code; dashboards + end-to-end traces NOT verified live.

---

## 1. Observability pillars

| Signal | Tool | Exit criterion |
| --- | --- | --- |
| **Logs** | ELK (Filebeat → Logstash → ES → Kibana) | Every log line is JSON with `correlation_id`, `tenant_id`; Kibana KQL lookup returns every hop |
| **Traces** | OTel Collector → Jaeger | One user request shows 4+ spans (gateway → retrieval → inference → MCP); W3C `traceparent` propagated |
| **Metrics** | Prometheus → Grafana | Dashboards per SLO; burn-rate alerts; CB state gauges per breaker |
| **Mesh telemetry** | Istio Telemetry v2 → Prometheus | `istio_requests_total` non-empty; Kiali renders mesh |

## 2. Trace scenario catalog

| Scenario | What to observe | Why |
| --- | --- | --- |
| User query trace | gateway → retrieval → inference → response | Debug slow / bad answers |
| Retrieval trace | query → Qdrant → reranker | Find retrieval failure |
| LLM trace | prompt size, latency, model, tokens | Cost + quality |
| MCP trace | tool call → tool result → action status | Action auditability |
| Kafka trace | event produced → consumed → lag | Async pipeline health |
| Circuit breaker trace | CLOSED → OPEN → HALF_OPEN | Resilience proof |
| Cache trace | hit / miss / TTL / version | Cost + latency |
| Tenant trace | tenant-specific usage + errors | Noisy-neighbor control |

## 3. Metrics catalog

| Metric | Component | Labels |
| --- | --- | --- |
| `documind_request_total` | api-gateway | `service, route, tenant_tier, code` |
| `documind_request_duration_seconds` | every service | `service, route` (histogram) |
| `documind_retrieval_result_count` | retrieval-svc | `tenant_tier` |
| `documind_vector_db_latency_seconds` | retrieval-svc | `collection` |
| `documind_llm_latency_seconds` | inference-svc | `model` |
| `documind_llm_tokens_total` | inference-svc | `model, tenant_tier, kind` (prompt/completion) |
| `documind_cache_hit_total` | cache wrapper | `layer` |
| `documind_circuit_breaker_state` | every CB | `name` (0=CLOSED, 1=HALF_OPEN, 2=OPEN) |
| `documind_circuit_breaker_failures_total` | every CB | `name` |
| `documind_circuit_breaker_opens_total` | every CB | `name` |
| `documind_fallback_used_total` | resilience wrapper | `name, fallback_type` |
| `documind_mcp_tool_latency_seconds` | mcp-action-workers | `tool` |
| `documind_kafka_consumer_lag` | every consumer group | `group, topic, partition` |
| `documind_eval_faithfulness_score` | eval-svc | `tenant_tier, model_version` |

**Hard rule:** no high-cardinality labels (never `tenant_id` as a Prometheus label — use tenant_tier instead; tenant_id goes in trace attributes + logs).

## 4. SLO catalog

Seeded in `observability.slo_targets`:

| SLO | Target | Window |
| --- | --- | --- |
| Availability | 99.5% | 30d |
| Chat query latency p95 | < 3000ms | 30d |
| Retrieval latency p95 | < 500ms | 30d |
| Inference latency p95 | < 5000ms | 30d |
| Upload-accepted p95 | < 1000ms | 30d |
| Indexing completion | 95% < 5 min | 30d |
| MCP read tool p95 | < 2000ms | 30d |
| MCP write tool p95 | < 10000ms | 30d |
| Error rate | < 1% | 30d |
| Cache hit rate (FAQ) | > 30% | 30d |
| Retrieval precision@5 | > 80% | 7d |
| Answer faithfulness | > 90% | 7d |

Burn-rate alerts: 1h / 6h / 72h multi-window.

## 5. Audit event schema

Every audited action writes to `governance.audit_log`:

| Field | Purpose |
| --- | --- |
| `event_id` | Idempotency |
| `tenant_id` | Who this is about |
| `actor_user_id` | Who did it |
| `action` | What was done (enum) |
| `resource_type, resource_id` | What it was done to |
| `prev_state, next_state` | Diff |
| `policy_version` | Which rule applied |
| `correlation_id` | Thread back to request |
| `timestamp` | UTC |
| `hash_chain_link` | Tamper evidence |

Audit scenarios to cover:
- User asked question → query hash, citations, answer, model, prompt version
- MCP action requested / executed → tool, payload hash, idempotency key, result
- Policy blocked answer → rule ID, reason
- Human approved action → approver, decision, timestamp
- Admin changed config → old value, new value, actor

## 6. Observability Circuit Breaker (non-negotiable)

Every OTel exporter wrapped in inverted-polarity breaker: **dead telemetry NEVER blocks user requests**. Collector outage → skip export silently + local alert.

Code: `libs/py/documind_core/breakers.py::ObservabilityCircuitBreaker`.

## 7. Chaos drill matrix

| # | Drill | Command | Expected |
| --- | --- | --- | --- |
| 1 | Kill Qdrant | `docker compose kill qdrant` | Retrieval CB opens; BM25 fallback; p95 spike; no 5xx |
| 2 | Slow Ollama (30s) | `docker compose pause ollama` | Inference CB opens; smaller-model fallback; `degraded=true` in response |
| 3 | Break Kafka | `docker compose kill kafka` | Ingestion sagas accumulate in outbox; relay catches up; zero event loss |
| 4 | Kill OTel collector | `docker compose kill otel-collector` | Observability CB opens; no user impact; logs show "export skipped" |
| 5 | Kill Redis | `docker compose kill redis` | Cache miss path; p95 spike; no 5xx |
| 6 | Saturate PG | `pgbench -c 100 -T 60` | Gateway rate-limits; no connection exhaustion |
| 7 | Kill MCP server | `docker compose kill mcp-server-itsm` | MCP CB opens; draft persisted to `governance.hitl_queue` |
| 8 | Inject 503 in inference | Istio fault `abort: { httpStatus: 500, percentage: 100 }` | Istio ejects pod via outlier detection; traffic continues to healthy replicas |
| 9 | High traffic spike | `hey -n 10000 -c 200 /api/v1/ask` | Rate-limit + autoscale; no CB trip on healthy deps |

## 8. Exit criteria

- [ ] `make chaos` runs the 9 drills and asserts expected behaviours.
- [ ] Dashboards committed to `infra/grafana/dashboards/`:
  - [ ] `api-gateway.json` — latency / error rate / RPS / 429s per tenant_tier
  - [ ] `circuit-breakers.json` — state + failures + opens + rejections per breaker
  - [ ] `slo-burn.json` — multi-window burn-rate for every SLO
  - [ ] `cost-per-tenant.json` — tokens + $ per tenant per day
  - [ ] `kafka-lag.json` — consumer lag per group + DLQ depth
- [ ] One end-to-end Jaeger trace screenshot at `docs/observability/trace-example.png`.
- [ ] Every Prom alert has `runbook_url` annotation in `infra/prometheus/alerts.yaml`.
- [ ] `scripts/demo-chaos.sh` — runs the 9 drills in demo mode with narration.

## 9. Brutal checklist

| Question | Required |
| --- | --- |
| Can one request be traced end-to-end in Jaeger? | Yes — screenshot committed |
| Can you prove why an answer was generated? | Yes — decision record in audit log |
| Can you show every circuit breaker state? | Yes — Grafana panel |
| Can you replay failed events? | Yes — from Kafka DLQ |
| Can you detect tenant-specific failure? | Yes — tenant_tier label + trace attr |
| Can you prove audit integrity? | Hash-chain writer (planned); append-only today |
| Can you run every chaos test and show fallback? | 9 drills with expected results |
| Does a dead telemetry backend NOT take down the app? | Yes — Observability CB (inverted) |
