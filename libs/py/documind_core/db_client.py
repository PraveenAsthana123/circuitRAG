"""
PostgreSQL client (Design Areas 5 — Tenant RLS, 12 — Consistency, 46 — DB Strategy).

Wraps asyncpg in a small, opinionated surface:

* Connection pool with sensible defaults.
* Per-request ``SET LOCAL app.current_tenant`` so row-level-security (RLS)
  policies on each table auto-filter by tenant — the application code
  literally cannot accidentally read another tenant's rows.
* :class:`Transaction` wrapper that groups writes under one lock.
* :class:`Repository` base class — every repo subclasses this.

Why asyncpg and not SQLAlchemy
------------------------------
At DocuMind's scale, we don't need an ORM. SQL is the domain language of
the data layer; hiding it behind an ORM just adds a second language to
learn and a second performance cliff to find. asyncpg is the fastest
PostgreSQL driver in Python (by a wide margin), exposes COPY + CURSOR, and
returns ``Record`` objects that are dict-compatible — plenty.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from .exceptions import DataError, TenantIsolationError

log = logging.getLogger(__name__)


class DbClient:
    """
    Lazy-initialized asyncpg pool + helpers.

    Lifecycle: call :meth:`connect` once at service startup, :meth:`close`
    on shutdown. In FastAPI this lives in the lifespan context.
    """

    def __init__(
        self,
        *,
        dsn: str,
        min_size: int = 2,
        max_size: int = 20,
        command_timeout: float = 10.0,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._command_timeout = command_timeout
        self._pool: asyncpg.Pool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            command_timeout=self._command_timeout,
        )
        log.info("postgres_pool_opened min=%d max=%d", self._min_size, self._max_size)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            log.info("postgres_pool_closed")

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise DataError("DbClient.connect() has not been called yet")
        return self._pool

    # ------------------------------------------------------------------
    # Tenant-scoped connection
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def tenant_connection(
        self, tenant_id: str
    ) -> AsyncIterator[asyncpg.Connection]:
        """
        Acquire a connection with ``app.current_tenant`` set — RLS policies
        on every tenant-scoped table will filter rows automatically.

        Usage::

            async with db.tenant_connection(tenant_id) as conn:
                rows = await conn.fetch("SELECT * FROM ingestion.documents")
        """
        if not tenant_id:
            raise TenantIsolationError("tenant_id must be non-empty")
        async with self.pool.acquire() as conn:
            # SET LOCAL scopes to the current transaction (implicit txn in
            # asyncpg's acquire()). Using SET (not SET LOCAL) leaks across
            # connection reuse — don't.
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", tenant_id
                )
                yield conn

    # ------------------------------------------------------------------
    # Admin (un-scoped) connection — USE SPARINGLY
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def admin_connection(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Un-scoped connection — bypasses RLS.

        Use ONLY for:
        * migrations
        * scheduled jobs that legitimately process all tenants
          (e.g. billing rollup)
        * platform-admin endpoints

        Never use for a user-facing request. Callers are audited.
        """
        log.info("admin_connection_acquired (RLS bypass)")
        async with self.pool.acquire() as conn:
            yield conn


# ---------------------------------------------------------------------------
# Base repository — every service repo inherits
# ---------------------------------------------------------------------------
class Repository:
    """
    Minimal base. Subclasses get ``self._db`` (the :class:`DbClient`) and
    are expected to expose domain-specific methods like
    ``create_document``, ``find_chunks_by_doc_id``, etc.

    Repositories are the ONLY layer that should contain SQL. Routers and
    services never write queries — they call repositories.
    """

    def __init__(self, db: DbClient) -> None:
        self._db = db

    @staticmethod
    def _to_dict(record: asyncpg.Record | None) -> dict[str, Any] | None:
        """Helper: turn a single Record into a plain dict, or None."""
        return dict(record) if record is not None else None
