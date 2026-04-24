-- observability schema (Design Areas 28, 64)
CREATE TABLE IF NOT EXISTS observability.slo_targets (
    name             TEXT PRIMARY KEY,
    sli              TEXT NOT NULL,
    target_percent   NUMERIC(5,2) NOT NULL,
    window_days      INTEGER NOT NULL,
    error_budget_pct NUMERIC(5,2),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO observability.slo_targets (name, sli, target_percent, window_days)
VALUES
    ('availability', 'successful_requests / total_requests', 99.5, 30),
    ('query_latency_p95', 'p95(query_duration_ms)', 3000, 30),
    ('retrieval_precision_at_5', 'eval_precision_at_5', 80, 7),
    ('answer_faithfulness', 'eval_faithfulness', 90, 7)
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS observability.alert_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    metric      TEXT NOT NULL,
    operator    TEXT NOT NULL,    -- gt | lt | eq
    threshold   NUMERIC NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'warning',
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    channels    TEXT[] NOT NULL DEFAULT '{"log"}'
);

CREATE TABLE IF NOT EXISTS observability.incident_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id     UUID REFERENCES observability.alert_rules(id),
    opened_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    severity     TEXT NOT NULL,
    summary      TEXT NOT NULL,
    details      JSONB NOT NULL DEFAULT '{}'
);
