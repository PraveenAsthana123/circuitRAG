-- Sidecar Advisor — migration 003: richer rating metadata.
--
-- Phase 1B-2 adds a real operator review surface under /admin/sidecar.
-- The original schema only captured a binary rating + timestamp.
-- That was enough for coarse feedback, but not enough to answer:
--
--   * Who rated this event?
--   * Why was it marked useful / not_useful?
--
-- This migration extends advisor_events with lightweight operator
-- metadata. Existing rows remain valid; both new columns are nullable.

ALTER TABLE advisor_events ADD COLUMN rated_by TEXT;
ALTER TABLE advisor_events ADD COLUMN rating_notes TEXT;

CREATE INDEX IF NOT EXISTS idx_advisor_events_rated_by
    ON advisor_events(rated_by);
