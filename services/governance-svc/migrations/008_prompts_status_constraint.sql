-- ============================================================================
-- 008 — governance.prompts: enforce status state machine in storage
-- ============================================================================
-- Why
-- ----
-- ``governance.prompts`` holds the active prompt registry. The ``status``
-- column controls which rows ``DbBackedPromptBuilder.list_active``
-- surfaces, but the column had no CHECK constraint — any string was
-- accepted. A typo in a migration or operator INSERT could write
-- ``status='actve'`` (silent typo) and the prompt would never appear
-- in the active set. No alert; the wrong prompt would silently keep
-- serving traffic.
--
-- This is the same defence-in-depth pattern as migration 006
-- (action_drafts) and 007 (mcp_idempotency): the storage layer rejects
-- nonsense values regardless of what application code does.
--
-- Allowed states (smallest workable set; expand via migration when a
-- new lifecycle state is justified, NOT by silently allowing it):
--   draft       — author wrote it; not in production
--   active      — currently serving traffic
--   archived    — used to be active; kept for audit + historical replay
--   deprecated  — phased out; will not return on list_active
-- ============================================================================

ALTER TABLE governance.prompts
    ADD CONSTRAINT prompts_status_valid
    CHECK (status IN ('draft', 'active', 'archived', 'deprecated'));

COMMENT ON CONSTRAINT prompts_status_valid ON governance.prompts IS
    'Storage-level state-machine guard for the prompt registry. Adding '
    'a new status requires a migration that ALTERs this constraint — '
    'that is the seam where lifecycle changes get reviewed.';
