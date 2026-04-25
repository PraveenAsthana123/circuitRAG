# ADR-003: Postgres-backed idempotency via `IdempotencyStore` protocol

## Status

Accepted — implemented in commit `ce56ab6` + migration
`007_mcp_idempotency.sql`.

## Context

Each MCP server kept its idempotency cache as a process-local
`dict[str, dict]`:

* Not durable — a server restart wiped the cache; the next retry
  re-executed the side-effect.
* Not coordinated — a horizontally-scaled fleet had one cache per
  replica; a retry routed elsewhere re-executed.
* Unbounded — the dict grew forever in long-running servers.

The reviewer's framing: "calling that 'idempotent' is generous."

## Decision

Define an `IdempotencyStore` protocol in `mcp/idempotency.py` with
two methods:

* `lookup_or_register(key, tool, payload_fingerprint) -> (state, response)`
  where state ∈ `{"new", "in_progress", "done", "conflict"}`.
* `finalize(key, response, status="succeeded"|"failed")` —
  CAS-guarded: only transitions `in_progress → succeeded|failed`.

Two implementations:

* `InMemoryIdempotencyStore` — process-local dict, dev/single-node.
* `PostgresIdempotencyStore` — durable, coordinated, TTL-purged
  inline on every read. Same-key + different payload-fingerprint
  → `"conflict"` state → 409 from `handle_tool_call`.

Backed by `governance.mcp_idempotency` (migration 007), service-
scope (not tenant-scope, see migration header for the why).

Tooling agreement: `handle_tool_call` stays dumb — get-or-record.
The store handles fingerprinting, conflict detection, TTL purge.
The seam is "everything that previously took `idempotency_cache:
dict` now takes `idempotency_store: IdempotencyStore`."

## Consequences

* Server restart no longer wipes idempotency state — same retry
  with the same key returns the cached response across restarts.
* Multi-replica MCP fleet stays coherent: any replica's lookup
  hits the shared `governance.mcp_idempotency` table.
* Same-key + different-payload → 409 surfaces client bugs that
  previously masqueraded as "stale data."
* CHECK constraint on the `status` column prevents future code
  from writing nonsense statuses (storage-level state machine,
  same pattern as ADR-005).
* The PG implementation is a full asyncpg pool per server. For a
  service that already opens an asyncpg pool for drafts, that's
  redundant — a future iteration could share the pool.
