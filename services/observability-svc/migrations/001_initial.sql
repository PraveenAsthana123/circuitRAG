-- observability schema (Design Areas 28, 64)
-- target_value is deliberately wider than NUMERIC(5,2) — it holds both
-- percentages (99.5) AND latency thresholds in milliseconds (3000).
-- kind disambiguates ('percent' | 'latency_ms' | 'count'), so dashboards
-- can format correctly.
CREATE TABLE IF NOT EXISTS observability.slo_targets (
    name             TEXT PRIMARY KEY,
    sli              TEXT NOT NULL,
    target_value     NUMERIC(10,3) NOT NULL,
    kind             TEXT NOT NULL DEFAULT 'percent',
    window_days      INTEGER NOT NULL,
    error_budget_pct NUMERIC(5,2),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO observability.slo_targets (name, sli, target_value, kind, window_days)
VALUES
    ('availability', 'successful_requests / total_requests', 99.5, 'percent', 30),
    ('query_latency_p95', 'p95(query_duration_ms)', 3000, 'latency_ms', 30),
    ('retrieval_precision_at_5', 'eval_precision_at_5', 80, 'percent', 7),
    ('answer_faithfulness', 'eval_faithfulness', 90, 'percent', 7)
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
