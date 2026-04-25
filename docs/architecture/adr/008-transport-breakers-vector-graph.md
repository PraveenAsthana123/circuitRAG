# ADR-008: Per-backend transport breakers around Qdrant + Neo4j

## Status

Accepted — implemented in commit `87816d9`.

## Context

`HybridRetriever` already had a quality breaker
(`RetrievalCircuitBreaker`) that watched RESULT QUALITY: top score,
result count, rolling window. Useful for "the service is up but the
corpus is empty."

But it didn't watch transport-level exceptions. A 30-minute Qdrant
outage cost every retrieval the full timeout (~5s) per call — the
`asyncio.gather(return_exceptions=True)` in `retrieve` swallowed the
error into a degraded result, but didn't FAST-REJECT subsequent
calls. Retry storms, p95 latency spikes.

## Decision

Add two transport-level breakers, one per backend:

* `retrieval-vector-transport` — guards `VectorSearcher.search`
* `retrieval-graph-transport` — guards `GraphSearcher.search`

Default `failure_threshold=3, recovery_timeout=30.0` matching MCP
breakers. Failures re-raise into the existing `asyncio.gather`
`degraded`-path; CircuitOpenError is just one more exception class
the gather absorbs.

Two layers, orthogonal concerns:

* Quality breaker — "service is up but corpus is empty"
* Transport breaker — "service is unreachable" (NEW)

Backend independence is the load-bearing detail: a vector-backend
outage must NOT block graph queries. Each backend gets its own
breaker, so the failure blast-radius is scoped to one dependency.
`drill_retrieval_transport_breaker` step 4 is the regression
surface for that property.

## Consequences

* Retrieval p95 during a Qdrant outage drops from ~5s/call to
  microseconds (fast-reject path).
* Cost in observability: two new Prometheus series labelled
  `retrieval-{vector,graph}-transport`. Cardinality stays bounded
  per ADR-010 (no tenant label).
* The reviewer's circuit-breaker-gap-review item #1 closes. Items
  #2 (streaming Ollama protection), #3 (admin UI exposure — handled
  by the operator dashboard from commit `83fca90`), #4 (config
  standardization), and #5 (cluster coordination) remain open.
* Future per-shard breakers (e.g. Qdrant tenant-shard) would slot in
  with the same protocol — `CircuitBreaker` instance per shard,
  same drill shape.
