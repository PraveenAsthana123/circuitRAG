# AIOps And OpenTelemetry Scenarios

This document captures scenario lists for:

- AIOps
- OpenTelemetry

These are closely related because AIOps depends on telemetry quality.
If traces, metrics, and logs are weak, AIOps becomes guesswork.

## 1. AIOps Scenarios

- anomaly detection on latency spike
- anomaly detection on token-cost spike
- anomaly detection on breaker-open frequency
- anomaly detection on replay backlog growth
- anomaly detection on tool failure rate
- noisy-tenant behavior detection
- regression detection after deploy
- drift detection in answer quality
- alert correlation across services
- root-cause suggestion from logs, traces, and metrics
- incident clustering by failure signature
- auto-ticket creation from repeated incidents
- forecast queue saturation
- forecast token-budget exhaustion
- SLO burn-rate detection
- auto-remediation suggestion
- auto-remediation execution with approval gate
- false-positive alert suppression
- capacity planning from historical telemetry
- postmortem evidence assembly

## 2. Why AIOps Matters

AIOps is useful when the system generates enough telemetry that humans alone are no longer the fastest way to:

- detect problems
- correlate signals
- identify patterns
- forecast resource pressure
- assemble operational evidence

The value is not in replacing operators.
The value is in reducing low-signal manual correlation work.

## 3. High-Value AIOps Use Cases

### Detection

- detect latency anomalies
- detect error-rate anomalies
- detect retrieval-quality regressions
- detect cost spikes after prompt or model changes

### Correlation

- connect breaker-open spikes with downstream outages
- connect retry storms with queue growth
- connect deploys with new failure classes

### Forecasting

- forecast queue backlog saturation
- forecast token budget exhaustion
- forecast storage or compute pressure from historical patterns

### Evidence assembly

- incident bundle generation
- trace + metric + log collation by correlation ID
- postmortem timeline assistance

## 4. OpenTelemetry Scenarios

- trace propagation gateway -> retrieval -> inference -> MCP
- missing `traceparent` breaks multi-service trace
- correlation ID and trace ID alignment
- span attributes include tenant and correlation safely
- high-cardinality tag misuse
- spans emitted for tool calls
- spans emitted for degraded draft fallback
- spans emitted for replay worker path
- error span on dependency timeout
- breaker-open state visible in spans
- prompt, retrieval, and model metadata added to spans
- token usage attached to inference spans
- export failure does not break user request
- observability circuit breaker opens on collector outage
- OTLP collector unavailable
- trace sampling too low to debug incidents
- trace sampling too high and cost explodes
- logs linked to traces
- metrics linked to traces
- Jaeger search by tenant, correlation, or tool
- admin debug endpoint shows OTel-related state
- per-service latency waterfall inspection
- missing span around key workflow step
- async worker trace continuity
- background task emits orphan spans

## 5. Why OpenTelemetry Matters

OpenTelemetry is useful because this repo has:

- multiple services
- async workers
- tool calls
- degraded fallback paths
- replay workflows
- breaker state changes

Those systems become much harder to debug if traces stop at service boundaries.

## 6. High-Value OpenTelemetry Use Cases

### End-to-end tracing

- gateway -> retrieval -> inference -> MCP
- gateway -> ingestion -> worker -> store
- operator replay -> MCP -> audit

### Failure inspection

- identify slowest span in request path
- see where timeout occurred
- confirm which dependency was degraded
- correlate breaker state with request outcomes

### AI-specific tracing

- retrieval metadata attached to spans
- prompt version attached to spans
- token usage attached to inference spans
- tool choice visible in traces

## 7. Combined AIOps Scenarios

- deploy causes retrieval latency spike -> anomaly detected -> trace points to embedder slowdown
- MCP outage -> breaker opens -> alerts correlate across inference, MCP, and draft backlog
- token spend jumps after prompt change -> AIOps flags cost anomaly
- replay backlog grows after namespace outage -> forecast saturation and suggest throttle
- repeated guardrail denials spike after policy rollout -> anomaly tied to deploy change

## 8. Combined OpenTelemetry Scenarios

- user request traced end-to-end through gateway, retrieval, inference, and MCP
- degraded action path includes draft-created span and audit span
- worker replay trace links back to original correlation context
- collector outage opens observability breaker but app stays healthy
- trace reveals one missing span where retrieval reranking should have been instrumented

## 9. Common Failure Patterns

### AIOps failure patterns

- anomaly detector fires on normal seasonal variance
- deploy metadata not attached so regression detection is weak
- too many low-quality alerts cause suppression of real incidents
- cost anomalies detected too late
- no clear approval boundary for remediation

### OpenTelemetry failure patterns

- missing propagation between services
- high-cardinality labels or attributes explode storage cost
- traces sampled away during incidents
- async tasks lose parent context
- exporter outage harms application path because telemetry is not isolated

## 10. Evaluation Questions

For AIOps, ask:

- did the system detect the real problem?
- did it reduce time-to-understanding?
- did it correlate the right signals?
- did it avoid noisy false positives?
- did it help operators act safely?

For OpenTelemetry, ask:

- is the end-to-end trace actually complete?
- can operators identify the slow span?
- are degraded and replay paths visible?
- are tenant and tool attributes included safely?
- does collector failure remain non-fatal to user traffic?

## 11. Best High-Value Scenario Set

Start with these:

1. gateway -> retrieval -> inference -> MCP trace continuity
2. MCP outage -> breaker open -> backlog anomaly detection
3. collector outage -> observability breaker -> app remains healthy
4. deploy regression -> latency anomaly -> trace-guided root cause
5. replay worker trace continuity
6. token cost spike after prompt or model change
7. missing span around one critical workflow step
8. alert correlation across service, breaker, and queue signals

## 12. Operator Prompt

When reviewing AIOps or OpenTelemetry behavior, ask:

- What signal first showed the problem?
- Could the trace identify the failing or slow layer quickly?
- Did telemetry help distinguish symptom from cause?
- Could the system correlate the outage across services?
- Did observability stay healthy enough to help during failure?
- What high-value span or metric is still missing?

---

## 13. How These Map To DocuMind Today

### Already covered

| Scenario | Where in repo |
| --- | --- |
| Trace propagation gateway → retrieval → inference → MCP | `libs/py/documind_core/middleware.py:CorrelationIdMiddleware`, `SpanAttributeMiddleware` |
| `correlation_id` aligned with `trace_id` | `documind.correlation_id` span attribute set on every server span |
| Tenant-safe span attributes | `documind.tenant_id` set on tenant-scoped requests; never on metric labels (cardinality discipline) |
| Spans for tool calls | `mcp/server_common.py:handle_tool_call` (`mcp.tool:<name>`) |
| Spans for degraded draft fallback | `mcp_draft_persisted` log + audit row + breaker-state span attribute |
| Spans for replay worker path | `draft_replayed_by_worker` log lines (no dedicated span yet — gap) |
| Breaker-open visible in spans / metrics | `documind_circuit_breaker_state` Gauge + `_transitions_total` Counter |
| Token usage attached to inference spans | partial — token counts in logs, not span attributes |
| Export failure does not break user request | `ObservabilityCircuitBreaker` in `libs/py/documind_core/breakers.py` |
| Logs linked to traces | structured logs include correlation_id; trace_id link via OTel log handler (configurable) |
| Per-service latency | `mount_metrics_endpoint` exposes histograms via `documind_*_request_duration_seconds` |
| Jaeger search by tenant / correlation / tool | `documind.tenant_id`, `documind.correlation_id`, `mcp.tool.name` span attributes (commit 7ab6410-era work) |

### Gaps the catalog surfaces — actionable

| Gap | Severity | Suggested step |
| --- | --- | --- |
| Anomaly detection on breaker-open frequency | medium | PromQL alert on `rate(documind_circuit_breaker_opens_total[5m])` per breaker name. |
| Anomaly detection on replay backlog growth | high | Closes once `documind_draft_pending_age_seconds{namespace}` gauge ships (catalog'd as deferred). |
| Token-cost-spike anomaly | medium | Token-counter middleware on inference-svc → Prometheus → alert on rate spike. |
| Drift detection in answer quality | medium-high | Eval pipeline doesn't exist yet (catalog gap from rag-data-layers §15). |
| Replay worker dedicated span | low | Wrap `_sweep` in a span so worker traces show up in Jaeger. |
| SLO burn-rate alerts | medium | Define SLI/SLO doc first; then PromQL multi-window burn-rate. |
| Auto-remediation with approval gate | low | Out of current scope; requires policy-engine wiring. |
| Trace sampling tuning | low | Currently constant rate; tail-based sampling is a future cost-savings move. |

### Drills that exist for the analogue

| Scenario class | Existing drill |
| --- | --- |
| Breaker-state visible in /metrics + /health | `drill_prometheus_breakers`, `drill_health_detailed` |
| Counter increments only on real transitions | `drill_breaker_transitions` |
| Tool-call outcome metric | `drill_mcp_tool_call_metrics` |
| Worker per-outcome metric | `drill_worker_metrics` |
| Multi-namespace breaker independence | `drill_multi_breaker_visibility` |
| Auto-rejected drafts surface as a metric label | `drill_worker_auto_reject` |
| Audit-write-failure metric | `drill_audit_fail_closed` |

### Highest-value combined-scenario picks (next loop)

1. **Backlog-age gauge** — catalog'd as deferred multiple times; the
   building block for the "replay backlog growth" anomaly scenario.
2. **Worker `_sweep` span** — single-line wrap with
   `tracer.start_as_current_span("draft_replay_sweep")` + tenant /
   namespace attributes. Closes the "replay worker trace continuity"
   gap.
3. **Token-counter metric** — `documind_inference_tokens_total
   {model, kind=prompt|completion}`. Closes the cost-spike anomaly +
   the rag-data-layers gap on token observability.
4. **Anomaly alert PromQL pack** — committed YAML (no Grafana
   needed) for the highest-leverage alerts: breaker-open rate,
   replay-conflict rate, audit-fail-closed rate.
