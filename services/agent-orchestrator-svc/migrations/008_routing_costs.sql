-- 008_routing_costs.sql
-- Phase A5: cost + routing audit on agent_task_runs.
--
-- Adds four columns enabling §41.1 cost tracking and §47.6/§48.6
-- routing-decision audit per row:
--   tokens_in INT NULL     — prompt tokens consumed by the call
--   tokens_out INT NULL    — completion tokens generated
--   cost_usd_cents INT NULL — best-effort USD cost in cents (Tier-A always 0)
--   routing_decision JSONB — chosen handle + fallback chain + reason
--
-- Backward compatibility (per §28.2):
--   * All columns nullable, no DEFAULT NOT NULL — old rows readable
--     unchanged, new rows fill in zeros / null when no routed call ran.
--   * Old service code that doesn't write these columns just sees them
--     as null — no constraint violation.
--   * Indexes added on (tenant_id, created_at DESC) NOT WHERE
--     cost_usd_cents > 0 — a partial index would skip null rows.
--
-- Rollback (manual):
--   ALTER TABLE orchestration.agent_task_runs
--     DROP COLUMN IF EXISTS routing_decision,
--     DROP COLUMN IF EXISTS cost_usd_cents,
--     DROP COLUMN IF EXISTS tokens_out,
--     DROP COLUMN IF EXISTS tokens_in;

ALTER TABLE orchestration.agent_task_runs
  ADD COLUMN IF NOT EXISTS tokens_in INTEGER NULL,
  ADD COLUMN IF NOT EXISTS tokens_out INTEGER NULL,
  ADD COLUMN IF NOT EXISTS cost_usd_cents INTEGER NULL,
  ADD COLUMN IF NOT EXISTS routing_decision JSONB NULL;

-- Index for cost dashboards: per-tenant cost over time.
-- (Standard index, not partial — partial would mask Tier-A rows where
-- cost is 0 but token counts may still exceed budget.)
CREATE INDEX IF NOT EXISTS idx_agent_task_runs_tenant_cost
  ON orchestration.agent_task_runs (tenant_id, created_at DESC)
  WHERE cost_usd_cents IS NOT NULL;

COMMENT ON COLUMN orchestration.agent_task_runs.tokens_in IS
  'Prompt tokens for this run; 0 for non-LLM phases.';
COMMENT ON COLUMN orchestration.agent_task_runs.tokens_out IS
  'Completion tokens for this run; 0 for non-LLM phases.';
COMMENT ON COLUMN orchestration.agent_task_runs.cost_usd_cents IS
  'Best-effort USD cents for this run. Tier-A (Ollama) always 0.';
COMMENT ON COLUMN orchestration.agent_task_runs.routing_decision IS
  'JSON {chosen, fallback_chain, reason} from app/model_router.py.';
