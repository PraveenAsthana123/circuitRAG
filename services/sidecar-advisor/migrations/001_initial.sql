-- Sidecar Advisor — initial schema (migration 001)
--
-- Two tables:
--   advisor_events  — one row per "user pasted X, advisor said Y, user rated Z"
--   advisor_memory  — distilled patterns the advisor learned from rated events
--
-- WAL mode enabled at runtime in memory.py.
-- Migrations run idempotently — re-applying this file is safe.

CREATE TABLE IF NOT EXISTS advisor_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,            -- ISO-8601 UTC
    event_type      TEXT    NOT NULL,            -- prompt|code|architecture|pr_review|debug
    source          TEXT    NOT NULL,            -- manual|git-diff|paste|webhook
    content_hash    TEXT    NOT NULL,            -- sha256(content)[:16] for joins; raw NOT logged elsewhere
    content         TEXT    NOT NULL,            -- the actual paste; stays local-only
    model_used      TEXT,
    policy_version  TEXT    NOT NULL,            -- sha256(policy.yaml)[:12]
    advisor_output  TEXT,                        -- JSON matching the output_schema
    advisor_output_raw TEXT,                     -- raw LLM response if JSON parse failed
    user_rating     TEXT,                        -- useful|not_useful|null (until rated)
    rated_at        TEXT,                        -- ISO-8601 UTC when rating set
    duration_s      REAL                         -- end-to-end advisor latency
);

-- §7.2: indexes on every WHERE/ORDER BY column
CREATE INDEX IF NOT EXISTS idx_advisor_events_created_at
    ON advisor_events(created_at);
CREATE INDEX IF NOT EXISTS idx_advisor_events_event_type
    ON advisor_events(event_type);
CREATE INDEX IF NOT EXISTS idx_advisor_events_user_rating
    ON advisor_events(user_rating);

-- Distilled patterns — memory the advisor uses on future events.
-- Populated by a separate "memory distillation" job (Phase 2).
-- Kept simple in Phase 1: one row = one pattern + the event IDs that
-- contributed to it.
CREATE TABLE IF NOT EXISTS advisor_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    pattern_kind    TEXT    NOT NULL,            -- mistake|preference|style|skip
    pattern_text    TEXT    NOT NULL,            -- "always run pytest before commit"
    confidence      REAL    NOT NULL DEFAULT 0.5,
    source_events   TEXT    NOT NULL,            -- JSON array of advisor_events.id
    last_used_at    TEXT,                        -- when the advisor last cited this
    use_count       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_advisor_memory_pattern_kind
    ON advisor_memory(pattern_kind);
CREATE INDEX IF NOT EXISTS idx_advisor_memory_last_used_at
    ON advisor_memory(last_used_at);

-- Bookkeeping table — tracks which migrations have been applied
CREATE TABLE IF NOT EXISTS _migrations (
    name        TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);
