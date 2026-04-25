# ADR-002: Single canonical CircuitBreaker; `_MCPBreaker` deleted

## Status

Accepted — implemented in commit `d1845ab`.

## Context

Two breaker implementations co-existed:

* `libs/py/documind_core/circuit_breaker.py:CircuitBreaker` —
  asyncio-locked, full metric series (`documind_circuit_breaker_*`),
  transition counter, rejection metric, StrEnum state.
* `mcp/client.py:_MCPBreaker` — local, lockless, no metrics, no
  transition accounting, string-based state.

The reviewer's concern was drift: "until nobody can explain why one
breaker opens differently from another." Two implementations with
the same conceptual contract but different semantics is the kind
of debt that hides under "they look similar enough."

## Decision

Unify on `documind_core.circuit_breaker.CircuitBreaker`. Delete
`_MCPBreaker`.

Add a bool-return surface (`allow / record_success / record_failure`)
to the canonical breaker so MCP's idiom — "ask if I can call,
proceed or degrade" — keeps working without forcing every caller to
catch `CircuitOpenError`. Same state machine, same metrics, two
control-flow shapes.

Add a `breaker_name` ctor parameter to `MCPClient` so the lifespan
can pass `mcp_<namespace>` (matching the dashboard label scheme)
instead of the URL (which would create a duplicate Prometheus
series alongside the BreakerMetricsExporter's pushed series).

## Consequences

* One state machine, one metric model. Dashboards labelled by
  `name` show every breaker as the same time series shape regardless
  of where it's instantiated.
* The transition counter (`documind_circuit_breaker_transitions_total
  {name,from_state,to_state}`) increments only on real state changes,
  not per poll — covered by `drill_breaker_transitions`.
* `CircuitBreaker` exposes a `failures` property and StrEnum `state`,
  so `/api/v1/health/detailed` can render breaker rows without
  reaching into private attributes (the prior `_failures` access
  pattern is gone).
* Future breakers (transport, quality, observability) all use the
  same surface. ADR-008 (transport breakers) is a direct application.
