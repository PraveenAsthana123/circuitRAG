-- Append-only record of audit chain breaks detected by audit_verify --seal.
-- Forensic evidence of tampering that persists even after the tampered
-- rows in governance.audit_log are restored/removed.
--
-- Not hash-chained itself — that's intentional. These rows are
-- meta-evidence; their integrity is protected by:
--   * append-only grant (no UPDATE, no DELETE for app role)
--   * INSERT-by-role limited to documind_ops (governance tool only)
--   * SELECT bound to tenant_id via RLS so a tenant sees only their
--     own breaks; governance role sees cross-tenant.
--
-- If you want per-tenant chain integrity on THIS table, add it in a
-- future migration — for now, the governance tool's audit trail +
-- Postgres's own WAL are the protections.

CREATE TABLE IF NOT EXISTS governance.audit_log_breaks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id       UUID NOT NULL,
    broken_row_id   UUID,                            -- pointer into audit_log.id
    broken_action   TEXT,                            -- the action field of the broken row
    break_type      TEXT NOT NULL,                   -- BROKEN_HASH | BROKEN_CHAIN | MISSING_HASH
    expected_hash   TEXT,                            -- what verifier computed
    stored_hash     TEXT,                            -- what the row claimed
    detail          TEXT,                            -- free-text diagnostic
    verifier_host   TEXT,                            -- which host ran the verify
    verifier_run_id UUID NOT NULL,                   -- groups breaks found in one verify run
    tenant_id_audit UUID                             -- if the row is from another tenant's chain (shouldn't happen but documented)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_breaks_tenant_time
    ON governance.audit_log_breaks (tenant_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_breaks_run
    ON governance.audit_log_breaks (verifier_run_id);

ALTER TABLE governance.audit_log_breaks ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.audit_log_breaks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON governance.audit_log_breaks;
CREATE POLICY tenant_isolation ON governance.audit_log_breaks
    USING (
        tenant_id IS NULL
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
    );
