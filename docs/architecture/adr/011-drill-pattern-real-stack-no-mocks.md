# ADR-011: Drills exercise real services; mocks belong in pytest

## Status

Accepted — codified in CLAUDE.md §43 and ~/.claude/policies/drill-testing-pattern.md.

## Context

The repo uses two complementary testing surfaces:

* **pytest** — fast, in-process, may mock dependencies, runs in CI
  on every PR. Covers pure-function logic, schema validation,
  unit-level correctness.
* **drills** — slow-by-design, talk to real services, ship as a
  named regression surface alongside the feature commit. Cover
  cross-service behavior, chaos, state machines, circuit breakers,
  HITL flows, multi-namespace routing.

The temptation is to blur the line: write a drill that mocks MCP
because the test setup is easier. Result: the drill passes against
a mock that diverges from the real MCP behavior, and the regression
surface is theatrical.

## Decision

**Drills exercise the real running stack.** No mocks for runtime
dependencies (MCP servers, Postgres, Qdrant, Neo4j, Ollama, the
inference service). Mocks belong in pytest.

Mechanics:

* Each drill is a standalone Python script under `mcp/tests/drill_*.py`.
* Discoverable by `scripts/run_drills.py` (resource-aware parallel
  runner) and `mcp/server_drills.py` (MCP-exposed runner).
* Resource tags (`# RESOURCES: mcp_hr inference pg`) declare what
  the drill touches — the runner uses these to schedule disjoint
  drills concurrently.
* Every drill ships at least one **negative assertion**: prove
  something does NOT happen, not just that the happy path works.

Exceptions for in-process drills exist, narrowly:

* Component-level drills that exercise a Protocol seam (e.g.
  `drill_retrieval_degraded_envelope` stubs the vector + graph
  backends because the test is about response-shape contract, not
  storage-layer behavior). Stubs are still NOT mocks — they
  implement the real protocol; just deterministically.

* Per-drill UUID tenants for isolation (`drill_worker_metrics`,
  `drill_retrieval_tenant_isolation`, etc.) — the data layer is
  real Postgres / Qdrant; only the tenant identity is per-drill
  to keep counter and result assertions deterministic.

## Consequences

* Drills catch the bugs that compose across services. The
  `drill_audit_actor_type` regression surface is the textbook
  example: catches both audit writer + worker + admin route +
  resolve_draft + reject_draft semantics in one 5-step run.
* Drills are slow. Some take 60+ seconds (CB recovery_timeout etc.).
  CI parallelism + the resource-aware scheduler + observation-
  driven waits (ADR follow-up: drill_audit_actor_type went from
  75s to 11.5s by replacing fixed `sleep(32)` with config-driven
  polling) mitigate but don't eliminate.
* Every feature commit ships a drill. Bug-fix commits ship a drill
  that would have caught the bug. CLAUDE.md §43.5 makes this
  blocking at review.
* The drill scoreboard is the regression surface for the whole
  project — counted, named, durable.
