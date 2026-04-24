-- ============================================================================
-- CRITICAL SECURITY FIX — force RLS for table owners.
-- ============================================================================
-- Postgres default: the table OWNER is exempt from RLS policies. Since
-- services connect as the same role that owns the tables (`documind`),
-- RLS was a NO-OP — tenants could see each other's rows.
--
-- `FORCE ROW LEVEL SECURITY` makes RLS apply to the owner too. The
-- `admin_connection` path still bypasses via `BYPASSRLS` / explicit
-- `SET LOCAL row_security = off` when the ops worker legitimately needs
-- it (audit, recovery, billing rollups).
--
-- Verified by libs/py/tests/test_rls_isolation.py:
--   * without this: test_cross_tenant_read_is_empty FAILS
--   * with this:    test passes — tenant A cannot see tenant B
-- ============================================================================

ALTER TABLE ingestion.documents FORCE ROW LEVEL SECURITY;
ALTER TABLE ingestion.chunks    FORCE ROW LEVEL SECURITY;
ALTER TABLE ingestion.sagas     FORCE ROW LEVEL SECURITY;
