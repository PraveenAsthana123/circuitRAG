ALTER TABLE orchestration.agent_tasks
    ADD COLUMN IF NOT EXISTS approval_mode TEXT NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS auto_advance BOOLEAN NOT NULL DEFAULT TRUE;
