-- ============================================================================
-- 007 — governance.mcp_idempotency: durable idempotency cache for MCP servers
-- ============================================================================
-- Why
-- ----
-- Each MCP server (server_hr, server_itsm, server_drills) has been keeping
-- its idempotency cache in a process-local ``dict[str, dict]``. That has
-- three production-grade weaknesses the round-2 review flagged:
--   1. Not durable — restart the server, every cached response is gone,
--      so the next retry actually re-executes the side-effect.
--   2. Not coordinated — a horizontally-scaled MCP fleet behind a load
--      balancer would have one cache per replica; a retry routed to a
--      different replica re-executes.
--   3. Unbounded — the dict grows forever in long-running servers.
--
-- This migration backs the idempotency cache with a Postgres table that
-- coordinates across replicas, persists across restarts, supports TTL
-- expiry, and detects same-key-different-payload as a conflict.
--
-- Scope
-- -----
-- INTENTIONALLY service-scope, not tenant-scope. The drill server has no
-- per-tenant data; HR/ITSM tools include tenant_id IN the payload (so
-- the fingerprint already differs across tenants). If a future use case
-- needs tenant-aware idempotency it must EXPLICITLY add a tenant_id
-- column + RLS policy — the absence of those columns is the contract
-- "this is service-scope" and a future migration that adds them is the
-- design checkpoint.
--
-- Schema
-- ------
--   key                  — Idempotency-Key from the HTTP header.
--   tool                 — Which tool the cached call invoked. Lets ops
--                          query "all idempotent replays of hr.leave_request".
--   payload_fingerprint  — sha256 of canonical-JSON arguments. Same key
--                          + different payload = client bug; reject 409.
--   status               — 'in_progress' | 'succeeded' | 'failed'.
--   response             — The cached response body (only on succeeded).
--   created_at / expires_at — TTL window. Default 24 hours.
--
-- Status state machine
-- --------------------
--   in_progress -> succeeded   (call returned ok)
--   in_progress -> failed      (call raised; future retries get fresh attempt)
-- Failed rows are kept until expiry so a tight retry loop sees the same
-- failure consistently rather than re-executing.
-- ============================================================================

CREATE TABLE IF NOT EXISTS governance.mcp_idempotency (
    key                  TEXT PRIMARY KEY,
    tool                 TEXT NOT NULL,
    payload_fingerprint  TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'in_progress',
    response             JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at           TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours',

    -- Storage-level state-machine guard, same defence-in-depth pattern
    -- as governance.action_drafts (migration 006).
    CONSTRAINT mcp_idempotency_status_valid
        CHECK (status IN ('in_progress', 'succeeded', 'failed')),

    -- Succeeded rows MUST carry their response; in-progress rows MUST
    -- NOT (the response doesn't exist yet). Failed rows allow either.
    CONSTRAINT mcp_idempotency_response_consistency
        CHECK (
            (status = 'succeeded' AND response IS NOT NULL)
            OR (status = 'in_progress' AND response IS NULL)
            OR status = 'failed'
        )
);

-- The TTL purge query reads (or DELETEs from) WHERE expires_at < NOW().
-- Without this index every purge is a Seq Scan that scales with cache
-- depth. The btree index on a single ordered column is the canonical
-- shape for time-ordered cleanup.
CREATE INDEX IF NOT EXISTS idx_mcp_idempotency_expires
    ON governance.mcp_idempotency (expires_at);

COMMENT ON TABLE governance.mcp_idempotency IS
    'Durable idempotency cache for MCP tool calls. Service-scope (not '
    'tenant-scope) — see migration 007 header for the rationale. '
    'TTL-purged inline on every read. Key collisions with different '
    'payload fingerprints are surfaced as 409 Conflict.';
