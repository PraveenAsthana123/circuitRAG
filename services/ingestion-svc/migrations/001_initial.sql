-- ============================================================================
-- ingestion schema — initial tables
-- ============================================================================
-- Design Areas 9 (State), 5 (Tenant RLS), 46 (DB), 18 (Saga), 20 (Idempotency)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- documents — one row per uploaded file; state-machine drives processing.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion.documents (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL,
    filename           TEXT NOT NULL,
    mime_type          TEXT NOT NULL,
    size_bytes         BIGINT NOT NULL,
    checksum_sha256    TEXT NOT NULL,
    blob_uri           TEXT NOT NULL,
    title              TEXT,
    page_count         INTEGER,
    chunk_count        INTEGER,
    state              TEXT NOT NULL DEFAULT 'uploaded',
    error_reason       TEXT,
    uploaded_by        UUID,
    version            INTEGER NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_documents_tenant_state     ON ingestion.documents (tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_created   ON ingestion.documents (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_checksum         ON ingestion.documents (checksum_sha256);

-- Row-Level Security — the single most important tenant-isolation control.
-- Every query against this table is auto-filtered by tenant_id once the
-- session has run: SELECT set_config('app.current_tenant', '<uuid>', true)
ALTER TABLE ingestion.documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON ingestion.documents;
CREATE POLICY tenant_isolation ON ingestion.documents
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

-- ----------------------------------------------------------------------------
-- chunks — one row per chunk, referenced by embeddings in Qdrant.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion.chunks (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL,
    document_id        UUID NOT NULL REFERENCES ingestion.documents(id) ON DELETE CASCADE,
    index              INTEGER NOT NULL,
    content_hash       TEXT NOT NULL,
    text               TEXT NOT NULL,
    token_count        INTEGER NOT NULL,
    page_number        INTEGER NOT NULL,
    metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_tenant         ON ingestion.chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document       ON ingestion.chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash   ON ingestion.chunks (content_hash);

ALTER TABLE ingestion.chunks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON ingestion.chunks;
CREATE POLICY tenant_isolation ON ingestion.chunks
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

-- ----------------------------------------------------------------------------
-- sagas — persistent state for the 5-step ingestion saga.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion.sagas (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL,
    saga_type          TEXT NOT NULL,
    subject_id         UUID NOT NULL,
    total_steps        INTEGER NOT NULL,
    completed_steps    INTEGER NOT NULL DEFAULT 0,
    state              TEXT NOT NULL DEFAULT 'running',
    failing_step       TEXT,
    error              TEXT,
    state_data         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sagas_tenant_state    ON ingestion.sagas (tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_sagas_subject         ON ingestion.sagas (subject_id);

ALTER TABLE ingestion.sagas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON ingestion.sagas;
CREATE POLICY tenant_isolation ON ingestion.sagas
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

-- ----------------------------------------------------------------------------
-- processed_events — Kafka consumer dedup (Design Area 20 Idempotency)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion.processed_events (
    event_id           UUID PRIMARY KEY,
    consumer_group     TEXT NOT NULL,
    processed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processed_events_time ON ingestion.processed_events (processed_at);

-- housekeeping — pretty trivial table, no RLS needed (consumer-group scoped).
