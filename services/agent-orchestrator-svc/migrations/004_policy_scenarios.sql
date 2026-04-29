ALTER TABLE orchestration.agent_tasks
    ADD COLUMN IF NOT EXISTS approval_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE orchestration.agent_policies
    ADD COLUMN IF NOT EXISTS require_for_high_risk BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS require_for_low_confidence BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS confidence_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.8,
    ADD COLUMN IF NOT EXISTS require_for_risk_flags BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS require_for_destructive_tools BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS require_for_tool_namespaces JSONB NOT NULL DEFAULT '["identity","finops","itsm"]'::jsonb;
