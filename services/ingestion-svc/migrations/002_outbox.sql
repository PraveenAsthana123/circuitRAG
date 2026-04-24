-- ============================================================================
-- Outbox pattern (Design Area 17 — Event-Driven Design)
-- ============================================================================
-- A saga step writes to its domain table AND inserts an outbox row in the
-- SAME transaction. A separate worker drains the outbox to Kafka. This
-- closes the "write to DB, crash, never publish" hole.
-- ============================================================================

CREATE TABLE IF NOT EXISTS ingestion.outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    topic           TEXT NOT NULL,
    event_id        UUID NOT NULL UNIQUE,   -- stable across retries
    event_type      TEXT NOT NULL,
    subject         TEXT,                   -- optional: document_id, etc.
    correlation_id  UUID,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT
);

-- Drain index: pull unpublished rows oldest-first.
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON ingestion.outbox (created_at)
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_outbox_tenant
    ON ingestion.outbox (tenant_id, created_at DESC);

-- Retention: published rows cleaned up after 7 days by a cron.
COMMENT ON TABLE ingestion.outbox
    IS 'Transactional outbox — events drained to Kafka by a worker.
       Cleanup: DELETE WHERE published_at < NOW() - INTERVAL ''7 days''.';
