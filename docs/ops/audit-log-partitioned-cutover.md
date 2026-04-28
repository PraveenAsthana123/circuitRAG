# Audit log partitioned — operations cutover runbook

Migration `009_audit_log_partitioned.sql` (commit `9fc7371`) creates
`governance.audit_log_partitioned` alongside the existing
`governance.audit_log`. The migration is **additive** — legacy table
untouched, new table populated only after operations runs the
phased cutover documented here.

This runbook is the procedure to flip the system from writing
audit rows to the unpartitioned legacy table to writing to the
partitioned table without losing data, breaking forensics, or
violating the §38 right-to-explanation contract during the
window.

## Pre-cutover verification

Before starting Phase 1, confirm:

```bash
# 1. Migration 009 applied on the target cluster.
psql -c "
  SELECT relkind FROM pg_class
  WHERE oid = 'governance.audit_log_partitioned'::regclass;
"
# Expected: 'p' (partitioned). Anything else = migration not applied.

# 2. Bootstrap partitions exist (current + next 2 months).
psql -c "
  SELECT inhrelid::regclass
  FROM pg_inherits
  WHERE inhparent = 'governance.audit_log_partitioned'::regclass
  ORDER BY 1;
"
# Expected: ≥ 3 partitions named audit_log_p_yYYYYmMM.

# 3. Retention cron is scheduled (see Phase 4).
crontab -l -u documind | grep create_audit_log_partition
# Expected: a row pre-creating month N+1 nightly. If absent,
# Phase 4 schedules it before traffic switch.

# 4. Drill 8/8 green against this cluster.
DOCUMIND_PG_DSN=postgresql://documind:documind@<host>:5432/documind \
DOCUMIND_PG_APP_DSN=postgresql://documind_app:documind_app@<host>:5432/documind \
  python mcp/tests/drill_audit_log_partitioned.py
# Expected: ALL 8 PARTITION STEPS PASSED.

# 5. Legacy audit_log row count baseline (used to verify backfill
#    didn't lose rows; record this number).
psql -c "
  SELECT count(*) AS legacy_count, min(timestamp) AS earliest, max(timestamp) AS latest
  FROM governance.audit_log;
"
# Record: <legacy_count>, <earliest>, <latest>.
```

If any of (1)–(4) fail, **do not proceed** — fix the prerequisite first.

---

## Phase 1 — Pre-create historical partitions

Backfill in Phase 2 will INSERT rows with timestamps spanning the
full retention horizon of the legacy table. Bootstrap (current +
next 2 months) only covers the going-forward window. Phase 1
pre-creates partitions for every month with legacy rows.

```sql
-- One transaction per month. The helper is idempotent
-- (CREATE TABLE IF NOT EXISTS) so re-running is safe.
DO $bootstrap_history$
DECLARE
    earliest TIMESTAMPTZ;
    latest   TIMESTAMPTZ;
    cursor_d TIMESTAMPTZ;
BEGIN
    SELECT min(timestamp), max(timestamp) INTO earliest, latest
    FROM governance.audit_log;

    cursor_d := date_trunc('month', earliest);
    WHILE cursor_d <= date_trunc('month', latest) LOOP
        PERFORM governance.create_audit_log_partition(
            to_char(cursor_d, 'YYYY'),
            to_char(cursor_d, 'MM')
        );
        cursor_d := cursor_d + INTERVAL '1 month';
    END LOOP;
END
$bootstrap_history$;

-- Verify all months covered.
SELECT count(*) AS partition_count
FROM pg_inherits
WHERE inhparent = 'governance.audit_log_partitioned'::regclass;
-- Expected: ≥ (months between earliest and latest) + 3 bootstrap.
```

**Reversible:** drop unused partitions with `DROP TABLE governance.audit_log_p_yYYYYmMM;`.

---

## Phase 2 — Backfill in batches

Insert legacy rows into the partitioned table in monthly chunks.
Per-month INSERT is fastest because the planner only touches one
partition. Run during low-traffic window — backfill takes a row
lock briefly and the legacy table stays available for reads.

```sql
-- Phase 2 — backfill one month at a time. Adjust the year/month
-- range to your audit_log span. Each statement is idempotent via
-- ON CONFLICT DO NOTHING — composite PK (id, timestamp) prevents
-- duplicate rows even if the loop is re-run.

INSERT INTO governance.audit_log_partitioned
    (id, timestamp, tenant_id, actor_id, actor_type, action,
     resource_type, resource_id, details, correlation_id,
     ip_address, user_agent, previous_hash, entry_hash)
SELECT id, timestamp, tenant_id, actor_id, actor_type, action,
       resource_type, resource_id, details, correlation_id,
       ip_address, user_agent, previous_hash, entry_hash
FROM governance.audit_log
WHERE timestamp >= '2024-01-01' AND timestamp < '2024-02-01'
ON CONFLICT (id, timestamp) DO NOTHING;

-- Verify per-month count matches.
SELECT
    (SELECT count(*) FROM governance.audit_log
     WHERE timestamp >= '2024-01-01' AND timestamp < '2024-02-01') AS legacy,
    (SELECT count(*) FROM governance.audit_log_partitioned
     WHERE timestamp >= '2024-01-01' AND timestamp < '2024-02-01') AS partitioned;
-- Expected: equal counts. If partitioned < legacy, missing rows;
-- check error log for ON CONFLICT skips (should be 0 on first run).
```

**Verification at end of Phase 2 — total row counts must match within tolerance:**

```sql
SELECT
    (SELECT count(*) FROM governance.audit_log) AS legacy,
    (SELECT count(*) FROM governance.audit_log_partitioned) AS partitioned;
-- Expected: equal. If partitioned > legacy, app already started
-- writing to both — check Phase 3 wasn't started prematurely.
-- If partitioned < legacy, re-run the missing months' backfill.
```

**Reversible:** `TRUNCATE governance.audit_log_partitioned;` and re-run.

---

## Phase 3 — App-write switchover (deploy + verify)

The audit-write code in `services/inference-svc/app/routers/__init__.py`
and `services/governance-svc` writes to `governance.audit_log` today.
Switch the INSERT target to `governance.audit_log_partitioned` and
re-deploy.

Search for INSERT call sites (typically 2–4 across services):

```bash
grep -rn "INSERT INTO governance.audit_log\b" services/ --include="*.py" --include="*.go"
```

Update each call site (PR can be a single small diff per service).
The schema is identical; the only change is the table name.

**Deploy with canary** (per `/admin/rollout/deep` + `/admin/post-release/deep`):

1. Deploy to canary (10% traffic, 5 min observation).
2. Verify both tables receiving writes during the window:
   ```sql
   -- Last 5 min of writes per table.
   SELECT 'legacy' AS tbl, count(*) FROM governance.audit_log
       WHERE timestamp > now() - INTERVAL '5 minutes'
   UNION ALL
   SELECT 'partitioned', count(*) FROM governance.audit_log_partitioned
       WHERE timestamp > now() - INTERVAL '5 minutes';
   -- Expected: legacy mostly (90% non-canary), partitioned has new rows
   -- at ~10% of overall write rate.
   ```
3. Verify forensics endpoint still resolves audit rows:
   ```bash
   # Pick a canary-tagged correlation_id.
   curl "http://<inference>/api/v1/admin/trace/$CID?tenant_id=$TID"
   # Expected: audit_rows[] populated (from partitioned table after
   # the switchover takes effect on this hop).
   ```
4. Promote to 100% if (1)–(3) green for 5 min.
5. After full rollout, the legacy table stops receiving new rows.

**Rollback:** revert the deploy. New writes go back to the legacy table; partitioned table stops receiving but keeps the rows it has (no data loss).

---

## Phase 4 — Schedule retention cron

Pre-create next month's partition before the boundary so writes after
midnight on the 1st of the month don't fail with "no partition for row".

```cron
# /etc/cron.d/audit-log-partition or equivalent
# Pre-create N+1 month partition every night at 03:00 UTC.
0 3 * * * documind psql -c "SELECT governance.create_audit_log_partition(\
    to_char(NOW() + INTERVAL '1 month', 'YYYY'),\
    to_char(NOW() + INTERVAL '1 month', 'MM')\
);"
```

For archival of partitions older than retention horizon (7y for
regulated, 1y default):

```sql
-- DETACH the old partition (no data movement, near-instant).
ALTER TABLE governance.audit_log_partitioned
DETACH PARTITION governance.audit_log_p_y2018m01;

-- Export to S3 / cold storage via pg_dump or COPY ... TO program.
-- Example (run as postgres OS user):
COPY governance.audit_log_p_y2018m01
TO PROGRAM 'aws s3 cp - s3://documind-audit-archive/audit-log/y2018m01.csv.gz --sse AES256 --content-encoding gzip'
WITH (FORMAT csv, HEADER, COMPRESSION gzip);

-- Verify upload landed.
aws s3 ls s3://documind-audit-archive/audit-log/y2018m01.csv.gz

-- Drop the now-archived partition.
DROP TABLE governance.audit_log_p_y2018m01;
```

**Reversible** until the DROP. After the DROP, restore from S3 by
reading the CSV back and re-attaching:

```sql
-- Re-create + ATTACH a partition for the archived range.
SELECT governance.create_audit_log_partition('2018', '01');
COPY governance.audit_log_p_y2018m01 FROM PROGRAM
    'aws s3 cp s3://documind-audit-archive/audit-log/y2018m01.csv.gz - | gunzip'
WITH (FORMAT csv, HEADER);
```

---

## Phase 5 — Cleanup

After Phase 3 has been stable for a defined cooling-off window
(default 30 days, regulatory minimum 6 months — defer to compliance):

```sql
-- Verify no writes to legacy table for the cooling-off window.
SELECT max(timestamp) AS last_legacy_write
FROM governance.audit_log;
-- Expected: timestamp older than 30 days (or your cooling-off).

-- Final backfill — catch any stragglers between Phase 2's last
-- run and Phase 3's switchover. Same SQL as Phase 2 but bounded
-- to the gap.
INSERT INTO governance.audit_log_partitioned (...)
SELECT ... FROM governance.audit_log
WHERE timestamp > '<phase-2-cutoff>' AND timestamp < '<phase-3-cutoff>'
ON CONFLICT (id, timestamp) DO NOTHING;

-- Final row-count check.
SELECT
    (SELECT count(*) FROM governance.audit_log) AS legacy_total,
    (SELECT count(*) FROM governance.audit_log_partitioned
     WHERE timestamp <= '<phase-3-cutoff>') AS partitioned_pre_switchover;
-- Expected: equal.

-- DROP the legacy table.
DROP TABLE governance.audit_log;

-- Optionally rename the partitioned table to take the legacy name.
-- This is cosmetic — call sites already updated in Phase 3.
ALTER TABLE governance.audit_log_partitioned RENAME TO audit_log;
-- Update each partition's name too if desired:
-- ALTER TABLE governance.audit_log_p_y2024m01 RENAME TO ...
```

**Reversible** until DROP TABLE — after the DROP, the legacy table
is gone forever (point-in-time recovery from backup is the only
restore path).

---

## Sign-off (per release)

The cutover is complete when **all** of the following are signed:

- [ ] Phase 1 — pre-cutover verification all green (5 commands above)
- [ ] Phase 2 — total row counts match after backfill (off-hours)
- [ ] Phase 3 — canary + 100% promotion both green; forensics endpoint resolves
- [ ] Phase 4 — retention cron scheduled + archival procedure tested in staging
- [ ] Phase 5 — cooling-off elapsed; legacy table dropped (or scheduled to drop)
- [ ] On-call lead, compliance, tech lead — pair sign-off on Phase 5

After Phase 5 sign-off, the operations runbook for the partitioned
schema is the canonical procedure. Update `~/.claude/policies/ai-explainability.md`
§4 if retention horizons changed during the cutover.

---

## References

- Migration: `services/governance-svc/migrations/009_audit_log_partitioned.sql`
- Drill: `mcp/tests/drill_audit_log_partitioned.py` (8 steps including 3 negative assertions)
- Deep-dive: `/admin/explainability/deep#audit-rag-contract-regulation`
- Architecture: `/admin/rollout/deep#rollback-strategy` (4-layer rollback applied to DB)
- Policy: `~/.claude/policies/ai-explainability.md` §4 retention requirements
- CI: `docs/ci-drills-setup.md` — drills-pg tier exercises this migration on every PR
