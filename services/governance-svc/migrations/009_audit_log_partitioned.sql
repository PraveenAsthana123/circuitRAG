-- 009_audit_log_partitioned.sql
--
-- Additive scaffold for monthly-partitioned audit retention.
--
-- The existing governance.audit_log stays UNTOUCHED; this migration
-- creates governance.audit_log_partitioned alongside it as a
-- declarative-partitioned table by RANGE (timestamp). Operations
-- decides cutover (backfill via INSERT ... SELECT, app write switch,
-- DROP old after retention) on a separate runbook — this migration
-- is reversible by `DROP TABLE governance.audit_log_partitioned;`.
--
-- WHY PARTITIONING (per /admin/explainability/deep#audit-rag-contract-regulation
-- and ~/.claude/policies/ai-explainability.md §4):
--   * EU AI Act Art. 12 requires ≥ 6 months retention.
--   * SOC 2 / regulated AI → 7 years.
--   * At ~1M predictions/day × ~5 KB/row × 7y ≈ 12 TB. Without
--     partitioning: full scans on compliance export, no efficient
--     archival, slow VACUUM, lock contention on hot indexes.
--   * Monthly partitions:
--       - Compliance queries by (tenant_id, time-range) hit ≤ 1 partition.
--       - Old partitions detach + archive to S3 / cold storage in O(1).
--       - RLS still applies (declarative partitioning preserves
--         policies on the parent).
--       - Indexes propagate from parent to partitions automatically.
--
-- WHY VANILLA POSTGRES (NOT pg_partman):
-- pg_partman is NOT available in the project's postgres:16-alpine
-- image (verified via pg_available_extensions). This migration uses
-- only declarative partitioning + a helper plpgsql function for
-- monthly partition creation. A future operations decision could
-- adopt pg_partman; the schema here is compatible.

-- ---------------------------------------------------------------------
-- 1. Partitioned parent table
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS governance.audit_log_partitioned (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id       UUID NOT NULL,
    actor_id        TEXT,
    actor_type      VARCHAR(20) NOT NULL,
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     UUID,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    correlation_id  UUID,
    ip_address      INET,
    user_agent      TEXT,
    previous_hash   TEXT,
    entry_hash      TEXT,
    -- Postgres declarative partitioning requires PK to include the
    -- partition key column. (id, timestamp) is the composite PK.
    -- Application code that joined audit_log on id alone keeps
    -- working — id is still globally unique within a partition AND
    -- across partitions because gen_random_uuid() is collision-safe.
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- ---------------------------------------------------------------------
-- 2. Indexes — propagate to every partition
-- ---------------------------------------------------------------------
-- Operator forensics by (tenant_id, time-range) — the dominant query
-- pattern (compliance export, dashboard filters).
CREATE INDEX IF NOT EXISTS idx_audit_log_p_tenant_time
    ON governance.audit_log_partitioned (tenant_id, timestamp DESC);

-- Forensics by correlation_id (the trace → draft → audit join key).
-- Partial index — most rows have a correlation_id, but we only
-- query when it's set, so a partial index is smaller + hotter.
CREATE INDEX IF NOT EXISTS idx_audit_log_p_correlation
    ON governance.audit_log_partitioned (correlation_id)
    WHERE correlation_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- 3. RLS — same shape as governance.audit_log (per migration 002)
-- ---------------------------------------------------------------------
-- FORCE-enabled so even table owner cannot bypass the policy without
-- BYPASSRLS. documind_app role is non-BYPASSRLS — RLS holds for it.
ALTER TABLE governance.audit_log_partitioned ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.audit_log_partitioned FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON governance.audit_log_partitioned;
CREATE POLICY tenant_isolation ON governance.audit_log_partitioned
    USING (
        tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
    );

-- ---------------------------------------------------------------------
-- 4. Helper function — create a monthly partition
-- ---------------------------------------------------------------------
-- Used by:
--   * This migration's bootstrap below (current + next 2 months).
--   * A future cron / scheduled worker that pre-creates partitions
--     for month N+1 BEFORE the boundary, so writes after midnight
--     on the first of the month never fail with "no partition".
-- Idempotent: CREATE TABLE IF NOT EXISTS. Returns the partition name
-- so the caller can log it.
CREATE OR REPLACE FUNCTION governance.create_audit_log_partition(
    yyyy TEXT, mm TEXT
) RETURNS TEXT AS $$
DECLARE
    partition_name TEXT;
    range_start    TEXT;
    range_end      TEXT;
    next_yyyy      TEXT;
    next_mm_int    INT;
BEGIN
    partition_name := format('audit_log_p_y%sm%s', yyyy, lpad(mm, 2, '0'));
    range_start    := format('%s-%s-01', yyyy, lpad(mm, 2, '0'));
    next_mm_int    := mm::int + 1;
    IF next_mm_int > 12 THEN
        next_yyyy   := (yyyy::int + 1)::text;
        next_mm_int := 1;
    ELSE
        next_yyyy   := yyyy;
    END IF;
    range_end := format('%s-%s-01', next_yyyy, lpad(next_mm_int::text, 2, '0'));
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS governance.%I PARTITION OF '
        'governance.audit_log_partitioned FOR VALUES FROM (%L) TO (%L)',
        partition_name, range_start, range_end
    );
    RETURN partition_name;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 5. Bootstrap — current month + next 2 months
-- ---------------------------------------------------------------------
-- Three months of headroom is the conservative default — in steady
-- state, a cron job pre-creates the next month every night. If the
-- cron breaks for two weeks, the system still has runway to repair
-- without dropping writes.
DO $bootstrap$
BEGIN
    PERFORM governance.create_audit_log_partition(
        to_char(NOW(),                      'YYYY'),
        to_char(NOW(),                      'MM')
    );
    PERFORM governance.create_audit_log_partition(
        to_char(NOW() + INTERVAL '1 month', 'YYYY'),
        to_char(NOW() + INTERVAL '1 month', 'MM')
    );
    PERFORM governance.create_audit_log_partition(
        to_char(NOW() + INTERVAL '2 months','YYYY'),
        to_char(NOW() + INTERVAL '2 months','MM')
    );
END
$bootstrap$;

-- ---------------------------------------------------------------------
-- 6. Cutover plan (informational comments — DO NOT execute here)
-- ---------------------------------------------------------------------
-- Operations decides the cutover separately. Recommended runbook:
--
--   Phase 1 (this migration):
--     audit_log_partitioned exists; audit_log untouched.
--     App still writes to audit_log.
--
--   Phase 2 (operations runbook):
--     Backfill in batches (with cron pre-creating older-month partitions):
--       INSERT INTO governance.audit_log_partitioned
--           (id, timestamp, tenant_id, actor_id, actor_type, action,
--            resource_type, resource_id, details, correlation_id,
--            ip_address, user_agent, previous_hash, entry_hash)
--       SELECT id, timestamp, tenant_id, actor_id, actor_type, action,
--              resource_type, resource_id, details, correlation_id,
--              ip_address, user_agent, previous_hash, entry_hash
--       FROM governance.audit_log
--       WHERE timestamp >= '2024-01-01' AND timestamp < '2024-02-01';
--
--   Phase 3 (deploy + verify):
--     Switch the inference-svc + governance-svc audit-write code to
--     INSERT INTO audit_log_partitioned (additive — same column shape).
--     Verify forensics endpoint still resolves audit rows by
--     correlation_id (now reads from the partitioned table).
--
--   Phase 4 (retention cron):
--     Schedule monthly: SELECT governance.create_audit_log_partition(
--       to_char(NOW() + '1 month'::interval, 'YYYY'),
--       to_char(NOW() + '1 month'::interval, 'MM')
--     );
--     For ARCHIVAL: ALTER TABLE governance.audit_log_p_yYYYYmMM
--       DETACH PARTITION; export to S3; DROP TABLE.
--
--   Phase 5 (cleanup):
--     After retention horizon (7y for regulated): DROP TABLE
--     governance.audit_log; rename audit_log_partitioned →
--     audit_log if desired.
