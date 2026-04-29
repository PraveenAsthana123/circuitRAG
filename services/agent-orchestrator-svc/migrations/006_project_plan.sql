ALTER TABLE orchestration.agent_projects
    ADD COLUMN IF NOT EXISTS planned_tasks_json JSONB NOT NULL DEFAULT '[]'::jsonb;
