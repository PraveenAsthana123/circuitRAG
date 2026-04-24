-- Action drafts — durable HITL queue for MCP tool calls that could not
-- execute (MCP server down, circuit breaker OPEN, 5xx from remote).
--
-- Design Area 27 (HITL) + Phase 6 §8 (MCP governance). Distinct from
-- ``governance.hitl_queue`` which targets RAG answer review, not tool
-- actions.
--
-- A draft is created whenever ``mcp.MCPClient`` cannot reach the tool
-- server. It stores the tool + arguments + the reason we failed, so an
-- operator (or a scheduled replay job) can later retry the action once
-- the tool comes back online.

CREATE TABLE IF NOT EXISTS governance.action_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id        TEXT NOT NULL UNIQUE,           -- "DRAFT-XXXX" token returned to the caller
    tenant_id       UUID,                           -- NULL for service-account calls
    tool            TEXT NOT NULL,                  -- e.g. "hr.leave_request"
    arguments       JSONB NOT NULL,                 -- original tool arguments
    correlation_id  UUID,                           -- request correlation for tracing
    reason          TEXT NOT NULL,                  -- "cb_open" | "ConnectError" | "http_502" | ...
    status          TEXT NOT NULL DEFAULT 'pending',-- pending | replayed | rejected
    replay_result   JSONB,                          -- populated on status=replayed
    replayed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_action_drafts_status_created
    ON governance.action_drafts (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_drafts_tenant_status
    ON governance.action_drafts (tenant_id, status, created_at DESC);

-- RLS: tenant-scoped rows visible to their tenant; NULL-tenant rows
-- (service-account drafts) visible only through admin bypass.
ALTER TABLE governance.action_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.action_drafts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON governance.action_drafts;
CREATE POLICY tenant_isolation ON governance.action_drafts
    USING (
        tenant_id IS NULL
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
    );
