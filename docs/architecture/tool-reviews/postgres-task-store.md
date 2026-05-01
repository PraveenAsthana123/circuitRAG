# `PostgresTaskStore` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/postgres_store.py`
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 1 | row #36 (no breaker around Postgres calls — DB outage = orchestrator service down with no graceful degradation) |
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
| 36 | DB CB | ✗ | **P0** — Postgres outage = every endpoint returns 500. Should wrap with a CB so /health/ready returns 503 instead, K8s can redirect traffic. |

## Brutal one-liner

> Parameterized SQL + RLS = **excellent SQL hygiene**. What's missing is the
> **failure surface**: no breaker, no per-query latency, no admin inspection.
> Postgres outage today = total service outage; should be graceful 503 + traffic
> shift via K8s.
