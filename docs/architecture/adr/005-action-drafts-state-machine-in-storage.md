# ADR-005: Storage-level CHECK constraints enforce the draft state machine

## Status

Accepted — implemented in commit `4455e64` + migration
`006_action_drafts_state_constraint.sql`.

## Context

The replay/resolve workflow is a state machine:

  pending → replayed
  pending → rejected

Application-level CAS guards (`mark_replayed` with `WHERE status =
'pending'`) prevent racing transitions. But the schema accepted
any string for `status`. If application code ever regressed (a
hot-fix bypassed the client, a future "rejection" feature touched
status, an SQL injection slipped through validation), the database
would happily store `status = 'garbage'` and dashboards would
silently include it.

## Decision

Add three CHECK constraints to `governance.action_drafts`:

* `action_drafts_status_valid` — `status IN ('pending', 'replayed',
  'rejected')`. Storage-level state-machine guard.
* `action_drafts_replayed_has_artefacts` — a 'replayed' row MUST
  have `replayed_at IS NOT NULL AND replay_result IS NOT NULL`.
* `action_drafts_pending_clean` — a 'pending' row MUST NOT carry
  replay artefacts.

Plus a partial index `idx_action_drafts_pending_by_tenant` on
`(tenant_id, created_at) WHERE status = 'pending'` for the
worker's hot scan path.

## Consequences

* Adding a new lifecycle state (e.g., `superseded`) requires a
  migration that ALTERs the constraint — that's the seam where
  lifecycle changes get reviewed, not buried in a Python file.
* Drilled by `drill_action_draft_state_constraint`: rejecting
  `status='garbage'` directly via asyncpg confirms the constraint
  fires (CheckViolationError).
* The "replayed has artefacts" constraint also catches a different
  bug: `mark_replayed` writing `status='replayed'` without
  populating `replay_result` — the storage rejects it.
* Same defence-in-depth pattern applied later to
  `governance.mcp_idempotency` (migration 007, ADR-003).
