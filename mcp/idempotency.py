"""
Idempotency store for MCP tool servers.

Two implementations behind a single Protocol:

* :class:`InMemoryIdempotencyStore` — process-local dict. Dev / single-
  node only. Lost on restart, not coordinated across replicas. Same
  shape that ``server_hr.py`` / ``server_itsm.py`` / ``server_drills.py``
  used before this module existed; kept as the default so tests with
  no Postgres still work.

* :class:`PostgresIdempotencyStore` — durable, coordinated, TTL-purged.
  Backed by ``governance.mcp_idempotency`` (migration 007). What
  production deployments use; a retry routed to a different replica
  sees the same cached response, and a server restart does not lose
  the cache.

Decoupling rule
---------------
``mcp/`` does not import ``documind_core``. We use ``asyncpg``
directly (already a runtime dep via ``mcp/drafts.py``) so this module
stays consumable by a hypothetical standalone-MCP repo.

Wire contract
-------------
Every store exposes the SAME two methods:

  * ``lookup_or_register(key, tool, payload_fingerprint)`` →
    ``(state, response)`` tuple. ``state`` is one of:

    - ``"new"`` — Key was unknown; the row is now reserved as
      ``in_progress``. Caller proceeds to dispatch and **must** call
      ``finalize`` when done (succeeded or failed).
    - ``"done"`` — Key was previously completed with the same
      payload; ``response`` is the cached body.
    - ``"in_progress"`` — Key is reserved by an in-flight call. Caller
      should return 202 Accepted (do NOT wait — drill.run can take
      minutes; a waiting client wedges connection pools).
    - ``"conflict"`` — Key matches but the payload fingerprint
      differs; almost always a client bug. Caller returns 409.

  * ``finalize(key, response, status)`` — Transition an
    ``in_progress`` row to ``"succeeded"`` or ``"failed"`` (idempotent
    via CAS — re-runs are no-ops).

Why a fingerprint
-----------------
A retried request with the same Idempotency-Key but a different
payload is ALWAYS a bug; without the fingerprint we'd return a stale
response and the caller would never know. Canonical-JSON sha256 means
"same arguments" is a stable equivalence even when JSON ordering
differs.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Protocol, runtime_checkable

import asyncpg

log = logging.getLogger("mcp.idempotency")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fingerprint(payload: dict[str, Any]) -> str:
    """
    Stable sha256 of canonical-JSON arguments.

    ``sort_keys + tight separators`` produces an identical bytes
    sequence regardless of dict ordering or whitespace, so two
    callers passing equivalent dicts get the same hash. ``default=str``
    lets datetime-like values fingerprint without raising — they
    serialise to ISO strings.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class IdempotencyStore(Protocol):
    """Wire contract — see module docstring."""

    async def lookup_or_register(
        self, key: str, tool: str, payload_fingerprint: str,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def finalize(
        self, key: str, response: dict[str, Any], *, status: str = "succeeded",
    ) -> None: ...

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# In-memory implementation — dev / single-node only
# ---------------------------------------------------------------------------
class InMemoryIdempotencyStore:
    """
    Process-local idempotency cache. NOT durable. NOT coordinated
    across replicas. Same shape as the previous ``dict`` field on
    each server's state object — kept as a default so tests + dev
    runs without Postgres still work. Production deployments use
    :class:`PostgresIdempotencyStore`.
    """

    def __init__(self) -> None:
        # Three small dicts rather than one structured object so
        # introspection in a debugger is straightforward. The total
        # memory is small relative to the response payloads.
        self._fingerprints: dict[str, str] = {}
        self._responses: dict[str, dict[str, Any]] = {}
        self._statuses: dict[str, str] = {}  # 'in_progress' | 'succeeded' | 'failed'

    async def lookup_or_register(
        self, key: str, tool: str, payload_fingerprint: str,
    ) -> tuple[str, dict[str, Any] | None]:
        existing_fp = self._fingerprints.get(key)
        if existing_fp is None:
            self._fingerprints[key] = payload_fingerprint
            self._statuses[key] = "in_progress"
            return ("new", None)
        if existing_fp != payload_fingerprint:
            return ("conflict", None)
        status = self._statuses.get(key, "in_progress")
        if status == "in_progress":
            return ("in_progress", None)
        return ("done", self._responses.get(key))

    async def finalize(
        self, key: str, response: dict[str, Any], *, status: str = "succeeded",
    ) -> None:
        if status not in ("succeeded", "failed"):
            raise ValueError(f"invalid status: {status!r}")
        # CAS analogue: only transition if currently in_progress.
        if self._statuses.get(key) != "in_progress":
            return
        self._statuses[key] = status
        self._responses[key] = response

    async def close(self) -> None:
        # Nothing to close; defined for protocol parity.
        return None


# ---------------------------------------------------------------------------
# Postgres implementation — durable + coordinated + TTL-purged
# ---------------------------------------------------------------------------
class PostgresIdempotencyStore:
    """
    Postgres-backed idempotency cache. Backed by
    ``governance.mcp_idempotency`` (migration 007). The connection
    pool is lazy — first call constructs it, ``close()`` releases.

    ttl_seconds: how long a cached response is honoured. After expiry
        the row is purged inline on the next ``lookup_or_register``;
        a caller hitting an expired key gets a fresh ``"new"`` slot.
    """

    def __init__(self, dsn: str, *, ttl_seconds: int = 86_400) -> None:
        self._dsn = dsn
        self._ttl = max(1, int(ttl_seconds))
        self._pool: asyncpg.Pool | None = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn, min_size=1, max_size=4,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def lookup_or_register(
        self, key: str, tool: str, payload_fingerprint: str,
    ) -> tuple[str, dict[str, Any] | None]:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # Inline TTL purge — keep the table from growing without
            # bound. One DELETE per call is cheap (indexed, no locking
            # of unrelated rows). A separate cron worker is the next
            # iteration if write rate makes this hot.
            await conn.execute(
                "DELETE FROM governance.mcp_idempotency WHERE expires_at < NOW()",
            )
            # Try to insert as a fresh in_progress row. ON CONFLICT
            # DO NOTHING + RETURNING tells us whether we won or lost.
            row = await conn.fetchrow(
                """
                INSERT INTO governance.mcp_idempotency
                    (key, tool, payload_fingerprint, status, expires_at)
                VALUES ($1, $2, $3, 'in_progress',
                        NOW() + make_interval(secs => $4))
                ON CONFLICT (key) DO NOTHING
                RETURNING key
                """,
                key, tool, payload_fingerprint, self._ttl,
            )
            if row is not None:
                return ("new", None)
            # Lost the insert — someone else owns this key. Read the
            # existing row to decide the response shape.
            existing = await conn.fetchrow(
                """
                SELECT payload_fingerprint, status, response
                  FROM governance.mcp_idempotency
                 WHERE key = $1
                """,
                key,
            )
            if existing is None:
                # Race: TTL purge between our INSERT attempt and SELECT.
                # Treat as new — caller will retry the call. Rare.
                log.warning(
                    "mcp_idempotency_purge_race key=%s — treating as new", key,
                )
                return ("new", None)
            if existing["payload_fingerprint"] != payload_fingerprint:
                return ("conflict", None)
            if existing["status"] == "in_progress":
                return ("in_progress", None)
            # 'succeeded' or 'failed' — return the stored response.
            response = existing["response"]
            if isinstance(response, str):
                response = json.loads(response)
            return ("done", response or {})

    async def finalize(
        self, key: str, response: dict[str, Any], *, status: str = "succeeded",
    ) -> None:
        if status not in ("succeeded", "failed"):
            raise ValueError(f"invalid status: {status!r}")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # CAS: only transition in_progress → succeeded/failed.
            # If the row was purged by TTL or the call already
            # finalised (rare retry), this no-ops. Same defensive
            # pattern as governance.action_drafts.mark_replayed.
            await conn.execute(
                """
                UPDATE governance.mcp_idempotency
                   SET status = $1,
                       response = $2::jsonb
                 WHERE key = $3
                   AND status = 'in_progress'
                """,
                status, json.dumps(response), key,
            )


__all__ = [
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "PostgresIdempotencyStore",
    "fingerprint",
]
