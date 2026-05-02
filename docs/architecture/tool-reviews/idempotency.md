# Idempotency module — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/idempotency.py` + migration 014
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | row #34 closed: PostgresIdempotencyStore wired into POST /api/v1/agentic/tasks via X-Idempotency-Key header (drilled by `drill_idempotency_postgres_wired.py`). Lifespan picks Postgres when DB is up, falls back to InMemoryIdempotencyStore in dev. |
| **P1** | 1 | row #20 (TTL cleanup not scheduled) — row #21 closed by P0 #34 wiring |
| **P2** | 2 | rows #19, #22 |

## Highlights

- ✅ Composite PK (tenant_id, key) — drilled to prevent cross-tenant collision
- ✅ Canonical SHA-256 (sorted keys, separators=(",",":") — drilled
- ✅ IdempotencyConflict raised on key+different-body — drilled
- ✅ Migration 014 with RLS policy

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 19 | Operator override | ✗ | Operator can't manually retire an idempotency key (e.g. force-replay) |
| 20 | TTL cleanup cron | ✗ | **P1** — schema has TTL index hint but no scheduled cleanup |
| 21 | Persistent store | ✅ | **closed** — PostgresIdempotencyStore wired in main.py lifespan; route handler calls lookup_or_reserve + save_record on every keyed POST |
| 33 | Rate limit | ✗ | Same key submitted 1000× returns the cached result quickly — but the LOOKUP could be DOS'd |
| 34 | Graceful shutdown | ✅ | **closed** — PostgresIdempotencyStore on the request hot path; multi-pod safe via shared Postgres `orchestration.idempotency_keys` table. Drilled end-to-end (cache hit + conflict + persistence) by `drill_idempotency_postgres_wired.py`. |
| 38 | Deadletter | n/a | — |

## Brutal one-liner

> Drill discipline is **excellent** (5 negative assertions on the contract).
> What's missing is **production wiring** — Postgres-backed store impl + service.py
> integration. Today the in-memory default is a multi-pod data loss risk; the
> migration table is unused. ~3 hours to wire properly.
