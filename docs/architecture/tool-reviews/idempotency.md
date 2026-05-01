# Idempotency module — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/idempotency.py` + migration 014
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 1 | row #34 (graceful shutdown — InMemoryIdempotencyStore not multi-pod safe; not yet wired to Postgres-backed store) |
| **P1** | 2 | rows #20 (TTL cleanup not scheduled), #21 (persistence wired schema-only, not service-side) |
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
| 21 | Persistent store | ⚠ | **P1** — schema present; Protocol allows in-memory and Postgres but Postgres adapter not yet implemented |
| 33 | Rate limit | ✗ | Same key submitted 1000× returns the cached result quickly — but the LOOKUP could be DOS'd |
| 34 | Graceful shutdown | ✗ | **P0** — InMemoryIdempotencyStore loses data on restart; multi-pod unsafe (different pods see different idempotency state) |
| 38 | Deadletter | n/a | — |

## Brutal one-liner

> Drill discipline is **excellent** (5 negative assertions on the contract).
> What's missing is **production wiring** — Postgres-backed store impl + service.py
> integration. Today the in-memory default is a multi-pod data loss risk; the
> migration table is unused. ~3 hours to wire properly.
