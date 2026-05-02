# `PostgresTaskStore` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/postgres_store.py`
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | row #36 closed: DbCircuitBreaker wired into PostgresTaskStore + /health/ready (drilled by `drill_db_circuit_breaker_wired.py`) |
| **P1** | 3 | rows #14 (no success-rate metric on DB calls), #19 (no admin endpoint to inspect / repair), #34 (asyncpg connection pool not gracefully drained on shutdown) |
| **P2** | 2 | rows #20, #22 |

## Highlights

- ✅ Parameterized queries (no f-string SQL)
- ✅ RLS on every tenant-scoped table (drilled by C3 / 015 audit migration)
- ✅ ON CONFLICT upserts preserve non-overwritten fields (defensive _maybe helper)
- ✅ A5 cost columns wired with backward-compat row decoder

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 1 | Per-call timeout | ⚠ | DbClient default; per-statement timeout not enforced |
| 5 | Narrow exception scope | ⚠ | `except Exception` in connect path |
| 13 | Latency histogram | ✗ | **P1** — no per-query histogram |
| 14 | Success counter | ✗ | **P1** — no metric for "DB calls / second succeeded" |
| 19 | Admin endpoint | ✗ | **P1** — no /admin/db/health with current connection-pool state |
| 34 | Graceful shutdown | ✗ | **P1** — `db.close()` in lifespan is fine if SIGTERM gives enough grace; under fast termination, in-flight queries get cut |
| 36 | DB CB | ✅ | **closed** — DbCircuitBreaker wired into PostgresTaskStore (`_admin_conn` helper guards 17 call sites); `/health/ready` returns 503 + DB_CIRCUIT_OPEN when breaker trips; `/health/live` deliberately stays 200 (cascade-restart prevention per §47.8). Locked by `drill_db_circuit_breaker_wired.py` steps 5-7. |

## Brutal one-liner

> Parameterized SQL + RLS = **excellent SQL hygiene**. What's missing is the
> **failure surface**: no breaker, no per-query latency, no admin inspection.
> Postgres outage today = total service outage; should be graceful 503 + traffic
> shift via K8s.
