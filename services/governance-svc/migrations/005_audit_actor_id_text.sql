-- ============================================================================
-- 005 — governance.audit_log.actor_id : UUID → TEXT
-- ============================================================================
-- Why
-- ----
-- ``actor_id`` was UUID-typed when only service callers wrote audit rows and
-- their identifier was a service-account UUID. Adding human-driven replays
-- (admin API → "operator") and federated tokens means ``sub`` claims are
-- often *not* UUIDs (e.g. "alice@example.com", "okta:0o1b2c"). The previous
-- ``$3::uuid`` cast in :func:`AuditWriter.write` raised ``InvalidTextRepresentation``
-- on every non-UUID subject, which the writer caught with a swallowed
-- ``except Exception`` — silently dropping the audit row while reporting
-- success to the caller. Governance reviews against a chain that's missing
-- exactly the rows you most want to see is the worst kind of false confidence.
--
-- Hash-chain compatibility
-- ------------------------
-- ``_compute_entry_hash`` does NOT cover ``actor_id``; the hash body is
-- ``{previous_hash, timestamp, tenant_id, actor_type, action, resource_type,
-- details}``. So the column-type change does not invalidate any existing
-- entry_hash. Confirm with ``scripts/audit_verify.py`` after the migration —
-- that's the gate before declaring the change safe.
--
-- Storage shape
-- -------------
-- TEXT here is intentional: an actor_id can be a UUID, a federated subject,
-- a service-account name, an email, or NULL (system action). Postgres still
-- normalises ``UUID::text`` to lowercase canonical form, so existing rows
-- come across unchanged.
-- ============================================================================

ALTER TABLE governance.audit_log
    ALTER COLUMN actor_id TYPE TEXT
    USING actor_id::text;

COMMENT ON COLUMN governance.audit_log.actor_id IS
    'Subject identifier from the verified token (or NULL when no human present). '
    'Free-form TEXT — not a UUID — to accept federated subjects, emails, etc. '
    'See migration 005_audit_actor_id_text.sql for the why.';
