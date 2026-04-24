-- eval schema (Design Areas 26, 59, 60, 61)
CREATE TABLE IF NOT EXISTS eval.datasets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID,
    name         TEXT NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS eval.datapoints (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id           UUID NOT NULL REFERENCES eval.datasets(id) ON DELETE CASCADE,
    question             TEXT NOT NULL,
    ground_truth_answer  TEXT NOT NULL,
    expected_chunk_ids   UUID[] NOT NULL DEFAULT '{}',
    metadata             JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_datapoints_dataset ON eval.datapoints(dataset_id);

CREATE TABLE IF NOT EXISTS eval.runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID NOT NULL REFERENCES eval.datasets(id),
    triggered_by    UUID,
    git_sha         TEXT,
    prompt_version  TEXT,
    model           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    n               INTEGER,
    precision_at_k  NUMERIC(5,4),
    recall          NUMERIC(5,4),
    mrr             NUMERIC(5,4),
    ndcg_at_10      NUMERIC(5,4),
    faithfulness    NUMERIC(5,4),
    answer_relevance NUMERIC(5,4)
);

CREATE INDEX IF NOT EXISTS idx_runs_started ON eval.runs (started_at DESC);

CREATE TABLE IF NOT EXISTS eval.feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    correlation_id  UUID,
    question        TEXT,
    answer          TEXT,
    thumbs          TEXT CHECK (thumbs IN ('up', 'down')),
    user_notes      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
