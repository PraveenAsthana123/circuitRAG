-- ============================================================================
-- 006 — governance.action_drafts: enforce state machine in storage
-- ============================================================================
-- Why
-- ----
-- The replay/resolve workflow is a state machine:
--   pending -> replayed
--   pending -> rejected
-- (anything else is a bug or a security anomaly).
--
-- Up to now the lifecycle was enforced only in application code:
--   * ``MCPClient.resolve_draft`` did ``UPDATE ... WHERE draft_id=$1``
--     with no status guard (commit 2b47d4a closed that with a CAS guard).
--   * Nothing in the schema rejected ``status='garbage'``.
-- Defense-in-depth requires the database to refuse nonsense even if
-- application code regresses. That is what this migration adds.
--
-- What
-- ----
-- 1. CHECK constraint on ``status`` — only 'pending'|'replayed'|'rejected'
--    are valid. Any future status MUST land in a migration alongside the
--    code change, not silently leak through.
-- 2. Tighter consistency: replayed rows MUST have ``replayed_at`` and
--    ``replay_result``; pending rows MUST NOT.
-- 3. Optional partial index for the worker's hot path: pending drafts
--    by (tenant_id, created_at). Existing
--    ``idx_action_drafts_tenant_status`` already covers this, but a
--    partial index reduces b-tree size for the common case.
--
-- Rollback
-- --------
-- ``ALTER TABLE ... DROP CONSTRAINT`` is reversible without data loss.
-- The partial index can be DROPped without touching rows.
-- ============================================================================

-- 1. Status enum constraint.
ALTER TABLE governance.action_drafts
    ADD CONSTRAINT action_drafts_status_valid
    CHECK (status IN ('pending', 'replayed', 'rejected'));

-- 2. Lifecycle consistency: a replayed draft MUST have its replay
--    artefacts populated; a pending draft MUST NOT.
--
--    Rejected drafts are allowed to have either shape — the rejection
--    workflow today doesn't fill replay_result, but a future "operator
--    rejected with reason" feature might. Don't over-constrain that.
ALTER TABLE governance.action_drafts
    ADD CONSTRAINT action_drafts_replayed_has_artefacts
    CHECK (
        status <> 'replayed'
        OR (replayed_at IS NOT NULL AND replay_result IS NOT NULL)
    );

ALTER TABLE governance.action_drafts
    ADD CONSTRAINT action_drafts_pending_clean
    CHECK (
        status <> 'pending'
        OR (replayed_at IS NULL AND replay_result IS NULL)
    );

-- 3. Partial index on the worker's hot path. The full
--    ``idx_action_drafts_tenant_status`` covers all statuses; this one
--    skips replayed/rejected pages so the worker's
--    ``WHERE status='pending' AND tenant_id=$1`` scan stays in cache.
CREATE INDEX IF NOT EXISTS idx_action_drafts_pending_by_tenant
    ON governance.action_drafts (tenant_id, created_at)
    WHERE status = 'pending';

COMMENT ON CONSTRAINT action_drafts_status_valid ON governance.action_drafts IS
    'Storage-level state-machine guard. Adding a new status requires a '
    'migration that alters this constraint — that''s the seam where new '
    'lifecycle transitions get reviewed.';
