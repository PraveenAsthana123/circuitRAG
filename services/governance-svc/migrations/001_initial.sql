-- governance schema (Design Areas 27, 55, 56, 57, 63)
CREATE TABLE IF NOT EXISTS governance.policies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID,               -- NULL = global
    name        TEXT NOT NULL,
    condition   TEXT NOT NULL,      -- CEL expression
    action      TEXT NOT NULL,      -- flag | block | log | notify
    severity    TEXT NOT NULL DEFAULT 'medium',
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    version     INTEGER NOT NULL DEFAULT 1,
    created_by  UUID,
    approved_by UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policies_tenant_enabled ON governance.policies (tenant_id, enabled);

CREATE TABLE IF NOT EXISTS governance.feature_flags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    scope           TEXT NOT NULL,       -- global | tenant | user | percentage
    default_value   BOOLEAN NOT NULL DEFAULT FALSE,
    percentage      INTEGER DEFAULT 0,
    allowed_tenants UUID[] NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'draft',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS governance.hitl_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    correlation_id  UUID NOT NULL,
    question        TEXT NOT NULL,
    retrieved_chunks JSONB NOT NULL,
    generated_answer TEXT NOT NULL,
    confidence      NUMERIC(4,3),
    flag_reason     TEXT,
    review_status   TEXT NOT NULL DEFAULT 'pending',
    reviewer_id     UUID,
    review_notes    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hitl_tenant_status ON governance.hitl_queue (tenant_id, review_status, created_at DESC);

CREATE TABLE IF NOT EXISTS governance.audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id       UUID NOT NULL,
    actor_id        UUID,
    actor_type      VARCHAR(20) NOT NULL,
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     UUID,
    details         JSONB NOT NULL DEFAULT '{}',
    correlation_id  UUID,
    ip_address      INET,
    user_agent      TEXT,
    previous_hash   TEXT,
    entry_hash      TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON governance.audit_log (tenant_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS governance.prompts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    version      TEXT NOT NULL,
    template     TEXT NOT NULL,
    variables    TEXT[] NOT NULL DEFAULT '{}',
    model        TEXT,
    temperature  NUMERIC(3,2),
    max_tokens   INTEGER,
    status       TEXT NOT NULL DEFAULT 'draft',
    created_by   UUID,
    approved_by  UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, version)
);
