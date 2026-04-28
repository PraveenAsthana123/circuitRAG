-- Sidecar Advisor — migration 002: council audit-row table.
--
-- The pr_review route delegates to a 3-author / 1-reviewer / 1-chair
-- AgentBoard council. Each invocation produces rich telemetry —
-- per-draft model_used, per-review score, chair errors, outcome
-- classification. Without persistence, that telemetry is observable
-- only via the structured-log stream (volatile) — not queryable for:
--
--   * "Which author errors most often?"
--     SELECT author, COUNT(*) FROM (json_each(drafts_json))
--     WHERE error IS NOT NULL GROUP BY author
--   * "Council p95 duration by outcome over the last 7 days"
--   * "All council runs where security_auditor flagged HIGH risk"
--
-- One row per advisor.review() call that hit the council path. The
-- event_id FK joins back to advisor_events for the user-visible
-- summary. Council runs WITHOUT a parent event_id (e.g. operator-
-- triggered backfill) get NULL; the FK is nullable.

CREATE TABLE IF NOT EXISTS advisor_council_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER,                -- nullable FK to advisor_events.id
    created_at      TEXT    NOT NULL,       -- ISO-8601 UTC
    outcome         TEXT    NOT NULL,       -- ok|partial|advisor_failed|all_authors_failed
    advisor_id      TEXT    NOT NULL,       -- chair role identifier
    prompt_version  TEXT    NOT NULL,       -- AgentBoard prompt-template hash
    duration_s      REAL    NOT NULL,
    advisor_error   TEXT,                   -- chair exception, if any
    failed_authors  TEXT    NOT NULL,       -- JSON array of author_ids
    drafts_json     TEXT    NOT NULL,       -- JSON: [{author_id, model_used, text, duration_s, error}]
    reviews_json    TEXT    NOT NULL,       -- JSON: [{reviewer_id, draft_author_id, score, critique, error}]
    FOREIGN KEY (event_id) REFERENCES advisor_events(id)
);

-- Indexes per §7.2 — every column the dashboard would WHERE / GROUP BY.
CREATE INDEX IF NOT EXISTS idx_council_runs_event_id
    ON advisor_council_runs(event_id);
CREATE INDEX IF NOT EXISTS idx_council_runs_outcome
    ON advisor_council_runs(outcome);
CREATE INDEX IF NOT EXISTS idx_council_runs_created_at
    ON advisor_council_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_council_runs_advisor_id
    ON advisor_council_runs(advisor_id);
