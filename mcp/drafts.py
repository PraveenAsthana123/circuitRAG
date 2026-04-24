"""
Durable draft store for MCP tool actions that could not execute.

When the MCP server is unreachable (connection refused, 5xx, CB OPEN),
``mcp.MCPClient`` can't run the tool but must still answer the caller —
it persists a *draft* that an operator can later resolve (replay, reject,
or edit). Drafts are the audit trail for "the user asked for X; we
couldn't do it right now; here's proof we didn't drop it on the floor".

Two backends live here:

* :class:`InMemoryDraftStore` — process-local dict. Default. Fine for
  tests + single-process demos.
* :class:`PostgresDraftStore` — writes to ``governance.action_drafts``.
  Survives crashes and lets a separate replay worker pick up drafts.

The client takes a :class:`DraftStore` (duck-typed) so you can plug in
either without touching the call path.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------
@dataclass
class DraftRecord:
    draft_id: str
    tool: str
    arguments: dict[str, Any]
    reason: str
    tenant_id: str | None = None
    correlation_id: str | None = None
    status: str = "pending"           # pending | replayed | rejected
    replay_result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    replayed_at: float | None = None


# ---------------------------------------------------------------------------
# Protocol — duck-typed; MCPClient accepts anything with these methods.
#
# All read / mutate ops take ``tenant_id`` because the Postgres backend
# runs as a NOBYPASSRLS role — it cannot see or write tenant-scoped
# rows without first setting ``app.current_tenant``. Callers already
# have the tenant from the request context.
# ---------------------------------------------------------------------------
class DraftStore(Protocol):
    async def save(self, draft: DraftRecord) -> None: ...
    async def get(
        self, draft_id: str, tenant_id: str | None = None
    ) -> DraftRecord | None: ...
    async def list_pending(
        self, tenant_id: str | None = None
    ) -> list[DraftRecord]: ...
    async def mark_replayed(
        self, draft_id: str, result: dict[str, Any], tenant_id: str | None = None
    ) -> None: ...


# ---------------------------------------------------------------------------
# In-memory (default)
# ---------------------------------------------------------------------------
class InMemoryDraftStore:
    """Process-local draft store. Lost on restart — use PostgresDraftStore in prod."""

    def __init__(self) -> None:
        self._drafts: dict[str, DraftRecord] = {}

    async def save(self, draft: DraftRecord) -> None:
        self._drafts[draft.draft_id] = draft

    async def get(
        self, draft_id: str, tenant_id: str | None = None
    ) -> DraftRecord | None:
        d = self._drafts.get(draft_id)
        if d is None:
            return None
        # tenant_id is authoritative if provided — match PG behaviour
        if tenant_id is not None and d.tenant_id != tenant_id:
            return None
        return d

    async def list_pending(
        self, tenant_id: str | None = None
    ) -> list[DraftRecord]:
        out = [
            d for d in self._drafts.values()
            if d.status == "pending" and (tenant_id is None or d.tenant_id == tenant_id)
        ]
        return sorted(out, key=lambda d: d.created_at)

    async def mark_replayed(
        self, draft_id: str, result: dict[str, Any], tenant_id: str | None = None
    ) -> None:
        d = self._drafts.get(draft_id)
        if d is None or (tenant_id is not None and d.tenant_id != tenant_id):
            return
        d.status = "replayed"
        d.replay_result = result
        d.replayed_at = time.time()


# ---------------------------------------------------------------------------
# PostgreSQL backend — writes to governance.action_drafts
# ---------------------------------------------------------------------------
# RLS note: the table has FORCE ROW LEVEL SECURITY. Runtime services
# connect as ``documind_app`` (NOBYPASSRLS), so INSERT/UPDATE/SELECT
# against tenant-scoped rows must first
# ``SET LOCAL app.current_tenant = <tenant>`` — otherwise the policy
# check collapses to ``tenant_id IS NULL`` and the statement silently
# sees (or writes) nothing. We use ``tenant_connection`` for any call
# that references a specific tenant_id; ``admin_connection`` is only
# safe for the ``tenant_id IS NULL`` path.
class PostgresDraftStore:
    """
    Durable draft store backed by ``governance.action_drafts``.

    Requires a ``documind_core.db_client.DbClient`` (duck-typed — any
    object exposing ``tenant_connection(tenant_id)`` and
    ``admin_connection()`` async context managers works).
    """

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    def _conn_for(self, tenant_id: str | None):
        """Pick the right connection type for RLS. Not async — just returns
        an async context manager."""
        if tenant_id:
            return self._db.tenant_connection(tenant_id)
        return self._db.admin_connection()

    async def save(self, draft: DraftRecord) -> None:
        async with self._conn_for(draft.tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO governance.action_drafts
                    (draft_id, tenant_id, tool, arguments, correlation_id,
                     reason, status, created_at)
                VALUES ($1, $2::uuid, $3, $4::jsonb, $5::uuid, $6, $7, to_timestamp($8))
                ON CONFLICT (draft_id) DO NOTHING
                """,
                draft.draft_id,
                draft.tenant_id,
                draft.tool,
                json.dumps(draft.arguments),
                draft.correlation_id,
                draft.reason,
                draft.status,
                draft.created_at,
            )
            log.info(
                "action_draft_persisted draft_id=%s tool=%s tenant=%s reason=%s",
                draft.draft_id, draft.tool, draft.tenant_id, draft.reason,
            )

    async def get(
        self, draft_id: str, tenant_id: str | None = None
    ) -> DraftRecord | None:
        async with self._conn_for(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT draft_id, tenant_id::text, tool, arguments,
                       correlation_id::text, reason, status, replay_result,
                       extract(epoch from created_at) AS created_at,
                       extract(epoch from replayed_at) AS replayed_at
                  FROM governance.action_drafts
                 WHERE draft_id = $1
                """,
                draft_id,
            )
        return _row_to_record(row) if row else None

    async def list_pending(
        self, tenant_id: str | None = None
    ) -> list[DraftRecord]:
        async with self._conn_for(tenant_id) as conn:
            if tenant_id:
                rows = await conn.fetch(
                    """
                    SELECT draft_id, tenant_id::text, tool, arguments,
                           correlation_id::text, reason, status, replay_result,
                           extract(epoch from created_at) AS created_at,
                           extract(epoch from replayed_at) AS replayed_at
                      FROM governance.action_drafts
                     WHERE status = 'pending' AND tenant_id = $1::uuid
                     ORDER BY created_at
                    """,
                    tenant_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT draft_id, tenant_id::text, tool, arguments,
                           correlation_id::text, reason, status, replay_result,
                           extract(epoch from created_at) AS created_at,
                           extract(epoch from replayed_at) AS replayed_at
                      FROM governance.action_drafts
                     WHERE status = 'pending' AND tenant_id IS NULL
                     ORDER BY created_at
                    """
                )
        return [_row_to_record(r) for r in rows]

    async def mark_replayed(
        self, draft_id: str, result: dict[str, Any], tenant_id: str | None = None
    ) -> None:
        async with self._conn_for(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE governance.action_drafts
                   SET status = 'replayed',
                       replay_result = $2::jsonb,
                       replayed_at = NOW()
                 WHERE draft_id = $1
                """,
                draft_id,
                json.dumps(result),
            )
            log.info("action_draft_replayed draft_id=%s tenant=%s", draft_id, tenant_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row_to_record(row: Any) -> DraftRecord:
    # asyncpg returns Record; supports dict-style and attribute access.
    args = row["arguments"]
    if isinstance(args, str):
        args = json.loads(args)
    result = row["replay_result"]
    if isinstance(result, str):
        result = json.loads(result)
    return DraftRecord(
        draft_id=row["draft_id"],
        tenant_id=row["tenant_id"],
        tool=row["tool"],
        arguments=args or {},
        correlation_id=row["correlation_id"],
        reason=row["reason"],
        status=row["status"],
        replay_result=result,
        created_at=float(row["created_at"]) if row["created_at"] else 0.0,
        replayed_at=float(row["replayed_at"]) if row["replayed_at"] else None,
    )


# Re-export for tidy imports
__all__ = [
    "DraftRecord",
    "DraftStore",
    "InMemoryDraftStore",
    "PostgresDraftStore",
]
