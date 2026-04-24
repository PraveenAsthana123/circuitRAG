# Distributed Tracing — OTel → Collector → Jaeger

**Status:** 🟢 Green. 8-step drill passes; multi-service trace trees land in Jaeger with both inference-svc and retrieval-svc spans under a single traceID.
**Date:** 2026-04-24

Shifts the focus from governance (HITL stack) to observability. Every
Python service was already emitting OTel spans; what was missing was
evidence that the pipeline from the service processes → OTel Collector
→ Jaeger actually worked end-to-end, and that spans from different
services correlated on a single traceID.

---

## What shipped

```
mcp/tests/drill_trace.py          — 8-step drill asserting multi-service tree
infra/observability/otel-config.yaml  — (no changes; already had traces
                                         pipeline to jaeger:4317)
/tmp/start-{ingestion,retrieval,inference}-env.sh
                                  — DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT
                                    and distinct DOCUMIND_PROMETHEUS_PORT
                                    per service
docs/DEMO-TRACE.md                — this file
```

No code changes were required in the services — instrumentation was
already wired via `documind_core.observability.setup_observability()`.
The fix was purely operational: bring up the collector with working
port bindings and point the services at it.

## Infra pipeline

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ inference-svc   │    │ retrieval-svc   │    │ ingestion-svc   │    │ OTel Collector  │
│ uvicorn :8084   │    │ uvicorn :8083   │    │ uvicorn :8082   │    │ :4317 gRPC      │
│                 │    │                 │    │                 │    │                 │
│ BatchSpanProc → │────┤ BatchSpanProc → │────┤ BatchSpanProc → │───▶│ traces pipeline │
│ OTLP gRPC       │    │ OTLP gRPC       │    │ OTLP gRPC       │    │ batch + resource│
└─────────────────┘    └─────────────────┘    └─────────────────┘    │ memory_limiter  │
                                                                     └────────┬────────┘
                                                                              │ otlp/jaeger
                                                                              ▼
                                                              ┌────────────────────────────┐
                                                              │ Jaeger all-in-one :16686   │
                                                              │ UI + /api/services +       │
                                                              │ /api/traces query          │
                                                              └────────────────────────────┘
```

Instrumentation already in `documind_core`:
- `FastAPIInstrumentor.instrument_app(app)` — one span per HTTP request,
  `POST /api/v1/<path>` naming.
- `HTTPXClientInstrumentor()` — outbound `httpx.AsyncClient` calls get
  a span with propagation headers, so the downstream FastAPI middleware
  sees the parent traceID.
- `RedisInstrumentor` — `EVALSHA`, `SETEX`, `GET` spans on each Redis op.
- `AsyncPGInstrumentor` (available but not activated in lifespan —
  follow-up).

## Captured evidence

```
── 1. sanity — inference + retrieval + jaeger reachable ──
  ✓ all three reachable

── 2. /api/v1/ask — fires distributed trace ──
  ✓ ask returned correlation_id=cce0b409-573b-468c-8dc6-5c6adcf34b6a

── 3. wait for BatchSpanProcessor flush (8s) ──
  ✓ flushed

── 4. jaeger /api/traces?service=inference-svc — find multi-service trace ──
  ✓ multi-service trace found
    traceID=009e5033bb0b83a7023a143201d61278
    services={'retrieval-svc': 10, 'inference-svc': 8}

── 5. assert inference + retrieval both contributed spans ──
  ✓ inference ops include POST /api/v1/ask
  ✓ retrieval ops include POST /api/v1/retrieve

── 6. /api/v1/agent/ask — agent + MCP trace ──
  ✓ agent trace multi-service
    traceID=d0a5101e6d6868a0ef1b587eb1d7f7e3
    services={'inference-svc': 10, 'retrieval-svc': 10}

── 7. dump trace sample → /tmp/documind-trace-sample.json ──
── 8. jaeger reports all 3 services enrolled ──
  ✓ services in jaeger: ['inference-svc', 'ingestion-svc',
                          'jaeger-all-in-one', 'retrieval-svc']

════════════════════════════════════════
  ALL 8 TRACE STEPS PASSED
════════════════════════════════════════
```

### Operation breakdown for a `/api/v1/ask` trace

```
traceID: 009e5033bb0b83a7023a143201d61278  (18 spans total)

inference-svc (8 spans):
  POST /api/v1/ask                   ← server-side FastAPI span
  POST /api/v1/ask http send         ← raw middleware span
  POST /api/v1/ask http receive
  POST                               ← httpx outbound to retrieval
  EVALSHA                            ← Redis rate-limit Lua call

retrieval-svc (10 spans):
  POST /api/v1/retrieve
  POST /api/v1/retrieve http send
  POST /api/v1/retrieve http receive
  POST                               ← httpx outbound to qdrant
  GET                                ← httpx outbound (e.g. neo4j bolt proxy)
  EVALSHA                            ← Redis rate-limit
  SETEX                              ← cache.set_json after successful fetch
```

The Redis `EVALSHA` on both services shows the sliding-window
rate-limiter firing — useful for perf investigations.
The `SETEX` on retrieval-svc is the cache write that the cache-poisoning
guard (committed earlier in chaos drill #1) protects with a
`backend_failed` flag.

Open in Jaeger UI:
`http://127.0.0.1:16686/trace/009e5033bb0b83a7023a143201d61278`

---

## Two bugs the drill surfaced

Neither of these was new code breaking; both were latent operational
gaps the drill made visible.

### 1. Collector container had no port bindings

First `docker compose up -d otel-collector` failed with
`failed to bind host port 0.0.0.0:9464: address already in use` — the
ingestion-svc uvicorn was already squatting 9464 for its own
Prometheus scrape. Docker created the container but left it with
*zero* port mappings. The second `up -d` just started the existing
broken container. Ports 4317/4318 weren't reachable from the host,
so every span export got `StatusCode.UNAVAILABLE`.

**Fix:** run `docker compose up -d --force-recreate otel-collector`
after clearing the 9464 conflict. Ingestion now uses 9467 in its
start-env script.

### 2. Observability Circuit Breaker (OCB) tripped silently

Because span export was failing, inference-svc's
`_BreakerGuardedMetricExporter` (the OCB around OTLP, committed
earlier in the observability module) transitioned CLOSED → OPEN and
stopped trying. Reading
```
otel_initialized endpoint=http://localhost:4317 service=inference-svc
Transient error StatusCode.UNAVAILABLE encountered while exporting traces
Failed to export traces to localhost:4317
obs_breaker name=otlp-export from=closed to=open
```
told me the pipeline wasn't failing *loudly* — but the OCB kept the
breaker state visible in the service log, which is exactly what it's
for.

**Fix:** once the collector was healthy, restarting the three services
reset the OCB to CLOSED and traces started flowing. In production
the OCB will HALF_OPEN-probe on its own; here we wanted the first
cycle to be clean.

---

## Update (commit after initial drill): MCP server-side OTel wired

The MCP server is now instrumented too. Every `/tools/call` produces:

  * `POST /tools/call` — FastAPI server span (auto)
  * `POST /tools/call http send` / `http receive` — middleware spans
  * `mcp.tool:<name>` — custom child span with attributes:
    `mcp.tool.name`, `mcp.tenant_id`, `mcp.correlation_id`,
    `mcp.idempotency_key_present`, `mcp.idempotent_replay`

W3C traceparent propagation works out of the box: `HTTPXClientInstrumentor`
in inference-svc injects the header, `FastAPIInstrumentor` in the MCP
server extracts it. An agent/ask that touches the leave tool now
produces a 24-span tree across three services:

```
traceID=be5bfcb517dd632b51ae754b1449823d
  inference-svc:    10 spans
  retrieval-svc:    10 spans
  mcp-server-hr:     4 spans
    POST /tools/call
    POST /tools/call http receive
    POST /tools/call http send
    mcp.tool:hr.leave_request    ← filterable in Jaeger
```

The `mcp.tool:` prefix lets a Jaeger search surface a specific tool
invocation regardless of which generic endpoint hosted it. Filtering
by tag `mcp.tool.name=hr.leave_request` catches every ticket-creation
event across a time window — the operational hook governance has
been asking for.

Trade-off: `mcp/server_hr.py` now has ~45 LoC of optional OTel setup.
Kept in the `mcp/` package (no `documind_core` import) so the package
stays consumable by any service that wants it.

## Remaining follow-ups

_(MCP server-side span — done, see above.)_
- Activate `AsyncPGInstrumentor` in service lifespans so PG queries
  get spans (today DB calls are invisible in the trace tree).
- Attach `tenant_id` and `correlation_id` as span attributes on the
  inbound FastAPI span — so Jaeger searches can filter by tenant.
- Sample rate: today every span is exported. Add
  `ParentBased(TraceIdRatioBased(0.1))` via config for high-volume
  envs.
- Grafana Tempo datasource — Jaeger is fine for drills; Tempo gives
  you trace search from within Grafana alongside Prometheus.
