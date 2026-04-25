# Tool Troubleshooting Checklist

This note is a practical troubleshooting guide for the main tools and platform layers discussed in this repo.

It is organized by tool.
For each tool, use the same audit flow:

1. confirm the tool is reachable
2. confirm the tool is doing the job it is supposed to do
3. confirm telemetry exists
4. confirm failures are visible
5. confirm the failure is in the tool, not in an upstream or downstream dependency

## 1. Universal Troubleshooting Flow

Use this checklist first before diving into any specific tool.

- [ ] What is the exact symptom?
- [ ] Is this a correctness problem, performance problem, routing problem, or observability problem?
- [ ] Is the failure reproducible?
- [ ] What changed recently?
- [ ] Is the tool itself down, or is one dependency under it failing?
- [ ] Do logs, metrics, and traces agree on the failure?
- [ ] Is this isolated to one tenant, one namespace, one route, or the whole system?
- [ ] Is degraded mode or fallback working?

## 2. API Gateway

### Common symptoms

- requests do not reach downstream services
- auth failures spike
- wrong service receives traffic
- latency rises before backend latency rises
- CORS or header propagation breaks

### Troubleshooting checklist

- [ ] Check `/health` on the gateway
- [ ] Check route mapping in `services/api-gateway/internal/proxy`
- [ ] Check JWT verification and auth middleware behavior
- [ ] Confirm `X-Tenant-ID`, correlation, and role headers are present
- [ ] Check rate-limit behavior
- [ ] Check gateway logs for 4xx vs 5xx distribution
- [ ] Compare gateway latency with downstream service latency

### Likely causes

- route misconfiguration
- auth or tenant propagation bug
- rate-limit misconfiguration
- downstream dependency failure surfacing through gateway

## 3. MCP Client And MCP Servers

### Common symptoms

- tool calls fail
- correct tool is chosen but action never completes
- degraded drafts spike
- scope denials increase
- replay does not clear backlog

### Troubleshooting checklist

- [ ] Check MCP server `/health`
- [ ] Check `/tools/list` returns expected tools
- [ ] Confirm tool schema and required scopes
- [ ] Check `documind_mcp_tool_calls_total` outcomes by tool
- [ ] Check breaker state for the MCP namespace
- [ ] Check draft creation count and pending backlog
- [ ] Check replay success rate and oldest pending age
- [ ] Confirm audit rows exist for draft create/replay/reject
- [ ] Confirm `Idempotency-Key` and correlation ID are present

### Likely causes

- MCP server unavailable
- wrong namespace routing
- scope mismatch
- breaker open
- downstream system under the MCP server is failing
- replay worker not draining

## 4. Circuit Breaker

### Common symptoms

- sudden fast-reject behavior
- repeated degraded responses
- breaker never closes after recovery
- retries appear to fight the breaker

### Troubleshooting checklist

- [ ] Check current breaker state: closed, open, half-open
- [ ] Check failure count and transition metrics
- [ ] Check whether the underlying dependency is actually healthy again
- [ ] Check if timeouts are too aggressive or too lenient
- [ ] Check whether retries are causing extra failures
- [ ] Confirm half-open probe behavior is exercised
- [ ] Check whether one namespace is affected or all namespaces

### Likely causes

- real downstream outage
- timeout mismatch
- retry storm
- threshold too low
- recovery timeout too long or too short

## 5. Retrieval Stack

This includes:

- retrieval-svc
- vector search
- graph search
- cache-assisted retrieval

### Common symptoms

- empty or weak results
- latency spikes
- cache hit rate collapses
- quality drops without obvious errors

### Troubleshooting checklist

- [ ] Check retrieval service `/health`
- [ ] Check retrieval latency and timeout rate
- [ ] Check Redis hit rate and cache behavior
- [ ] Check vector backend latency
- [ ] Check graph backend latency
- [ ] Compare cold-cache vs warm-cache behavior
- [ ] Check recent changes to chunking, embeddings, or reranking
- [ ] Validate tenant filters are applied correctly

### Likely causes

- Qdrant or Neo4j slowdown
- cache cold start or cache invalidation issue
- retrieval config drift
- chunking or embedding regression
- tenant filter bug

## 6. Inference / Model Backend

### Common symptoms

- answers become slow
- timeouts spike
- model output quality degrades
- streaming behaves differently from non-streaming

### Troubleshooting checklist

- [ ] Check inference service `/health`
- [ ] Check Ollama or model backend health
- [ ] Check model latency and timeout rate
- [ ] Check prompt size and token usage
- [ ] Check fallback or degraded behavior
- [ ] Compare baseline ask flow to current latency
- [ ] Check recent prompt or model changes

### Likely causes

- model backend saturation
- long-context prompts
- regression in prompt construction
- downstream retrieval slowdown appearing as inference slowdown

## 7. OpenTelemetry

### Common symptoms

- missing traces
- broken trace continuity across services
- spans exist in one service but not the next
- trace IDs do not align with logs

### Troubleshooting checklist

- [ ] Confirm OTel exporter is configured
- [ ] Confirm spans are emitted on the critical path
- [ ] Check gateway -> retrieval -> inference -> MCP trace continuity
- [ ] Check collector or exporter health
- [ ] Check missing spans on async or replay paths
- [ ] Confirm correlation ID and trace ID are both visible where expected

### Likely causes

- missing instrumentation
- collector outage
- sampling misconfiguration
- async boundary not instrumented

## 8. Prometheus

### Common symptoms

- dashboards show no data
- metrics stop updating
- one service has gaps while others are fine
- alerting becomes noisy or silent

### Troubleshooting checklist

- [ ] Check target scrape status
- [ ] Check `/metrics` endpoints manually
- [ ] Check metric names and label values
- [ ] Check whether cardinality exploded
- [ ] Check whether the service emits metrics at all
- [ ] Confirm breaker, MCP, replay, and latency metrics are present

### Likely causes

- scrape target misconfiguration
- service no longer exposing metrics
- label explosion
- wrong dashboard query

## 9. Grafana

### Common symptoms

- panels are empty
- graphs do not match reality
- dashboards hide the real issue
- operators cannot tell what action to take

### Troubleshooting checklist

- [ ] Confirm datasource health
- [ ] Confirm dashboard queries against Prometheus
- [ ] Check time range and variable filters
- [ ] Check whether dashboards include the critical metrics
- [ ] Check whether panel titles and labels are operationally meaningful
- [ ] Check whether per-tool and per-namespace views exist where needed

### Likely causes

- bad query
- wrong time range
- missing metric
- dashboard built for the wrong operational question

## 10. Langfuse Or Phoenix

### Common symptoms

- prompt and retrieval details are missing
- tool-choice reasoning is hard to inspect
- run-level AI traces are incomplete

### Troubleshooting checklist

- [ ] Confirm SDK or integration is wired
- [ ] Confirm runs are created for the main ask flow
- [ ] Confirm prompt, model, retrieval, and tool metadata are attached
- [ ] Confirm failed runs are still visible
- [ ] Check whether privacy and redaction rules are applied

### Likely causes

- incomplete integration
- only happy path instrumented
- metadata not attached
- privacy filter stripping too much or too little

## 11. k6

### Common symptoms

- test script runs but results are meaningless
- thresholds fail unexpectedly
- latency numbers do not match dashboards

### Troubleshooting checklist

- [ ] Confirm the scenario matches a real production path
- [ ] Confirm payloads are realistic
- [ ] Confirm thresholds are explicit
- [ ] Compare k6 output with Prometheus and Grafana
- [ ] Confirm the right environment and dataset were used
- [ ] Check whether rate limits or auth caused artificial failures

### Likely causes

- unrealistic scenario
- wrong endpoint or payload
- test hitting a dev environment with different config
- no telemetry correlation during the run

## 12. Locust

### Common symptoms

- workflow results are inconsistent
- stateful scenarios fail unpredictably
- replay or degraded flows do not match expectations

### Troubleshooting checklist

- [ ] Confirm user behavior model is realistic
- [ ] Confirm task order mirrors the real workflow
- [ ] Confirm seed data and tenant data are valid
- [ ] Check whether the scenario includes proper wait and retry behavior
- [ ] Confirm workflow-level telemetry exists during the run

### Likely causes

- invalid state transitions in test setup
- poor fixture isolation
- unrealistic concurrency model
- workflow ordering bug in the test itself

## 13. Playwright

### Common symptoms

- browser tests are flaky
- failures are visible to users but not to backend tests
- F12 errors exist even though API tests pass

### Troubleshooting checklist

- [ ] Check browser console output
- [ ] Check network tab for failed requests
- [ ] Confirm loading, error, and empty states are asserted
- [ ] Check desktop and mobile variants
- [ ] Capture screenshot and trace artifacts on failure

### Likely causes

- UI state not modeled in tests
- slow API handling bugs
- frontend route-level error issues
- hydration or runtime JS errors

## 14. Ragas

### Common symptoms

- quality scores drift suddenly
- retrieval quality drops without obvious system errors
- faithfulness looks worse after a prompt or retrieval change

### Troubleshooting checklist

- [ ] Confirm the evaluation dataset is still valid
- [ ] Confirm the same prompt and retrieval config are being compared
- [ ] Compare quality results with latency and retrieval changes
- [ ] Check if chunking or embeddings changed recently
- [ ] Separate quality regression from system-latency regression

### Likely causes

- prompt drift
- retrieval config drift
- embedding or reranker change
- stale or low-quality eval dataset

## 15. Promptfoo

### Common symptoms

- prompt change causes silent regressions
- different models produce inconsistent outputs
- structured output breaks unexpectedly

### Troubleshooting checklist

- [ ] Check which prompt version is under test
- [ ] Check which model version is under test
- [ ] Confirm assertions match business expectations
- [ ] Check whether failures are systematic or only edge cases
- [ ] Compare current run with known-good baseline

### Likely causes

- prompt drift
- model behavior change
- missing regression cases
- weak assertions

## 16. Tool Troubleshooting Matrix

| Tool | First thing to check | Most important metric | Most likely root cause category |
|---|---|---|---|
| API gateway | `/health` and routing | latency and 5xx rate | routing or auth propagation |
| MCP | `/health`, `/tools/list`, breaker | tool outcome counts | outage, scope, routing, replay |
| circuit breaker | state and transitions | open and rejection rate | downstream failure or threshold mismatch |
| retrieval | backend latency and cache | retrieval p95 and hit rate | backend pressure or config drift |
| inference | model backend health | answer latency and timeout rate | model saturation or prompt size |
| OTel | trace continuity | missing spans | instrumentation or exporter issue |
| Prometheus | scrape targets | metric freshness | scrape or metric exposure issue |
| Grafana | datasource and queries | panel correctness | dashboard/query problem |
| Langfuse/Phoenix | run visibility | run completeness | missing metadata or integration |
| k6 | scenario realism | threshold pass/fail | weak script or wrong environment |
| Locust | workflow correctness | failure distribution | bad fixture or state model |
| Playwright | console and network | user-visible failures | frontend state bug |
| Ragas | dataset and config | quality score deltas | retrieval or prompt drift |
| Promptfoo | prompt/model version | regression pass/fail | prompt drift or weak assertions |

## 17. Final Checklist For Any Incident

- [ ] Identify which tool or layer showed the first visible symptom
- [ ] Verify the symptom in metrics, logs, and traces
- [ ] Confirm whether the issue is local, per-tenant, per-tool, or global
- [ ] Check what changed recently
- [ ] Check whether degraded mode worked
- [ ] Check whether audit and correlation data were preserved
- [ ] Record the result as:
  - tool issue
  - dependency issue
  - contract issue
  - configuration issue
  - observability gap

## 18. Bottom Line

Good troubleshooting is not:

- “restart it and hope”

Good troubleshooting is:

- find the failing layer
- verify its telemetry
- confirm the real dependency chain
- determine whether fallback and recovery worked
- convert the failure into a repeatable checklist or regression test
