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

\echo 'DocuMind → schemas ready: identity, ingestion, eval, governance, finops, observability';
