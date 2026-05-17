# Database Assessment - `migrations`

**Profile:** Database (PostgreSQL (SQL files))
**Generated:** 2026-05-17 02:05 UTC
**Reviewer:** Praveen Asthana

> 25-section database-specific production assessment. Reviewer fills Status / Notes / Risk / Recommendation per row. Skeleton starts with TBD per global honesty rule.

---

## Metadata (auto-detected)

| Field | Value |
|---|---|
| Folder | `services/observability-svc/migrations` |
| Profile | Database |
| Runtime | PostgreSQL (SQL files) |
| SQL files | 1 |
| Migration files | 1 |
| `migrations/` dir | no |
| `schemas/` dir | no |
| Alembic detected | no |
| Flyway detected | no |
| ORM / DB client libs | _(none)_ |
| Database engines (detected) | PostgreSQL |
| Row-Level Security present | no |
| JSONB column type used | yes |
| Partition tables | no |
| `CREATE INDEX CONCURRENTLY` used | no |
| Foreign keys defined | yes |
| Lines of code (rough) | 0 |
| Git authors | 1	Praveen, 1	PraveenAsthana123 |
| Reviewer | Praveen Asthana |
| Generated | 2026-05-17 02:05 UTC |

---

### 1. Schema design

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Database engine documented? Detected: PostgreSQL | TBD | — | — | — |
| 2. Normalized to 3NF (no redundant columns)? | TBD | — | — | — |
| 3. Foreign keys defined? Detected: True | TBD | — | — | — |
| 4. Surrogate vs natural keys decision documented? | TBD | — | — | — |
| 5. Timestamps (created_at, updated_at) on every mutable table? | TBD | — | — | — |
| 6. Soft-delete pattern (`deleted_at`) vs hard DELETE? | TBD | — | — | — |
| 7. Tenant_id column on every multi-tenant table? | TBD | — | — | — |
| 8. Schema versioned in source control? | TBD | — | — | — |

### 2. Migrations

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Migration files numbered + ordered? Detected: 1 files | TBD | — | — | — |
| 2. Each migration is reversible (down.sql)? | TBD | — | — | — |
| 3. Migrations idempotent (safe to re-run)? | TBD | — | — | — |
| 4. Expand -> migrate -> contract pattern (never add+drop same release)? | TBD | — | — | — |
| 5. Tool: Alembic (False) / Flyway (False) / custom? | TBD | — | — | — |
| 6. Migration applied via app startup OR explicit deploy step? | TBD | — | — | — |
| 7. Migration history tracked in `_migrations` table? | TBD | — | — | — |
| 8. Production-data backfills tested in staging? | TBD | — | — | — |

### 3. Indexing

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Index on every foreign key? | TBD | — | — | — |
| 2. Index on every WHERE column on tables > 1000 rows? | TBD | — | — | — |
| 3. Index on ORDER BY column? | TBD | — | — | — |
| 4. Composite index for hot multi-column queries (column order matters)? | TBD | — | — | — |
| 5. Partial index for soft-delete (`WHERE deleted_at IS NULL`)? | TBD | — | — | — |
| 6. `CREATE INDEX CONCURRENTLY` for production? Detected: False | TBD | — | — | — |
| 7. Index bloat monitored (vacuum + analyze schedule)? | TBD | — | — | — |
| 8. Unused indexes audited periodically? | TBD | — | — | — |

### 4. Transactions (ACID)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Isolation level documented per use case (READ COMMITTED vs SERIALIZABLE)? | TBD | — | — | — |
| 2. Transaction boundaries narrow (no HTTP / LLM inside)? | TBD | — | — | — |
| 3. Rollback on exception? | TBD | — | — | — |
| 4. Retry on serialization failure (40001)? | TBD | — | — | — |
| 5. Pessimistic vs optimistic locking decision per table? | TBD | — | — | — |
| 6. Deadlock prevention (consistent lock order)? | TBD | — | — | — |
| 7. Savepoints used for nested transactions? | TBD | — | — | — |

### 5. Multi-tenant isolation

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Row-Level Security policies enabled? Detected: False | TBD | — | — | — |
| 2. Tenant context set at connection (`SET app.current_tenant`)? | TBD | — | — | — |
| 3. Tenant-id column on every row? | TBD | — | — | — |
| 4. BYPASSRLS role isolated from app code? | TBD | — | — | — |
| 5. Wrong-tenant query returns ZERO rows (drill-locked)? | TBD | — | — | — |
| 6. Per-tenant connection pool limits? | TBD | — | — | — |

### 6. Connection pooling

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Pool size sized per service (not unlimited)? | TBD | — | — | — |
| 2. Connection timeout configured? | TBD | — | — | — |
| 3. Idle connection eviction? | TBD | — | — | — |
| 4. PgBouncer / proxy in front of Postgres? | TBD | — | — | — |
| 5. Read replica routing for read-heavy workloads? | TBD | — | — | — |
| 6. Connection lifecycle managed by ORM (not raw)? | TBD | — | — | — |

### 7. Query optimization

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. EXPLAIN ANALYZE run on every new hot-path query? | TBD | — | — | — |
| 2. `pg_stat_statements` enabled? | TBD | — | — | — |
| 3. Slow query log in Grafana? | TBD | — | — | — |
| 4. No SELECT * (explicit columns)? | TBD | — | — | — |
| 5. No N+1 (batched IN/JOIN)? | TBD | — | — | — |
| 6. Pagination uses keyset (not OFFSET) for large tables? | TBD | — | — | — |
| 7. JOIN order verified for query planner? | TBD | — | — | — |

### 8. Concurrency + locking

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Hot rows identified (FOR UPDATE strategy)? | TBD | — | — | — |
| 2. Lock wait timeout configured? | TBD | — | — | — |
| 3. Long transactions detected + alerted? | TBD | — | — | — |
| 4. Advisory locks for app-level coordination? | TBD | — | — | — |
| 5. VACUUM frequency tuned for high-write tables? | TBD | — | — | — |

### 9. Backup + recovery

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Continuous WAL archiving to S3? | TBD | — | — | — |
| 2. Daily snapshots retained N days? | TBD | — | — | — |
| 3. Restore drill monthly (operator runs + measures RTO)? | TBD | — | — | — |
| 4. Backup encryption at rest (KMS)? | TBD | — | — | — |
| 5. Cross-region backup replication? | TBD | — | — | — |
| 6. Point-in-time recovery tested? | TBD | — | — | — |

### 10. Partitioning + sharding

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Partitioned tables? Detected: False | TBD | — | — | — |
| 2. Partition pruning strategy documented? | TBD | — | — | — |
| 3. Sharding key chosen (avoid hot shards)? | TBD | — | — | — |
| 4. Resharding plan + tooling? | TBD | — | — | — |
| 5. Cross-shard queries minimized? | TBD | — | — | — |

### 11. Data types

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. JSONB for flexible schema? Detected: True | TBD | — | — | — |
| 2. ENUM vs lookup table decision documented? | TBD | — | — | — |
| 3. TIMESTAMPTZ (not TIMESTAMP) for all timestamps? | TBD | — | — | — |
| 4. UUID v4 vs v7 / ULID choice documented? | TBD | — | — | — |
| 5. DECIMAL for money (never FLOAT)? | TBD | — | — | — |
| 6. TEXT vs VARCHAR(N) decision (TEXT preferred in PG)? | TBD | — | — | — |

### 12. Data integrity

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. NOT NULL on every required column? | TBD | — | — | — |
| 2. CHECK constraints for business invariants? | TBD | — | — | — |
| 3. UNIQUE constraints for natural keys? | TBD | — | — | — |
| 4. Foreign key ON DELETE behavior chosen (CASCADE / SET NULL / RESTRICT)? | TBD | — | — | — |
| 5. Trigger usage minimized (logic in app code preferred)? | TBD | — | — | — |

### 13. Security

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. No DB credentials in code (Vault / env)? | TBD | — | — | — |
| 2. App role least-privileged (SELECT/INSERT/UPDATE only)? | TBD | — | — | — |
| 3. RLS enforced for all app queries? | TBD | — | — | — |
| 4. SQL injection prevented (parameterized queries everywhere)? | TBD | — | — | — |
| 5. Audit log for sensitive table changes? | TBD | — | — | — |
| 6. PII columns encrypted at rest (pgcrypto)? | TBD | — | — | — |

### 14. Performance monitoring

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. pg_stat_database scraped to Prometheus? | TBD | — | — | — |
| 2. Active connections + waiting count alerted? | TBD | — | — | — |
| 3. Replication lag alerted? | TBD | — | — | — |
| 4. Disk space alerted? | TBD | — | — | — |
| 5. Slow query alerted (> N seconds)? | TBD | — | — | — |

### 15. ORM hygiene (if applicable)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. ORM libs: none — using raw SQL | TBD | — | — | — |
| 2. Lazy loading avoided in hot paths? | TBD | — | — | — |
| 3. Eager loading explicit (joinedload / selectinload)? | TBD | — | — | — |
| 4. Session lifecycle per request (not per process)? | TBD | — | — | — |
| 5. Bulk operations use batch APIs (not loop + single insert)? | TBD | — | — | — |
| 6. Raw SQL escape hatch documented for complex queries? | TBD | — | — | — |

### 16. Caching

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Read-through cache (Redis) for hot rows? | TBD | — | — | — |
| 2. Cache invalidation on source row change? | TBD | — | — | — |
| 3. Per-tenant cache keys (no cross-tenant leak)? | TBD | — | — | — |
| 4. Materialized views for expensive aggregations? | TBD | — | — | — |
| 5. Cache stampede prevention (single flight)? | TBD | — | — | — |

### 17. Schema evolution + change mgmt

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Schema change requires ADR? | TBD | — | — | — |
| 2. Schema diff visible in PR review? | TBD | — | — | — |
| 3. Production schema vs staging diff zero? | TBD | — | — | — |
| 4. Downstream consumer notified before schema change? | TBD | — | — | — |
| 5. Breaking schema changes versioned (additive only in v1)? | TBD | — | — | — |

### 18. Testing

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Unit tests use real DB (testcontainers / docker)? | TBD | — | — | — |
| 2. Integration tests cover migration up + down? | TBD | — | — | — |
| 3. Drills assert RLS isolation (per project policy)? | TBD | — | — | — |
| 4. Property-based tests for invariants? | TBD | — | — | — |
| 5. Load tests at expected scale? | TBD | — | — | — |

### 19. Documentation

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. ER diagram in `docs/db/`? | TBD | — | — | — |
| 2. Data dictionary (column descriptions)? | TBD | — | — | — |
| 3. Migration changelog? | TBD | — | — | — |
| 4. Runbook for common DB incidents (replication lag, connection storm)? | TBD | — | — | — |

### 20. AI/RAG-specific (if applicable)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Vector column type (pgvector or external)? | TBD | — | — | — |
| 2. Embedding model version stored alongside vector? | TBD | — | — | — |
| 3. Re-embed strategy when model bumps? | TBD | — | — | — |
| 4. Per-tenant vector collection isolation? | TBD | — | — | — |
| 5. Hybrid retrieval index (BM25 + vector + metadata)? | TBD | — | — | — |

### 21. DR + RTO / RPO

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. RTO tier documented (< 15 min / < 1 hr / < 4 hr)? | TBD | — | — | — |
| 2. RPO documented (< 0 / < 15 min / < 1 hr)? | TBD | — | — | — |
| 3. Hot standby for tier-1? | TBD | — | — | — |
| 4. Failover drill quarterly? | TBD | — | — | — |
| 5. Cross-region DR for tier-1? | TBD | — | — | — |

### 22. Cost

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Storage growth monitored + alerted? | TBD | — | — | — |
| 2. Index storage vs table storage ratio tracked? | TBD | — | — | — |
| 3. Cold data archived (S3 + table partition drop)? | TBD | — | — | — |
| 4. Read replica cost vs latency tradeoff documented? | TBD | — | — | — |

### 23. Common DB mistakes (avoid)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. f-string SQL (use parameters)? | TBD | — | — | — |
| 2. Implicit transaction (rely on autocommit)? | TBD | — | — | — |
| 3. DROP COLUMN in same release that stops reading it? | TBD | — | — | — |
| 4. Missing index on hot-path WHERE column? | TBD | — | — | — |
| 5. Unbounded query without LIMIT? | TBD | — | — | — |
| 6. Synchronous DB call inside `async def`? | TBD | — | — | — |
| 7. Cross-tenant SELECT without WHERE tenant_id? | TBD | — | — | — |

### 24. Production gates

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. All migrations idempotent + reversible? | TBD | — | — | — |
| 2. Zero schema diff between staging and prod? | TBD | — | — | — |
| 3. Backup tested in last 30 days? | TBD | — | — | — |
| 4. p95 query latency within SLO? | TBD | — | — | — |
| 5. No table > 100M rows without partitioning plan? | TBD | — | — | — |

### 25. Sign-off

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. DBA reviewed | TBD | — | — | — |
| 2. Security reviewed (RLS + audit log) | TBD | — | — | — |
| 3. SRE reviewed (backup + DR) | TBD | — | — | — |
| 4. Tech Lead reviewed | TBD | — | — | — |
| 5. Data Engineer reviewed (lineage) | TBD | — | — | — |

---

_Generated by `scripts/generate_specialized_assessment.py --profile database`. Re-run after major changes._
