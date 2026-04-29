CREATE SCHEMA IF NOT EXISTS orchestration;

CREATE TABLE IF NOT EXISTS orchestration.agent_tasks (
  task_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  goal TEXT NOT NULL,
  status TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  require_human_approval BOOLEAN NOT NULL DEFAULT FALSE,
  approved BOOLEAN NULL,
  confidence DOUBLE PRECISION NULL,
  tool_namespace TEXT NULL,
  tool_name TEXT NULL,
  tool_arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
  plan_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  worker_output TEXT NULL,
  reviewer_notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  advisor_summary TEXT NULL,
  next_action TEXT NULL,
  audit_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_tenant_status
  ON orchestration.agent_tasks (tenant_id, status, updated_at DESC);

ALTER TABLE orchestration.agent_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.agent_tasks FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_tasks_tenant_isolation ON orchestration.agent_tasks;
CREATE POLICY agent_tasks_tenant_isolation
  ON orchestration.agent_tasks
  USING (tenant_id = current_setting('app.current_tenant', true));
