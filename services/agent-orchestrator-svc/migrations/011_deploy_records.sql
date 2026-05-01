-- 011_deploy_records.sql
-- Phase B5: deploy records from DeployerAgent.
--
-- §42 HARD STOP: every deploy requires human approval. The deployer
-- never auto-applies; service.py gates POST /api/v1/agentic/tasks/{id}/deploy
-- behind an explicit ApprovalRequest with decision=approve.
-- rollback_handle is what the Observer (B6) uses for auto-rollback
-- when soak metrics breach thresholds.

CREATE TABLE IF NOT EXISTS orchestration.deploy_records (
  deploy_id        TEXT PRIMARY KEY,
  task_id          TEXT NOT NULL REFERENCES orchestration.agent_tasks(task_id) ON DELETE CASCADE,
  tenant_id        TEXT NOT NULL,
  target           TEXT NOT NULL,            -- 'docker-compose' | 'k8s' | 'helm'
  rollback_handle  TEXT NULL,                -- runtime ID for rollback call
  status           TEXT NOT NULL,            -- 'pending'|'applied'|'rolled_back'|'failed'
  approval_id      TEXT NULL,                -- FK-soft to agent_approvals
  routing_decision JSONB NULL,
  log_tail         TEXT NULL,
  deployed_at      TIMESTAMPTZ NULL,
  rolled_back_at   TIMESTAMPTZ NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deploy_records_task
  ON orchestration.deploy_records (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_deploy_records_tenant_status
  ON orchestration.deploy_records (tenant_id, status, created_at DESC);

ALTER TABLE orchestration.deploy_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.deploy_records FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS deploy_records_isolation ON orchestration.deploy_records;
CREATE POLICY deploy_records_isolation
  ON orchestration.deploy_records
  USING (tenant_id = current_setting('app.current_tenant', true));

COMMENT ON TABLE orchestration.deploy_records IS
  '§42-gated deploy events. Never INSERTed without an approval_id.';
