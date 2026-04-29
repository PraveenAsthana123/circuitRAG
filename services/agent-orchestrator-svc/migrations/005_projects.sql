CREATE TABLE IF NOT EXISTS orchestration.agent_projects (
  project_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  name TEXT NOT NULL,
  goal TEXT NOT NULL,
  status TEXT NOT NULL,
  use_global_policy BOOLEAN NOT NULL DEFAULT TRUE,
  task_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  policy_override_json JSONB NULL,
  audit_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_projects_tenant_status
  ON orchestration.agent_projects (tenant_id, status, updated_at DESC);

ALTER TABLE orchestration.agent_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.agent_projects FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_projects_tenant_isolation ON orchestration.agent_projects;
CREATE POLICY agent_projects_tenant_isolation
  ON orchestration.agent_projects
  USING (tenant_id = current_setting('app.current_tenant', true));

ALTER TABLE orchestration.agent_tasks
  ADD COLUMN IF NOT EXISTS project_id TEXT NULL;
