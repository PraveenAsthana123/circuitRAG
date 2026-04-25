# OpenTelemetry Tool-Level Coverage Scorecard And Tracker

This note answers a practical question:

- how close is this repo to full OpenTelemetry coverage at tool and component level?

It does **not** pretend the answer is already `100%`.
Instead it gives:

- current coverage
- scoring
- done criteria
- completed work
- current gaps
- future plan
- current tracking structure

## 1. What “100% Implemented” Should Mean

For this repo, tool-level OTel should mean:

- service startup initializes OTel correctly
- inbound request path is traced
- important outbound dependency calls are traced
- important tool or workflow decisions have useful spans
- async or replay paths preserve traceability where practical
- correlation ID and trace ID can be linked
- failed paths still emit usable telemetry

If one of those is missing, the tool is not truly “fully implemented” from an observability perspective.

## 2. Scoring Model

Use a `0` to `5` scale:

- `0` no visible OTel usage
- `1` dependency present but not clearly wired
- `2` startup or partial wiring exists
- `3` service-level OTel exists
- `4` service-level plus important workflow spans exist
- `5` strong tool-level and failure-path coverage with operator usefulness

## 3. Current Coverage Matrix

| Tool / component | Current score | Current state | Done criteria | Status |
|---|---:|---|---|---|
| `ingestion-svc` | 4 | `setup_observability` + FastAPI + asyncpg + redis + httpx instrumentation visible | add strong custom spans on parse/chunk/embed/index critical steps and verify failure-path traces | partial-strong |
| `retrieval-svc` | 4 | service-level OTel and outbound dependency instrumentation visible | add clearer custom spans for vector/graph/rerank/cache decision points | partial-strong |
| `inference-svc` | 5 | service-level OTel + worker tracer usage + per-guardrail-call span (`inference.guardrail.check`) with attributes for passed-state, confidence, violations.count, violations (csv), found_labels, top_retrieval_score. Drill `drill_guardrail_otel_attributes.py` proves attribute set + log-line shape + per-call cardinality + bounded confidence. | **strong (closed this iteration)** |
| `evaluation-svc` | 3 | `setup_observability` + FastAPI visible | add deeper eval workflow spans and async/replay visibility | partial |
| MCP servers (`hr`, `itsm`, `drills`) | 5 | shared `setup_server_otel` + FastAPI instrumentation + per-call span attributes for actor (`mcp.actor.id`, `mcp.actor.email`), outcome (`mcp.outcome` ∈ {ok, error, replay, conflict, in_progress, http_*}), tenant, correlation_id, idempotency-replay flag — set in `mcp/server_common.handle_tool_call`. Drill `drill_otel_actor_outcome_attrs.py` proves actor identification fires per-call and respects auth boundaries (no leak on 401 / 403). | **strong (closed this iteration)** |
| `api-gateway` | 1 | OTel dependencies in Go module, but no visible init in main path | add real OTel initialization, HTTP middleware instrumentation, outbound trace propagation | weak |
| `identity-svc` | 0 | no visible OTel wiring in inspected code | implement startup OTel + request tracing | missing |
| `governance-svc` | 0 | no visible OTel wiring in inspected code | implement startup OTel + policy/audit path spans | missing |
| `finops-svc` | 0 | no visible OTel wiring in inspected code | implement startup OTel + aggregation path spans | missing |
| `observability-svc` | 0 | no visible OTel wiring in inspected code | implement startup OTel + admin API spans | missing |
| `frontend` | 1 | OTel package references exist in lockfile, but no clear active browser tracing path inspected | decide whether browser tracing is required and wire explicitly if yes | weak |
| `draft replay worker` | 3 | explicit tracer use visible in worker | preserve span continuity and improve replay-specific attributes | partial |
| `multi-hop agent` | 2 | conceptual breaker story strong, but no obvious deep custom tracing in skeleton | add step spans for planning, retrieval hops, synthesis, stop reasons | partial |

## 4. Completed Work Already Present

These appear already done in the repo:

### Shared Python observability layer

- [libs/py/documind_core/observability.py](/mnt/deepa/rag/libs/py/documind_core/observability.py)
- FastAPI instrumentation helper
- asyncpg instrumentation helper
- httpx instrumentation helper
- redis instrumentation helper
- OTel setup with OTLP exporters
- observability circuit breaker around exporters

### Python services with visible wiring

- [services/ingestion-svc/app/main.py](/mnt/deepa/rag/services/ingestion-svc/app/main.py)
- [services/retrieval-svc/app/main.py](/mnt/deepa/rag/services/retrieval-svc/app/main.py)
- [services/inference-svc/app/main.py](/mnt/deepa/rag/services/inference-svc/app/main.py)
- [services/evaluation-svc/app/main.py](/mnt/deepa/rag/services/evaluation-svc/app/main.py)

### MCP server OTel scaffold

- [mcp/server_common.py](/mnt/deepa/rag/mcp/server_common.py)
- used by:
  - [mcp/server_hr.py](/mnt/deepa/rag/mcp/server_hr.py)
  - [mcp/server_itsm.py](/mnt/deepa/rag/mcp/server_itsm.py)
  - [mcp/server_drills.py](/mnt/deepa/rag/mcp/server_drills.py)

### Some worker-level tracing

- [services/inference-svc/app/workers/draft_replay.py](/mnt/deepa/rag/services/inference-svc/app/workers/draft_replay.py)

## 5. Current Gaps

### Gap 1: Go services are not clearly instrumented

From visible code inspection, I do not see explicit OTel initialization in:

- `api-gateway`
- `identity-svc`
- `governance-svc`
- `finops-svc`
- `observability-svc`

That is the largest coverage gap.

### Gap 2: service-level instrumentation is stronger than tool-level spans

Python services are instrumented, but “tool-level” coverage is still not uniformly deep.

Examples of likely missing or thin spans:

- agent tool-decision span
- per-tool dispatch span with rich attributes
- replay transition span
- evaluation replay span
- vector vs graph retrieval decision spans

### Gap 3: frontend/browser-level telemetry is not clearly active

The frontend references OTel-related packages in dependencies, but active browser tracing is not clearly visible from the inspected app code.

### Gap 4: failure-path span coverage needs explicit review

A path can be instrumented on success but still weak on:

- denials
- degraded fallback
- replay conflict
- audit failure
- timeout and cancellation paths

## 6. Definition Of Done By Tool

## 6.1 API gateway

Done means:

- startup initializes OTel
- incoming HTTP requests create spans
- downstream calls propagate trace context
- auth failures and route failures are visible
- admin and user paths are distinguishable

## 6.2 Python services

Done means:

- service setup initializes OTel
- inbound FastAPI spans exist
- outbound httpx, redis, and asyncpg calls are instrumented where relevant
- key domain operations have manual spans
- failed and degraded paths are still visible

## 6.3 MCP servers

Done means:

- `/tools/list` and `/tools/call` are traced
- per-tool dispatch has useful span attributes
- scope denial and error paths are visible
- idempotent replay and degraded outcomes are visible in telemetry

## 6.4 Agent flows

Done means:

- ask flow has trace continuity
- tool-decision point is visible
- scope denial is visible
- degraded draft fallback is visible
- replay path links back clearly enough for operators

## 6.5 Kafka and async workers

Done means:

- event production and consumption can be correlated
- replay or backlog work has spans
- worker sweeps and queue lag can be explained

## 7. Task Tracker

## 7.1 Current tasks in progress

Use this as the current active tracker.

| Area | Current task | Priority | Status |
|---|---|---|---|
| Go services | confirm or add OTel init and request tracing | P0 | open |
| API gateway | add end-to-end OTel wiring and outgoing propagation | P0 | open |
| MCP | enrich tool-level spans and failure attributes | P1 | open |
| inference agent | add tool-decision and degraded-path spans | P1 | open |
| retrieval | add richer vector/graph/cache spans | P1 | open |
| frontend | decide whether browser tracing is in scope and implement if yes | P2 | open |
| evaluation | add replay/eval-specific span coverage | P2 | open |

## 7.2 Future plan tasks

| Phase | Task |
|---|---|
| Phase 1 | instrument all Go services at startup and request level |
| Phase 2 | enrich manual spans for MCP, agent, replay, and retrieval decisions |
| Phase 3 | add async and worker trace continuity where practical |
| Phase 4 | add browser tracing if the team wants frontend-first incident diagnosis |
| Phase 5 | create OTel coverage tests and dashboards as release gates |

## 7.3 “Done” tracking fields

When working a tool/component, track:

- owner
- code path
- startup wiring done
- inbound spans done
- outbound spans done
- failure-path spans done
- trace propagation validated
- dashboard visible
- drill or test coverage exists

## 8. Recommended Tracking Table

Use this operational table:

| Component | Owner | Startup wired | Inbound spans | Outbound spans | Failure-path spans | Propagation checked | Dashboard ready | Drill/test ready | Overall |
|---|---|---|---|---|---|---|---|---|---|
| API gateway |  |  |  |  |  |  |  |  |  |
| ingestion-svc |  |  |  |  |  |  |  |  |  |
| retrieval-svc |  |  |  |  |  |  |  |  |  |
| inference-svc |  |  |  |  |  |  |  |  |  |
| evaluation-svc |  |  |  |  |  |  |  |  |  |
| identity-svc |  |  |  |  |  |  |  |  |  |
| governance-svc |  |  |  |  |  |  |  |  |  |
| finops-svc |  |  |  |  |  |  |  |  |  |
| observability-svc |  |  |  |  |  |  |  |  |  |
| MCP HR |  |  |  |  |  |  |  |  |  |
| MCP ITSM |  |  |  |  |  |  |  |  |  |
| MCP drills |  |  |  |  |  |  |  |  |  |

## 9. Release Standard

You should only call tool-level OTel “fully implemented” when:

- every critical component scores at least `4`
- no critical service remains at `0` or `1`
- trace continuity is verified across:
  - gateway
  - retrieval
  - inference
  - MCP
  - replay where applicable
- dashboards and drill evidence exist

## 10. Bottom Line

The repo already has strong Python-side service-level OTel foundations and strong MCP server scaffolding.

It is **not** yet honest to call OTel:

- fully implemented at each tool level

The right current statement is:

- strong partial implementation
- biggest remaining gap is Go-service coverage
- next maturity step is a tracked rollout to component-level and failure-path completeness
