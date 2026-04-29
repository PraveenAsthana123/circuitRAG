ALTER TABLE orchestration.agent_projects
    ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';

ALTER TABLE orchestration.agent_tasks
    ADD COLUMN IF NOT EXISTS plan_item_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS scope_paths_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS acceptance_checks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS rollback_notes TEXT NULL,
    ADD COLUMN IF NOT EXISTS worker_risks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS reviewer_risks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS advisor_risks_json JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS orchestration.agent_project_plan_items (
  plan_item_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL REFERENCES orchestration.agent_projects(project_id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  objective TEXT NOT NULL,
  status TEXT NOT NULL,
  risk_level TEXT NOT NULL DEFAULT 'LOW',
  owner_role TEXT NOT NULL DEFAULT 'manager',
  depends_on_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  acceptance_checks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  scope_paths_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  task_id TEXT NULL REFERENCES orchestration.agent_tasks(task_id) ON DELETE SET NULL,
  sort_index INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_project_plan_items_project_sort
  ON orchestration.agent_project_plan_items (project_id, sort_index, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_project_plan_items_tenant_status
  ON orchestration.agent_project_plan_items (tenant_id, status, updated_at DESC);

ALTER TABLE orchestration.agent_project_plan_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.agent_project_plan_items FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_project_plan_items_tenant_isolation ON orchestration.agent_project_plan_items;
CREATE POLICY agent_project_plan_items_tenant_isolation
  ON orchestration.agent_project_plan_items
  USING (tenant_id = current_setting('app.current_tenant', true));

CREATE TABLE IF NOT EXISTS orchestration.agent_task_runs (
  run_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  task_id TEXT NOT NULL REFERENCES orchestration.agent_tasks(task_id) ON DELETE CASCADE,
  project_id TEXT NULL REFERENCES orchestration.agent_projects(project_id) ON DELETE SET NULL,
  phase TEXT NOT NULL,
  status TEXT NOT NULL,
  model_map_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  inputs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  outputs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence DOUBLE PRECISION NULL,
  risk_level TEXT NULL,
  duration_ms INTEGER NULL,
  error_text TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_task_runs_task_created
  ON orchestration.agent_task_runs (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_task_runs_tenant_created
  ON orchestration.agent_task_runs (tenant_id, created_at DESC);

ALTER TABLE orchestration.agent_task_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.agent_task_runs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_task_runs_tenant_isolation ON orchestration.agent_task_runs;
CREATE POLICY agent_task_runs_tenant_isolation
  ON orchestration.agent_task_runs
  USING (tenant_id = current_setting('app.current_tenant', true));

CREATE TABLE IF NOT EXISTS orchestration.agent_approvals (
  approval_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  task_id TEXT NOT NULL REFERENCES orchestration.agent_tasks(task_id) ON DELETE CASCADE,
  project_id TEXT NULL REFERENCES orchestration.agent_projects(project_id) ON DELETE SET NULL,
  actor_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_approvals_task_created
  ON orchestration.agent_approvals (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_approvals_tenant_created
  ON orchestration.agent_approvals (tenant_id, created_at DESC);

ALTER TABLE orchestration.agent_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.agent_approvals FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_approvals_tenant_isolation ON orchestration.agent_approvals;
CREATE POLICY agent_approvals_tenant_isolation
  ON orchestration.agent_approvals
  USING (tenant_id = current_setting('app.current_tenant', true));

CREATE TABLE IF NOT EXISTS orchestration.agent_memories (
  memory_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  memory_kind TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_scope_created
  ON orchestration.agent_memories (scope_type, scope_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_memories_tenant_kind
  ON orchestration.agent_memories (tenant_id, memory_kind, created_at DESC);

ALTER TABLE orchestration.agent_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.agent_memories FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_memories_tenant_isolation ON orchestration.agent_memories;
CREATE POLICY agent_memories_tenant_isolation
  ON orchestration.agent_memories
  USING (tenant_id = current_setting('app.current_tenant', true));
