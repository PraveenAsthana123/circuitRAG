-- ============================================================================
-- DocuMind — PostgreSQL initialization (runs once, on first cluster start)
-- ============================================================================
-- Creates the schema-per-service namespaces documented in spec §5.1. Each
-- service's own migrations then add tables under its schema. This script
-- deliberately creates NO tables — schema ownership stays with each service.
-- ============================================================================

\echo 'DocuMind → creating per-service schemas and migration tracker';

CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS ingestion;
CREATE SCHEMA IF NOT EXISTS eval;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS finops;
CREATE SCHEMA IF NOT EXISTS observability;

-- Migration tracker shared across services. Each row = one applied migration.
-- Service + filename is the natural key; same filename across services is OK.
CREATE TABLE IF NOT EXISTS public._migrations (
    service     TEXT      NOT NULL,
    filename    TEXT      NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT,
    PRIMARY KEY (service, filename)
);

-- gen_random_uuid() — used by every tenant-scoped table
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- pg_trgm — fuzzy text search on document titles / filenames
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Default tenant-context setting used by RLS policies. Unset = no rows visible,
-- which is the safe default. Each connection is expected to
-- SELECT set_config('app.current_tenant', '<uuid>', false)
-- after authenticating the caller.
ALTER DATABASE documind SET app.current_tenant = '';

-- ============================================================================
-- Role separation for RLS enforcement (Design Area 5).
--
-- THE CRITICAL RULE: services MUST NOT connect as the superuser / owner.
-- Postgres always bypasses RLS for superusers AND for BYPASSRLS roles,
-- regardless of `FORCE ROW LEVEL SECURITY`. The default `POSTGRES_USER`
-- created by the docker image is a superuser, so RLS was a no-op until
-- this migration landed.
--
-- Roles:
--   documind       — bootstrap + owner (SUPERUSER by default). Runs migrations.
--   documind_app   — what services connect as at runtime. NO superuser,
--                    NO bypassrls. RLS applies. Grants below give it only
--                    DML on the schemas it needs.
--   documind_ops   — background / recovery / billing jobs that LEGITIMATELY
--                    need cross-tenant access. BYPASSRLS = true. Use
--                    sparingly; audited.
-- ============================================================================

-- Create roles once; IF NOT EXISTS is not valid for CREATE ROLE so we wrap.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'documind_app') THEN
        CREATE ROLE documind_app
            LOGIN PASSWORD 'documind_app'
            NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'documind_ops') THEN
        CREATE ROLE documind_ops
            LOGIN PASSWORD 'documind_ops'
            NOSUPERUSER BYPASSRLS NOCREATEROLE NOCREATEDB;
    END IF;
END $$;

-- Allow both to USE the schemas + run DML on every existing table.
-- Future tables inherit via default privileges below.
GRANT USAGE ON SCHEMA identity, ingestion, eval, governance, finops, observability
    TO documind_app, documind_ops;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA
    identity, ingestion, eval, governance, finops, observability
    TO documind_app, documind_ops;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA
    identity, ingestion, eval, governance, finops, observability
    TO documind_app, documind_ops;

-- Default privileges for tables CREATED BY the `documind` role in future
-- migrations — without these the migration-runner's new tables would
-- reject the app role until explicit grant.
ALTER DEFAULT PRIVILEGES FOR ROLE documind IN SCHEMA
    identity, ingestion, eval, governance, finops, observability
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO documind_app, documind_ops;
ALTER DEFAULT PRIVILEGES FOR ROLE documind IN SCHEMA
    identity, ingestion, eval, governance, finops, observability
    GRANT USAGE, SELECT ON SEQUENCES TO documind_app, documind_ops;

\echo 'DocuMind → schemas + roles ready (documind=owner, documind_app=runtime, documind_ops=privileged-jobs)';
