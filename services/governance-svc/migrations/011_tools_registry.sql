-- Tools registry — SQL surface for MCP server tool catalog + permissions.
--
-- Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
-- (expand→migrate→contract), §52 row 4 (operator API gap).
--
-- The MCP server tool definitions currently live as Python literals
-- in mcp/server_*.py (TOOLS = [...] lists, ~4 servers, ~10-15 tools
-- total). Python literals are fine for declaration but provide no
-- queryable surface for governance: "which tools require approval?",
-- "which actors can call hr.policy_lookup?", "what's the risk
-- profile of every read-only tool?" all need custom code today.
--
-- This migration creates the SQL catalog. Per §47.7 expand-phase:
-- the table is created + drilled, but the Python TOOLS lists in
-- mcp/server_*.py REMAIN AUTHORITATIVE. A future iteration syncs
-- the Python lists into the table on server startup; later, contract-
-- phase makes the table authoritative and the Python lists become
-- generated.
--
-- Two tables created:
--   governance.tools             — tool catalog (server, name, schema,
--                                  scopes, risk, approval_required)
--   governance.tool_permissions  — RBAC entries (tool, actor pattern,
--                                  capability flags)
--
-- Both are SYSTEM CATALOG (not tenant data) so NO RLS — same pattern
-- as governance.policies + governance.feature_flags. Write access is
-- restricted via grant: only documind admin (table owner) can mutate;
-- documind_app gets SELECT only (read-side). Future write-side ships
-- with explicit grant change + drill update.
--
-- Drilled by mcp/tests/drill_tools_registry_table.py.

-- ───────────────────────────────────────────────────────────
-- Tool catalog
-- ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS governance.tools (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Natural key: (server, name) is unique across the whole catalog.
    -- e.g. ("paperclip", "paperclip.snapshot"), ("hr", "hr.policy_lookup")
    server            TEXT NOT NULL,
    name              TEXT NOT NULL,

    -- Documentation
    description       TEXT NOT NULL,

    -- Schema definitions sourced from the Python TOOLS records.
    -- input_schema is JSON Schema; output_schema is JSON Schema or
    -- a JSON-encoded string description for non-strict tools.
    input_schema      JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_schema     JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Governance metadata. side_effects values: read | write |
    -- destructive | external. required_scopes is the list a caller
    -- must hold to invoke this tool.
    side_effects      TEXT NOT NULL,
    required_scopes   TEXT[] NOT NULL DEFAULT '{}',
    idempotent        BOOLEAN NOT NULL DEFAULT FALSE,

    -- Risk classification — derived from side_effects + sensitivity.
    -- Risk floor enforced by CHECK; future iteration may add policy.
    risk_level        TEXT NOT NULL,

    -- Lifecycle
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    owner_team        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT tools_server_name_unique UNIQUE (server, name),
    CONSTRAINT tools_risk_level_valid CHECK (risk_level IN ('low','medium','high','critical')),
    CONSTRAINT tools_side_effects_valid CHECK (side_effects IN ('read','write','destructive','external'))
);

CREATE INDEX IF NOT EXISTS idx_tools_server_enabled
    ON governance.tools (server, enabled);
CREATE INDEX IF NOT EXISTS idx_tools_risk_enabled
    ON governance.tools (risk_level, enabled);
CREATE INDEX IF NOT EXISTS idx_tools_approval_required
    ON governance.tools (approval_required) WHERE approval_required = TRUE;

COMMENT ON TABLE governance.tools IS
    'MCP server tool catalog. SYSTEM CATALOG (not tenant-scoped) — '
    'NO RLS. Mirrors mcp/server_*.py TOOLS lists; future iteration '
    'syncs on server startup. Drilled by drill_tools_registry_table.py.';
COMMENT ON COLUMN governance.tools.required_scopes IS
    'Scope strings a caller must hold (e.g. "snapshot:read", "drill:run"). '
    'Empty array = no scope check (any actor may call).';

-- ───────────────────────────────────────────────────────────
-- Tool permissions (RBAC matrix)
-- ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS governance.tool_permissions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Natural key on (server, tool_name, actor_pattern). Using server +
    -- name (NOT tool id FK) so this table can be loaded ahead of the
    -- tool catalog and the foreign key is logical, not enforced.
    -- (Migration order: tools first, then permissions; cleaner ops.)
    server         TEXT NOT NULL,
    tool_name      TEXT NOT NULL,

    -- Actor pattern — matches command_orchestrator's actor-classification
    -- conventions: "council:author", "user:*", "system:*", or a literal
    -- agent name. SQL LIKE-style pattern; '*' is the only wildcard.
    actor_pattern  TEXT NOT NULL,

    -- Capability flags. RBAC matrix is intentionally simple:
    --   can_invoke — actor may call the tool at all
    --   can_modify — actor may pass arguments that mutate state (write tools)
    --   can_admin  — actor may grant/revoke this tool's permissions
    can_invoke     BOOLEAN NOT NULL DEFAULT FALSE,
    can_modify     BOOLEAN NOT NULL DEFAULT FALSE,
    can_admin      BOOLEAN NOT NULL DEFAULT FALSE,

    granted_by     TEXT,                            -- which operator/process
    granted_reason TEXT,                            -- audit context
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ,                     -- NULL = no expiry

    CONSTRAINT tool_permissions_unique UNIQUE (server, tool_name, actor_pattern)
);

CREATE INDEX IF NOT EXISTS idx_tool_permissions_actor
    ON governance.tool_permissions (actor_pattern);
CREATE INDEX IF NOT EXISTS idx_tool_permissions_server_tool
    ON governance.tool_permissions (server, tool_name);

COMMENT ON TABLE governance.tool_permissions IS
    'RBAC matrix: which actor patterns may invoke / modify / admin '
    'each tool. Drilled by drill_tools_registry_table.py. Composes '
    'with the MCP gateway authorization (scripts/mcp_gateway.py).';

-- ───────────────────────────────────────────────────────────
-- Grants — read-only for app role; admin retains full control
-- ───────────────────────────────────────────────────────────
GRANT SELECT ON governance.tools TO documind_app;
GRANT SELECT ON governance.tool_permissions TO documind_app;
-- Future iteration: GRANT INSERT, UPDATE on these to documind_app
-- when MCP servers sync their TOOLS list at startup. Until then,
-- only the migration + admin scripts can write.
