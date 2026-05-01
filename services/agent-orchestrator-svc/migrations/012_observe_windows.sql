-- 012_observe_windows.sql
-- Phase B6: observer soak windows.
--
-- After deployer applies (B5), service.py opens an observe_window;
-- a background sweep checks Prom/Loki at soak_ends_at and either
-- finalises (healthy) or invokes mcp_deploy.rollback(rollback_handle).

CREATE TABLE IF NOT EXISTS orchestration.observe_windows (
  window_id          TEXT PRIMARY KEY,
  task_id            TEXT NOT NULL REFERENCES orchestration.agent_tasks(task_id) ON DELETE CASCADE,
  deploy_id          TEXT NOT NULL,
  tenant_id          TEXT NOT NULL,
  soak_started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  soak_ends_at       TIMESTAMPTZ NOT NULL,
  alerts_seen_json   JSONB NOT NULL DEFAULT '[]'::jsonb,
  p95_baseline_ms    INTEGER NULL,
  p95_observed_ms    INTEGER NULL,
  status             TEXT NOT NULL DEFAULT 'pending',  -- pending|healthy|degraded|rolled_back
  routing_decision   JSONB NULL,
  notes              TEXT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_observe_windows_pending
  ON orchestration.observe_windows (status, soak_ends_at)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_observe_windows_task
  ON orchestration.observe_windows (task_id, created_at DESC);

ALTER TABLE orchestration.observe_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.observe_windows FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS observe_windows_isolation ON orchestration.observe_windows;
CREATE POLICY observe_windows_isolation
  ON orchestration.observe_windows
  USING (tenant_id = current_setting('app.current_tenant', true));

COMMENT ON TABLE orchestration.observe_windows IS
  'Post-deploy soak windows. Background sweep transitions pending → '
  'healthy | degraded | rolled_back when soak_ends_at elapses.';
