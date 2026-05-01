-- 013_tenant_budgets.sql
-- Phase C1: per-tenant daily Tier-B budget cap.
--
-- Cost guard for §41.1. Service.py reads budget at task start, passes
-- budget_remaining_cents into model_router.route(); router downgrades
-- Tier-B routing decisions when budget exhausted, with audit reason
-- 'R*_budget_exhausted_fallback'.
--
-- Backward compat (per §28.2):
--   * Table empty by default — service treats absence as 'no cap'
--     (effectively unlimited, preserves pre-C1 behavior).
--   * Operators add rows per-tenant to opt in to budgeting.
--
-- Reset semantics: used_today_cents reset to 0 by a scheduled task
-- (or service startup). reset_at tracks when the rolling window started.

CREATE TABLE IF NOT EXISTS orchestration.tenant_budgets (
  tenant_id          TEXT PRIMARY KEY,
  daily_cap_cents    INTEGER NOT NULL DEFAULT 1000,  -- $10/day default
  used_today_cents   INTEGER NOT NULL DEFAULT 0,
  reset_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notes              TEXT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT tenant_budgets_cap_nonneg CHECK (daily_cap_cents >= 0),
  CONSTRAINT tenant_budgets_used_nonneg CHECK (used_today_cents >= 0)
);

CREATE INDEX IF NOT EXISTS idx_tenant_budgets_reset
  ON orchestration.tenant_budgets (reset_at);

-- Tenants reading their OWN budget row only.
ALTER TABLE orchestration.tenant_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.tenant_budgets FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_budgets_isolation ON orchestration.tenant_budgets;
CREATE POLICY tenant_budgets_isolation
  ON orchestration.tenant_budgets
  USING (tenant_id = current_setting('app.current_tenant', true));

COMMENT ON TABLE orchestration.tenant_budgets IS
  'Per-tenant daily Tier-B (cloud LLM) cost cap. Read by model_router '
  'before Tier-B selection; exhausted → downgrade to Tier-A fallback.';
COMMENT ON COLUMN orchestration.tenant_budgets.daily_cap_cents IS
  'Maximum Tier-B spend per day in USD cents. 0 = no Tier-B allowed.';
COMMENT ON COLUMN orchestration.tenant_budgets.used_today_cents IS
  'Running tally for the current rolling-day window.';
COMMENT ON COLUMN orchestration.tenant_budgets.reset_at IS
  'Window start timestamp; service resets tally when (now - reset_at) > 24h.';
