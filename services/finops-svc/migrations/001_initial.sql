-- finops schema (Design Area 29)
CREATE TABLE IF NOT EXISTS finops.token_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    correlation_id  UUID,
    model           TEXT NOT NULL,
    prompt_tokens   INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    shadow_cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_time ON finops.token_usage (tenant_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS finops.budgets (
    tenant_id           UUID PRIMARY KEY,
    daily_tokens        BIGINT NOT NULL DEFAULT 100000,
    monthly_tokens      BIGINT NOT NULL DEFAULT 2000000,
    alert_at_percent    INTEGER[] NOT NULL DEFAULT '{50, 80, 100}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS finops.billing_periods (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    total_tokens    BIGINT NOT NULL,
    total_cost_usd  NUMERIC(10,2) NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
