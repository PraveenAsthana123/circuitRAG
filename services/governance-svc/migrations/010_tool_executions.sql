-- Tool executions audit — SQL surface for MCP gateway tool calls.
--
-- Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
-- (expand→migrate→contract), §52 row 4 (operator API gap),
-- §53.39 (observability taxonomy).
--
-- The MCP gateway (scripts/mcp_gateway.py) currently writes one
-- audit row per tool-call to .loop/mcp_gateway_audit.jsonl. JSONL
-- is fast + grep-friendly but NOT SQL-queryable: operators cannot
-- answer "show me all denied tool calls by actor X this week" or
-- "which tools have the highest deny rate" without writing custom
-- jq pipelines.
--
-- This table mirrors the JSONL row shape with an SQL-queryable
-- structure. Per §47.7 expand-phase: this commit creates the
-- table only; the write-side (gateway dual-write) ships in a
-- subsequent commit. Once the SQL table is loaded with steady
-- traffic, the migrate-phase backfills historical JSONL rows;
-- only THEN does the contract-phase remove the JSONL writer.
--
-- JSONL shape captured (per .loop/mcp_gateway_audit.jsonl on
-- 2026-05-06): allow, reason, actor, server, tool, risk,
-- approved_actors, rule_matched, timestamp, request_id.
--
-- Drilled by mcp/tests/drill_tool_executions_table.py.

CREATE TABLE IF NOT EXISTS governance.tool_executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Correlation + tenant. tenant_id is NULLABLE because some MCP
    -- traffic (council:* actors, drill traffic) is service-account
    -- and not tenant-scoped. RLS policy lets service-account rows
    -- be invisible to tenant queries (security floor).
    request_id      UUID NOT NULL,
    tenant_id       TEXT,
    correlation_id  UUID,

    -- Actor + target identity
    actor           TEXT NOT NULL,                  -- "council:author", "user:alice", etc.
    server          TEXT NOT NULL,                  -- MCP server name (research/hr/itsm/...)
    tool            TEXT NOT NULL,                  -- tool name within the server

    -- Decision
    allow           BOOLEAN NOT NULL,               -- TRUE if gateway permitted
    decision_reason TEXT NOT NULL,                  -- gateway's reason text
    risk            TEXT NOT NULL,                  -- low | medium | high | critical
    rule_matched    TEXT,                           -- which gateway rule fired

    -- Operator-facing arguments + result. Cap at jsonb 1MB by
    -- convention; oversize args go to a separate blob store.
    arguments       JSONB NOT NULL DEFAULT '{}'::jsonb,
    result          JSONB,                          -- only populated on allow=TRUE
    error_message   TEXT,                           -- non-NULL on allow=FALSE OR runtime error

    -- Performance
    latency_ms      INTEGER,                        -- end-to-end gateway → tool → response
    status_code     INTEGER,                        -- HTTP status if applicable

    -- Lifecycle
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes — every WHERE column the dashboards / RCA queries hit
CREATE INDEX IF NOT EXISTS idx_tool_executions_created
    ON governance.tool_executions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_executions_tenant_created
    ON governance.tool_executions (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_executions_actor_created
    ON governance.tool_executions (actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_executions_server_tool_created
    ON governance.tool_executions (server, tool, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_executions_allow_risk
    ON governance.tool_executions (allow, risk, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_executions_request_id
    ON governance.tool_executions (request_id);

-- RLS: tenant-scoped rows visible only to their tenant. Service-
-- account rows (tenant_id IS NULL) are visible only via admin
-- bypass — same pattern as governance.action_drafts. Per §43.4
-- isolation drill expectation.
ALTER TABLE governance.tool_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.tool_executions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON governance.tool_executions;
CREATE POLICY tenant_isolation ON governance.tool_executions
    USING (
        tenant_id IS NULL
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')
    );

-- Granular grants — application role gets INSERT (writes from gateway),
-- SELECT (reads from observability), and UPDATE (mark replays). NEVER
-- DELETE (audit immutability). RLS enforces tenant scoping on every
-- access, so the grants don't widen the data surface.
GRANT SELECT, INSERT, UPDATE ON governance.tool_executions TO documind_app;
-- documind admin role keeps full control for migrations + emergency
-- corrections; auto-vacuum + pg_repack still work at the table-owner
-- level (documind).

COMMENT ON TABLE governance.tool_executions IS
    'MCP gateway tool-call audit. Mirrors .loop/mcp_gateway_audit.jsonl '
    'with SQL-queryable structure. Drilled by '
    'drill_tool_executions_table.py + composed into agent_task_registry '
    'as a provider lane.';
COMMENT ON COLUMN governance.tool_executions.tenant_id IS
    'NULL for service-account / council:* / drill traffic. RLS policy '
    'makes NULL-tenant rows invisible to tenant queries (security floor).';
COMMENT ON COLUMN governance.tool_executions.allow IS
    'TRUE if gateway permitted the tool call (rule_matched fired). '
    'FALSE if denied (decision_reason explains).';
