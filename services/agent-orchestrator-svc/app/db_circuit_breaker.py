"""Circuit breaker around the Postgres data layer.

P0 #36 fix from per-tool review (postgres-task-store.md):

    Pre-fix: Postgres outage = every endpoint returns 500. No graceful
    degradation; no /health/ready signal; K8s can't redirect traffic.
    Fix: wrap DbClient operations with a CircuitBreaker. When OPEN,
    callers see CircuitOpenError (typed) instead of asyncpg's connection
    error; service /health/ready can return 503 so K8s routes traffic
    elsewhere. Calls are recorded with cost (always 0 for DB) and the
    breaker emits standard documind_circuit_breaker_* metrics.

Usage:
    cb = DbCircuitBreaker(name="orchestrator-db")
    db = DbClient(dsn=...)
    await cb.connect_with_breaker(db)  # runs db.connect() through CB

    async with cb.guarded_admin_connection(db) as conn:
        await conn.execute(...)
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from documind_core.circuit_breaker import CircuitBreaker, CircuitOpenError

if TYPE_CHECKING:
    import asyncpg  # noqa: F401

log = logging.getLogger("orchestrator.db_circuit_breaker")


class DbCircuitBreaker:
    """Wraps DbClient with a CircuitBreaker. Failures (asyncpg / connect /
    timeout) trip the breaker; subsequent calls fail fast with
    CircuitOpenError until recovery_timeout elapses.

    Defaults are conservative for a database (failure_threshold=3,
    recovery_timeout=10s). Operators can override per-environment.
    """

    def __init__(
        self,
        *,
        name: str = "postgres",
        failure_threshold: int = 3,
        recovery_timeout: float = 10.0,
        call_timeout_s: float = 5.0,
    ) -> None:
        # Import here to keep module-level deps minimal.
        try:
            import asyncpg  # type: ignore[import-untyped]
            db_exceptions: tuple[type[BaseException], ...] = (
                asyncpg.PostgresConnectionError,
                asyncpg.exceptions.ConnectionDoesNotExistError,
                ConnectionError,
                OSError,
                TimeoutError,
            )
        except ImportError:  # pragma: no cover
            db_exceptions = (ConnectionError, OSError, TimeoutError)

        self._cb = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=db_exceptions,
            call_timeout_s=call_timeout_s,
            half_open_success_threshold=1,
        )

    @property
    def state(self) -> str:
        return self._cb.state.value

    @property
    def is_healthy(self) -> bool:
        """True iff the breaker is CLOSED. Used by /health/ready to
        decide 200 vs 503."""
        return self._cb.allow() and self._cb.state.value == "closed"

    async def connect_with_breaker(self, db) -> None:
        """Run db.connect() through the breaker. On failure, the
        breaker counts it; subsequent attempts fail fast until
        recovery_timeout elapses."""
        await self._cb.call_async(db.connect)

    @asynccontextmanager
    async def guarded_admin_connection(self, db) -> AsyncIterator[Any]:
        """Wrap db.admin_connection() with the breaker. The breaker check
        happens BEFORE acquisition; once acquired, the caller's queries
        run unguarded (they can use their own per-statement timeouts).

        On asyncpg-class errors during query execution, the caller
        should call breaker.record_failure() + raise — this gives the
        breaker visibility into runtime errors, not just connect ones.
        """
        if not self._cb.allow():
            raise CircuitOpenError(
                f"DB circuit '{self._cb.name}' OPEN — Postgres degraded",
                details={"name": self._cb.name, "state": self._cb.state.value},
            )
        try:
            async with db.admin_connection() as conn:
                yield conn
            self._cb.record_success()
        except Exception as exc:  # noqa: BLE001
            self._cb.record_failure(exc)
            raise

    @asynccontextmanager
    async def guarded_tenant_connection(self, db, tenant_id: str) -> AsyncIterator[Any]:
        """Same as guarded_admin_connection but for tenant-scoped reads."""
        if not self._cb.allow():
            raise CircuitOpenError(
                f"DB circuit '{self._cb.name}' OPEN — Postgres degraded",
                details={"name": self._cb.name, "state": self._cb.state.value},
            )
        try:
            async with db.tenant_connection(tenant_id) as conn:
                yield conn
            self._cb.record_success()
        except Exception as exc:  # noqa: BLE001
            self._cb.record_failure(exc)
            raise

    async def aclose(self) -> None:
        """Close the underlying breaker (release subprocess clients,
        flush metrics)."""
        # CircuitBreaker has no close (no async resources). Future:
        # if persistent_store is wired, flush its connection here.
        return None
