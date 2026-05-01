-- 015_rls_audit.sql
-- Phase C3: codify the tenant-isolation audit performed by
-- mcp/tests/drill_tenant_isolation.py.
--
-- This migration is a NO-OP at the data layer (no DDL changes).
-- Its purpose is to land an explicit, version-controlled record
-- of which tables are intentionally GLOBAL (no tenant scope) and
-- which are TENANT-SCOPED (RLS-enforced).
--
-- The drill reads this file's TENANT_SCOPED / GLOBAL_TABLES section
-- to verify the live migration set matches the documented inventory.
-- Adding a new tenant-scoped table without updating this list
-- (or its RLS policy) → drill rejects → catch the leak before merge.

-- TENANT_SCOPED (every row carries tenant_id; RLS forced):
--   orchestration.agent_tasks                     [001]
--   orchestration.agent_projects                  [005]
--   orchestration.agent_project_plan_items        [007]
--   orchestration.agent_task_runs                 [007]
--   orchestration.agent_approvals                 [007]
--   orchestration.agent_memories                  [007]
--   orchestration.research_artifacts              [009]
--   orchestration.test_results                    [010]
--   orchestration.deploy_records                  [011]
--   orchestration.observe_windows                 [012]
--   orchestration.tenant_budgets                  [013]
--   orchestration.idempotency_keys                [014]
--
-- GLOBAL_TABLES (intentionally cross-tenant; no tenant_id column;
-- access controlled at API layer, not by RLS):
--   orchestration.agent_policies                  [003] — global
--     default approval policy applied when no per-tenant override.

DO $$
BEGIN
    -- Belt-and-suspenders: if any of the tenant-scoped tables exist
    -- but lack RLS, this DO block fails loudly. Operators see the
    -- mismatch at migrate time, not at first cross-tenant query.
    PERFORM 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'orchestration'
      AND c.relname IN (
        'agent_tasks', 'agent_projects', 'agent_project_plan_items',
        'agent_task_runs', 'agent_approvals', 'agent_memories',
        'research_artifacts', 'test_results', 'deploy_records',
        'observe_windows', 'tenant_budgets', 'idempotency_keys'
      )
      AND c.relrowsecurity = false;
    IF FOUND THEN
        RAISE EXCEPTION 'C3: tenant-scoped table without ROW LEVEL SECURITY';
    END IF;
END $$;

COMMENT ON SCHEMA orchestration IS
  'Agent orchestrator data plane. Tenant-scoped tables enforce RLS '
  'via current_setting(''app.current_tenant''). agent_policies is '
  'intentionally global (no tenant_id). See migrations/015_rls_audit.sql.';
