-- 010_test_results.sql
-- Phase B4: test results from TesterAgent.
--
-- TesterAgent invokes mcp_tests.run_pytest / run_jest / run_ruff /
-- run_mypy and persists structured outcomes here. The B3 review-loop
-- already retries when reviewer is unconvinced; B4 adds a parallel
-- retry condition: failing tests trigger another worker pass (max 3).

CREATE TABLE IF NOT EXISTS orchestration.test_results (
  result_id     TEXT PRIMARY KEY,
  task_id       TEXT NOT NULL REFERENCES orchestration.agent_tasks(task_id) ON DELETE CASCADE,
  tenant_id     TEXT NOT NULL,
  runner        TEXT NOT NULL,  -- 'pytest' | 'jest' | 'ruff' | 'mypy'
  passed        BOOLEAN NOT NULL,
  failed_json   JSONB NOT NULL DEFAULT '[]'::jsonb,
  coverage_pct  DOUBLE PRECISION NULL,
  log_tail      TEXT NULL,
  routing_decision JSONB NULL,
  retry_count   INTEGER NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_results_task
  ON orchestration.test_results (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_test_results_tenant_passed
  ON orchestration.test_results (tenant_id, passed, created_at DESC);

ALTER TABLE orchestration.test_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.test_results FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS test_results_isolation ON orchestration.test_results;
CREATE POLICY test_results_isolation
  ON orchestration.test_results
  USING (tenant_id = current_setting('app.current_tenant', true));

COMMENT ON TABLE orchestration.test_results IS
  'Structured test runner outputs from TesterAgent / mcp_tests. '
  'failed_json is a list of {test_name, error, file, line}.';
