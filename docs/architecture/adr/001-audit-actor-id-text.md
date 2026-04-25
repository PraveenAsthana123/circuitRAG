# ADR-001: `governance.audit_log.actor_id` is TEXT, not UUID

## Status

Accepted — implemented in commit `2b47d4a` + migration `005_audit_actor_id_text.sql`.

## Context

The original schema declared `actor_id UUID`. The audit writer cast
`$3::uuid` on every INSERT. Federated subjects (`alice@example.com`,
`okta:0o1b2c`, `service:replay-worker`) raised
`InvalidTextRepresentation` on the cast. The exception was caught
by the writer's `except Exception` block, the audit row was
silently dropped, and the writer reported success to the caller.

This was the worst category of governance bug: silent loss of
exactly the rows reviewers most need to see. A successful business
operation with no audit trail.

## Decision

Migrate `actor_id` from `UUID` to `TEXT`. Drop the `$3::uuid` cast
in `AuditWriter.write`. Accept any non-empty string identifier
from a verified token's `sub` claim — UUID, federated subject,
email, service-account name.

Hash chain compatibility: `_compute_entry_hash` does NOT cover
`actor_id`, so the column type change does not invalidate any
existing entry hash. Verified by running `audit_verify.py` before
and after the migration.

Pair this with two related changes:
* Replace silent-drop with `documind_audit_write_failures_total
  {action,error_type}` Prometheus counter (so even fail-open drops
  are graphable)
* Add `fail_closed: bool = False` parameter so governance-critical
  callers can opt in to hard failure (see ADR-004)

## Consequences

* Federated identity providers can issue tokens with non-UUID
  `sub` claims without breaking audit attribution.
* The `$3::uuid` cast can never silently regress — the column type
  itself rejects any future attempt to add it back.
* Hash chain integrity is preserved across the migration (verified
  29 → 39 rows post-migration in commit `2b47d4a`).
* `actor_id` is now a free-text field; high-cardinality / malformed
  values can land. The acceptable mitigation is the JWT shape
  validator (ADR-006) which constrains `sub` to non-empty string
  ≤256 chars.
