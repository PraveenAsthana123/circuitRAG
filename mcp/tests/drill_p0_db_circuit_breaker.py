#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for P0 #36 — DbCircuitBreaker wraps DbClient (postgres_store.py).

Verifies:
  - DbCircuitBreaker class exists and uses canonical CircuitBreaker
  - Failure counts after 3 consecutive errors → state OPEN
  - guarded_admin_connection raises CircuitOpenError when OPEN
  - is_healthy / state expose status for /health/ready
  - On query exception, breaker records failure (not just connect)

Negative assertions:
  - 3 connect failures → breaker OPEN
  - When OPEN, guarded_admin_connection raises CircuitOpenError fast
    (no asyncpg call attempted)
  - Successful query in HALF_OPEN → CLOSED transition
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"


def _load_dbcb():
    sys.path.insert(0, str(REPO / "libs" / "py"))
    spec = importlib.util.spec_from_file_location(
        "p0c_dbcb", SVC / "app" / "db_circuit_breaker.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["p0c_dbcb"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeDb:
    """Stand-in for DbClient with controllable failure modes."""

    def __init__(self, *, fail_connect: int = 0, fail_query: int = 0):
        self.fail_connect = fail_connect
        self.fail_query = fail_query
        self.connect_calls = 0
        self.admin_calls = 0

    async def connect(self):
        self.connect_calls += 1
        if self.fail_connect > 0:
            self.fail_connect -= 1
            raise ConnectionError("fake postgres connect failed")

    @asynccontextmanager
    async def admin_connection(self):
        self.admin_calls += 1
        if self.fail_query > 0:
            self.fail_query -= 1
            raise ConnectionError("fake postgres query failed")
        yield FakeConn()


class FakeConn:
    async def execute(self, *_args, **_kwargs):
        return None
    async def fetch(self, *_args, **_kwargs):
        return []


def main() -> int:
    mod = _load_dbcb()
    DbCircuitBreaker = mod.DbCircuitBreaker
    from documind_core.circuit_breaker import CircuitOpenError

    print("-- 1. POSITIVE: DbCircuitBreaker initialises with canonical breaker --")
    cb = DbCircuitBreaker(name="test-db", failure_threshold=3, recovery_timeout=0.1)
    assert cb.state == "closed"
    assert cb.is_healthy is True
    print("  ok: state=closed, is_healthy=True")

    print("-- 2. NEGATIVE: 3 consecutive connect failures → OPEN --")
    cb = DbCircuitBreaker(name="trip-test", failure_threshold=3, recovery_timeout=10)
    db = FakeDb(fail_connect=3)
    for _ in range(3):
        try:
            asyncio.run(cb.connect_with_breaker(db))
        except (ConnectionError, CircuitOpenError):
            pass
    assert cb.state == "open", f"expected OPEN; got {cb.state}"
    assert cb.is_healthy is False
    print("  ok: 3 connect failures → state=OPEN, is_healthy=False")

    print("-- 3. NEGATIVE: when OPEN, guarded_admin_connection fast-fails --")
    db_healthy = FakeDb()  # would succeed if called
    raised_cb = False
    async def _try():
        async with cb.guarded_admin_connection(db_healthy) as _:
            pass
    try:
        asyncio.run(_try())
    except CircuitOpenError as exc:
        raised_cb = True
        assert exc.details.get("state") == "open"
    assert raised_cb, "P0 #36 BROKEN: OPEN breaker should fast-fail (no asyncpg call)"
    assert db_healthy.admin_calls == 0, (
        f"P0 #36 BROKEN: admin_connection was called despite OPEN breaker "
        f"(admin_calls={db_healthy.admin_calls})"
    )
    print("  ok: OPEN → CircuitOpenError raised; underlying db.admin_connection NOT called")

    print("-- 4. POSITIVE: query exception inside guarded_admin records failure --")
    cb = DbCircuitBreaker(name="query-fail", failure_threshold=2, recovery_timeout=10)
    db = FakeDb(fail_query=2)
    for _ in range(2):
        async def _q():
            async with cb.guarded_admin_connection(db) as _:
                pass
        try:
            asyncio.run(_q())
        except (ConnectionError, CircuitOpenError):
            pass
    assert cb.state == "open", (
        f"P0 #36 BROKEN: 2 query failures should trip CB; state={cb.state}"
    )
    print("  ok: query exceptions surface to breaker; state=OPEN after threshold")

    print("-- 5. POSITIVE: HALF_OPEN → success → CLOSED transition --")
    import time
    cb = DbCircuitBreaker(name="recovery", failure_threshold=1, recovery_timeout=0.05)
    db = FakeDb(fail_query=1)
    async def _q():
        async with cb.guarded_admin_connection(db) as _:
            pass
    try:
        asyncio.run(_q())
    except (ConnectionError, CircuitOpenError):
        pass
    assert cb.state == "open"
    time.sleep(0.1)  # recovery elapses

    # Successful call should transition OPEN → HALF_OPEN → CLOSED.
    db_ok = FakeDb()
    asyncio.run(_q.__call__()) if False else None  # placeholder
    async def _q2():
        async with cb.guarded_admin_connection(db_ok) as _:
            pass
    asyncio.run(_q2())
    assert cb.state == "closed", f"expected CLOSED after recovery; got {cb.state}"
    print("  ok: OPEN → recovery elapses → success → CLOSED")

    print("-- 6. POSITIVE: is_healthy property reflects state for /health/ready --")
    # Used by /health/ready to decide 200 vs 503.
    cb = DbCircuitBreaker(name="health-flag", failure_threshold=1, recovery_timeout=10)
    assert cb.is_healthy is True
    db = FakeDb(fail_connect=1)
    try:
        asyncio.run(cb.connect_with_breaker(db))
    except ConnectionError:
        pass
    assert cb.is_healthy is False, (
        "P0 #36 BROKEN: is_healthy did not flip False after trip"
    )
    print("  ok: is_healthy → False on OPEN, True on CLOSED")

    print()
    print("ALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
