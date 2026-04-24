# Tenant-ID Span Attributes — `documind.tenant_id` on every span

**Status:** 🟢 Green. 6-step drill passes; Jaeger tag-filter by `documind.tenant_id=<uuid>` returns traces across all three services.
**Date:** 2026-04-24

Turns Jaeger from "find a trace by traceID" into "find every trace
a tenant has made in the last N hours." The operational hook
governance + SRE have wanted since the first trace commit.

---

## What shipped

```
libs/py/documind_core/middleware.py
  + SpanAttributeMiddleware          ← tags current span with authoritative
                                       documind.{tenant_id, correlation_id,
                                       user_id, roles}
services/inference-svc/app/main.py   ← wire SpanAttributeMiddleware first
services/retrieval-svc/app/main.py   ← same
mcp/server_hr.py                      ← mcp.tool:<name> child span now ALSO
                                       carries documind.tenant_id /
                                       documind.correlation_id (unified naming)
mcp/tests/drill_tenant_span_tags.py  ← 6-step drill
docs/DEMO-TENANT-SPAN-TAGS.md        ← this file
```

## How it works

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│ CorrelationId MW    │→ │ TenantContext MW    │→ │ JWTAuth MW (opt'l)  │→
│  sets               │  │  sets                │  │  overrides          │
│  state.correlation_id│  │  state.tenant_id    │  │  state.tenant_id +  │
└─────────────────────┘  │  from header         │  │  state.roles from   │
                         └─────────────────────┘  │  verified JWT claim  │
                                                  └──────────┬──────────┘
                                                             │
                                                             ▼
                                    ┌─────────────────────────────────────┐
                                    │ SpanAttributeMiddleware              │
                                    │  reads FINAL state, calls            │
                                    │  trace.get_current_span().set_attrs: │
                                    │    documind.tenant_id                │
                                    │    documind.correlation_id           │
                                    │    documind.user_id                  │
                                    │    documind.roles                    │
                                    └─────────────────────────────────────┘
```

`SpanAttributeMiddleware` is registered FIRST in the middleware chain
so it's INNERMOST — runs last on the request path, after every other
middleware has populated `request.state`. By the time it fires,
whatever authority produced the tenant_id (signed JWT claim, gateway-
forwarded header, dev X-Tenant-ID) has already won; this middleware
just surfaces the result to the tracing layer.

## Why a middleware, not `server_request_hook`

OpenTelemetry's `FastAPIInstrumentor` accepts a
`server_request_hook(span, scope)` that runs at request start. It's
seductive — one function, no middleware boilerplate — but it fires
BEFORE any app-level middleware runs, so `request.state` doesn't
exist yet. The tenant_id would have to be re-extracted from headers,
which:
1. Duplicates the logic in `TenantContextMiddleware` + `JWTAuthMiddleware`.
2. Can't see the JWT's tenant claim (no verifier available).

Middleware runs inside the server span's context, so
`trace.get_current_span().set_attribute(...)` writes to the right span
without any plumbing. Twelve lines; no duplicate logic.

## Cross-service naming

Unified under the `documind.` prefix so a single Jaeger filter catches
every service:

| Service | Span(s) that carry the tag |
| --- | --- |
| inference-svc | `POST /api/v1/agent/ask` + `POST /api/v1/ask` + `POST /api/v1/drafts/*` |
| retrieval-svc | `POST /api/v1/retrieve` |
| mcp-server-hr | `mcp.tool:<name>` (custom business span from earlier commit) |

MCP's `mcp.tenant_id` + `mcp.correlation_id` attributes stay too, as
back-compat aliases. Dashboards bound to either name keep working.

## The 6-step drill

```
── 1. sanity ──
  ✓ inference + jaeger reachable

── 2. fire /api/v1/agent/ask → 3-service trace ──
  ✓ ok ticket=HR-C9A62DBA corr=310bb522-3ea6-42b3-a034-0e0cf118f76b

── 3. wait 8s for batch flush ──
  ✓ flushed

── 4. fetch agent/ask traces tagged with THIS correlation_id ──
  ✓ 3-service trace traceID=a77d784826a3d7d0a735ec6fbe3a2337
    (correlation_id match)

── 5. assert documind.tenant_id on each service's spans ──
  ✓ inference-svc has at least one span tagged
    documind.tenant_id=137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a
  ✓ retrieval-svc has at least one span tagged ...
  ✓ mcp-server-hr has at least one span tagged ...

── 6. jaeger tag-filter search returns a non-empty set ──
  ✓ tag-filter search returned 2 traces

════════════════════════════════════════
  ALL 6 TENANT-SPAN-TAG STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_tenant_span_tags.py`

## Lesson from the first run

First drill run failed because it grabbed a stale pre-middleware
trace (`traceID=be5bfcb5...`) — the drill's "find the most recent
3-service trace" heuristic happily returned a trace from hours
earlier that predated the middleware change. Tests that filter
on "recent" are a classic source of flake.

Fixed by filtering by the `documind.correlation_id` that *this drill
run* generated. The Jaeger API accepts a `tags` JSON-encoded filter:

```
GET /api/traces?service=inference-svc&tags={"documind.correlation_id":"<ours>"}
```

That guarantees we inspect the trace produced by *our* `agent/ask`
call, not a coincidentally-matching historical trace. Same fix
applies to any drill that asserts on "the latest X" — tag-filter on
a drill-specific value instead.

## Operational payoff

Jaeger UI → `inference-svc` → Tags filter:
```
documind.tenant_id=137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a
```
Returns every trace that tenant has produced across the service mesh,
including retrieval and MCP sub-traces under the same IDs. A SRE
investigating "tenant A reports slow p99 at 14:30" now starts a
tenant-scoped search in ~3 clicks instead of grep-ing logs for
correlation_ids.

Combined with earlier commits, the investigation chain is:
1. `/api/v1/health/detailed` — is anything degraded right now?
2. Prometheus gauge — did a breaker trip and when?
3. Jaeger tenant-filtered search — which traces for this tenant
   were affected?
4. Inside a trace, AsyncPG spans — which query took 400ms?
5. `governance.audit_log` (via verifier) — did tampering correlate
   with the incident window?

Five separate tools built over the last several commits, each with
its own drill, composing into one operational workflow.

## Remaining follow-ups

- **Tenant on error spans** — today if a route raises, the exception
  recorder runs BEFORE SpanAttributeMiddleware fires. A follow-up moves
  attribute setting into `server_request_hook` for just the root span
  OR wraps routes with a decorator that tags on exception paths too.
- **`documind.tool_name` on agent/ask** — when the agent calls an MCP
  tool, we know the tool name at the route layer. Adding that to the
  root span means "find every agent/ask that touched hr.leave_request"
  works from the inference side without hopping to mcp-server-hr spans.
- **Metrics labels from span attrs** — a Prometheus span-metrics
  exporter could produce `documind_requests_total{tenant_id="..."}`
  counters, closing the observability triangle (metrics for
  aggregation, traces for investigation, logs for context).
