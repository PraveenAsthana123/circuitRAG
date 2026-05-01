-- 014_idempotency.sql
-- Phase C2: Idempotency-Key support for task creation.
--
-- Per §6.3: clients can pass `Idempotency-Key: <uuid>` on
-- POST /api/v1/agentic/tasks. Same (tenant_id, key) + same body_hash
-- → return cached task_id (201 again, but no double creation).
-- Same (tenant_id, key) + different body_hash → 409 Conflict
-- (silent overwrite would be a data-integrity bug).
--
-- Composite key (tenant_id, key) — bare key would collide across
-- tenants per §C2.4. RLS forces tenant scope on every read.
--
-- TTL: rows older than 24h are eligible for cleanup. The cleanup
-- itself is a service-side cron (future phase); the index supports
-- it without locking writes.

CREATE TABLE IF NOT EXISTS orchestration.idempotency_keys (
  tenant_id    TEXT NOT NULL,
  key          TEXT NOT NULL,
  task_id      TEXT NOT NULL,
  body_hash    TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, key)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created
  ON orchestration.idempotency_keys (created_at);

ALTER TABLE orchestration.idempotency_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.idempotency_keys FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS idempotency_keys_isolation ON orchestration.idempotency_keys;
CREATE POLICY idempotency_keys_isolation
  ON orchestration.idempotency_keys
  USING (tenant_id = current_setting('app.current_tenant', true));

COMMENT ON TABLE orchestration.idempotency_keys IS
  'Per-tenant idempotency keys for POST /api/v1/agentic/tasks. '
  'Composite PK (tenant_id, key) prevents cross-tenant collision.';
COMMENT ON COLUMN orchestration.idempotency_keys.body_hash IS
  'SHA-256 of canonical request body. Same key + diff hash → 409.';
