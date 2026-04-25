# OpenTelemetry Gap Review By Service And Tool

This note reviews OTel gaps by service and by tool or workflow layer.

It is meant to answer:

- where OTel is strongest
- where it is weak
- what the next highest-value instrumentation work is

## 1. Strongest Areas

### Shared Python observability foundation

Strong because:

- one shared setup path exists
- FastAPI instrumentation is centralized
- asyncpg, redis, and httpx instrumentation helpers exist
- observability exporter path is breaker-protected

Relevant code:

- [libs/py/documind_core/observability.py](/mnt/deepa/rag/libs/py/documind_core/observability.py)

### Python service startup wiring

Strong because:

- `ingestion-svc`
- `retrieval-svc`
- `inference-svc`
- `evaluation-svc`

all visibly wire OTel in startup paths.

### MCP server scaffold

Strong because:

- one shared server OTel setup exists
- all current MCP servers use it

## 2. Service Gaps

## 2.1 API gateway

### Current state

- OTel dependencies exist in `go.mod`
- visible `main.go` does not show actual OTel initialization or middleware instrumentation

### Gap

- no clearly visible request tracing
- no clearly visible outgoing trace propagation
- no clearly visible auth or route-failure span coverage

### Priority

- P0

## 2.2 Identity service

### Current state

- no visible OTel wiring found in inspected code

### Gap

- no clear startup tracing
- no clear request span coverage

### Priority

- P1

## 2.3 Governance service

### Current state

- no visible OTel wiring found in inspected code

### Gap

- policy decisions
- audit-adjacent flows
- approval paths

are not clearly instrumented

### Priority

- P1

## 2.4 FinOps service

### Current state

- no visible OTel wiring found in inspected code

### Gap

- usage aggregation and cost-flow visibility are not clearly traced

### Priority

- P2

## 2.5 Observability service

### Current state

- no visible OTel wiring found in inspected code

### Gap

- ironic but important: admin health and capacity APIs are not clearly traced

### Priority

- P2

## 2.6 Frontend

### Current state

- OTel package references exist in frontend deps
- active browser tracing is not clearly visible in inspected code

### Gap

- no clear browser-side tracing path
- no clear frontend-to-backend trace continuity proof

### Priority

- P3 unless browser tracing is a product requirement

## 3. Tool And Workflow Gaps

## 3.1 Agent tool-decision path

### Gap

The repo has service-level tracing, but the actual agent decision points are still thin.

Useful missing spans likely include:

- tool intent detected
- scope pre-check result
- action denied
- action degraded

### Priority

- P1

## 3.2 MCP tool-dispatch path

### Gap

MCP servers are instrumented at the server level, but tool-level detail should be richer.

Useful missing attributes or spans likely include:

- tool name
- scope outcome
- idempotent replay hit
- degraded outcome
- dispatch duration by tool

### Priority

- P1

## 3.3 Replay path

### Gap

Replay has some explicit tracer use, but continuity still appears incomplete.

Useful missing spans likely include:

- replay started
- replay CAS outcome
- replay marked as replayed
- replay conflict
- replay audit outcome

### Priority

- P1

## 3.4 Retrieval decision path

### Gap

Retrieval service is instrumented, but deeper visibility into decisions is still likely thin.

Useful missing spans likely include:

- vector search duration
- graph search duration
- rerank duration
- cache hit vs miss decision

### Priority

- P1

## 3.5 Evaluation and replay-eval path

### Gap

Evaluation service has base service-level OTel but not clearly deep workflow coverage.

Useful missing spans likely include:

- eval run start
- metric-by-metric scoring phase
- regression gate decision
- replay-eval request lifecycle

### Priority

- P2

## 4. Failure-Path Gaps

The most important gap class is not happy-path coverage.
It is failure-path coverage.

These paths need explicit review:

- scope denial
- breaker open
- degraded draft creation
- replay conflict
- audit failure
- timeout and cancellation

If those are not clearly visible in traces, operations will be weaker exactly where the system is most complex.

## 5. Recommended Priority Order

1. API gateway OTel wiring
2. agent and MCP tool-level spans
3. replay-path spans
4. retrieval decision spans
5. Go service coverage for identity and governance
6. evaluation and FinOps deeper spans
7. browser tracing if desired

## 6. Bottom Line

The repo is strongest in:

- shared Python observability setup
- Python service startup wiring
- MCP server scaffold

The biggest missing step is:

- turning service-level observability into workflow- and tool-level observability

while also closing the Go-service and gateway gap.
