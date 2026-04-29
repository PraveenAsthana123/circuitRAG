CREATE TABLE IF NOT EXISTS orchestration.agent_policies (
  policy_key TEXT PRIMARY KEY,
  require_human_approval BOOLEAN NOT NULL DEFAULT FALSE,
  approval_mode TEXT NOT NULL DEFAULT 'plan_once',
  auto_advance BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by TEXT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO orchestration.agent_policies
    (policy_key, require_human_approval, approval_mode, auto_advance)
VALUES
    ('global', FALSE, 'plan_once', TRUE)
ON CONFLICT (policy_key) DO NOTHING;
