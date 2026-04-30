"""
Tamper-evident audit log (Design Area 27 — Governance).

Every sensitive state transition (draft persisted, draft replayed,
policy evaluated, admin action) ends up as a row in
``governance.audit_log``. The schema carries ``previous_hash`` and
``entry_hash`` columns so a reviewer can detect insertion or
modification after the fact: each row's hash covers the row body
PLUS the previous row's hash, forming a per-tenant append-only chain.

Design notes
------------
* **Per-tenant chain.** Each tenant has its own sealed chain — that
  way a compromise of one tenant's rows cannot forge entries for
  another. The ``previous_hash`` for the first ever row per tenant is
  the empty string.
* **JSON canonicalisation.** Hashes cover a stable, sorted JSON
  serialisation of the row body, so field ordering + whitespace
  cannot change the hash for the same logical entry.
* **Optional.** ``AuditWriter`` is duck-typed. If not wired, callers
  behave as before (no row written). This mirrors :class:`DraftStore`'s
  fail-open philosophy — a missing audit layer should never be the
  reason a degraded tool call turns into a 500.

Typical use::

    writer = AuditWriter(db_client=..., service="inference-svc")
    await writer.write(
        tenant_id=tenant_id,
        action="mcp_draft.created",
        resource_type="mcp_draft",
        details={"draft_id": "DRAFT-...", "tool": "hr.leave_request",
                 "reason": "ConnectError"},
        correlation_id=correlation_id,
    )

The verification CLI that replays the chain per tenant is a follow-up;
the schema (entry_hash, previous_hash) and writer are the load-bearing
bits and land here.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Prometheus counter — audit writes that *failed*. Without this, the
# fail-open path (see ``AuditWriter.write``) is invisible: rows just
# disappear and reviewers never know. Loud-but-non-blocking is the
# right posture for governance — never break the business path, but
# never drop a row without a graphable signal either.
try:
    from prometheus_client import Counter as _PCounter

    _audit_write_failures = _PCounter(
        "documind_audit_write_failures_total",
        "Audit-row writes that failed and were dropped — by action and error class.",
        labelnames=["action", "error_type"],
    )
except ImportError:  # pragma: no cover — prometheus_client is optional
    _audit_write_failures = None  # type: ignore[assignment]


def _classify_error(exc: BaseException) -> str:
    """
    Stable, low-cardinality label for the failure class. We deliberately
    do NOT include the asyncpg-encoded SQLSTATE in the label text —
    Prometheus would explode if every malformed actor_id produced its
    own series. ``InvalidTextRepresentation`` is by far the common case
    and gets its own bucket; everything else collapses into the
    exception class name.
    """
    name = type(exc).__name__
    # asyncpg.exceptions.InvalidTextRepresentationError -> 'InvalidTextRepresentationError'
    if name.endswith("Error"):
        return name[:-5] or name  # strip trailing 'Error' for terser label
    return name


def _canonical_json(payload: dict[str, Any]) -> str:
    """Stable, sorted JSON so hashes are reproducible across runs."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_entry_hash(
    *,
    previous_hash: str,
    timestamp_iso: str,
    tenant_id: str,
    actor_type: str,
    action: str,
    resource_type: str | None,
    details: dict[str, Any],
) -> str:
    """SHA-256 over a stable tuple of row fields + previous_hash."""
    body = {
        "previous_hash": previous_hash,
        "timestamp": timestamp_iso,
        "tenant_id": tenant_id,
        "actor_type": actor_type,
        "action": action,
        "resource_type": resource_type or "",
        "details": details,
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Protocol — anything with .write(...) is accepted by the callers
# ---------------------------------------------------------------------------
class AuditLog(Protocol):
    async def write(
        self,
        *,
        tenant_id: str,
        action: str,
        actor_type: str = "service",
        actor_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        fail_closed: bool = False,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Postgres implementation
# ---------------------------------------------------------------------------
class AuditWriter:
    """
    Persists audit rows to ``governance.audit_log`` with a per-tenant
    hash chain. Requires a ``DbClient`` (or anything exposing
    ``tenant_connection(tenant_id)``).
    """

    def __init__(self, *, db_client: Any, service: str) -> None:
        self._db = db_client
        self._service = service  # included in actor_id-ish context

    async def write(
        self,
        *,
        tenant_id: str,
        action: str,
        actor_type: str = "service",
        actor_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        fail_closed: bool = False,
    ) -> None:
        """
        Record an audit row.

        ``fail_closed``: when True, an audit-write failure RAISES
        ``DataError`` instead of silently swallowing. Default False
        keeps the existing fail-open posture (governance must never
        break the business path) — this is the right default for
        retries, draft creation, scope denials, and other cases
        where dropping a row + emitting a metric is the right
        trade-off. Callers that need a hard guarantee (operator-driven
        admin actions, regulatory writes) opt in per call:

            await audit.write(..., fail_closed=True)

        Per-call control is deliberately the only knob — we don't
        ship a policy table or per-action enum because that's
        design-then-fix, not fix.

        Both modes increment ``documind_audit_write_failures_total``
        and emit a structured error log on failure. The only
        difference is whether the exception escapes the writer.
        """
        details = dict(details or {})
        details.setdefault("service", self._service)
        try:
            async with self._db.tenant_connection(tenant_id) as conn:
                # Look up the latest hash for this tenant to chain onto.
                last = await conn.fetchrow(
                    """
                    SELECT entry_hash, timestamp
                      FROM governance.audit_log
                     WHERE tenant_id = $1::uuid
                     ORDER BY timestamp DESC, id DESC
                     LIMIT 1
                    """,
                    tenant_id,
                )
                previous_hash = last["entry_hash"] if last and last["entry_hash"] else ""

                # We hash a stable textual representation of the row, but
                # asyncpg needs a ``datetime`` for the TIMESTAMPTZ column.
                # Pull NOW() from the server so it matches the reader's
                # clock, keep the string for hashing, and parse into
                # datetime for the bind.
                timestamp_iso = await conn.fetchval("SELECT NOW()::text")
                timestamp_dt = datetime.fromisoformat(timestamp_iso)
                entry_hash = _compute_entry_hash(
                    previous_hash=previous_hash,
                    timestamp_iso=timestamp_iso,
                    tenant_id=tenant_id,
                    actor_type=actor_type,
                    action=action,
                    resource_type=resource_type,
                    details=details,
                )
                await conn.execute(
                    # actor_id is TEXT (migration 005). NEVER cast to UUID
                    # here — federated subjects, emails, and service-account
                    # names are all valid actor_ids, and a cast would silently
                    # raise + drop the audit row. Migration 005 has the full
                    # rationale.
                    """
                    INSERT INTO governance.audit_log
                        (timestamp, tenant_id, actor_id, actor_type,
                         action, resource_type, resource_id, details,
                         correlation_id, previous_hash, entry_hash)
                    VALUES ($1, $2::uuid, $3, $4,
                            $5, $6, $7::uuid, $8::jsonb,
                            $9::uuid, $10, $11)
                    """,
                    timestamp_dt,
                    tenant_id,
                    actor_id,
                    actor_type,
                    action,
                    resource_type,
                    resource_id,
                    _canonical_json(details),
                    correlation_id,
                    previous_hash,
                    entry_hash,
                )
            log.info(
                "audit_written tenant=%s action=%s resource=%s corr=%s",
                tenant_id,
                action,
                resource_type,
                correlation_id,
            )
        except Exception as exc:  # noqa: BLE001 — controlled re-raise on fail_closed
            # Counter + structured log are the same in both modes —
            # the difference is only whether we then raise or swallow.
            error_type = _classify_error(exc)
            if _audit_write_failures is not None:
                _audit_write_failures.labels(
                    action=action,
                    error_type=error_type,
                ).inc()
            posture = "fail_closed" if fail_closed else "fail_open"
            log.error(
                "audit_write_failed action=%s tenant_id=%s actor_type=%s "
                "actor_id=%r resource_type=%s resource_id=%s "
                "correlation_id=%s error_type=%s err=%s posture=%s",
                action,
                tenant_id,
                actor_type,
                actor_id,
                resource_type,
                resource_id,
                correlation_id,
                error_type,
                exc,
                posture,
            )
            if fail_closed:
                # Caller asked for a hard guarantee. Wrap as DataError
                # (5xx) so the FastAPI error handler maps it to a
                # consistent envelope and the original exception is
                # preserved in __cause__.
                from .exceptions import DataError

                raise DataError(
                    f"audit write failed (fail_closed) action={action!r} " f"error_type={error_type}",
                    details={
                        "action": action,
                        "error_type": error_type,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                    },
                ) from exc


__all__ = ["AuditLog", "AuditWriter", "_compute_entry_hash", "_canonical_json"]
