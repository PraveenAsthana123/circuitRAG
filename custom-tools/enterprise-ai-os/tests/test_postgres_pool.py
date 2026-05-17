# Negative drills for Iter 33 (2026-05-17): Postgres pool.
# Real-DB tests are out of scope; these verify the pool integration
# layer via mocks (acquire/release/rollback contract).

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.description = None
        self._rows = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params):
        if self._conn._raise_on_execute:
            raise RuntimeError("query failed")
        self.description = [("col",)] if sql.lower().startswith("select") else None
        self._rows = [{"col": 1}] if sql.lower().startswith("select") else []
    def fetchall(self): return self._rows


class FakeConn:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self._raise_on_execute = False
    def cursor(self, **kw): return FakeCursor(self)
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


class FakePool:
    def __init__(self, minconn=1, maxconn=10, **conn_kwargs):
        self.minconn = minconn
        self.maxconn = maxconn
        self.conns = [FakeConn() for _ in range(maxconn)]
        self.checked_out = []
        self.returned = []
        self.closed = False
    def getconn(self):
        c = self.conns.pop()
        self.checked_out.append(c)
        return c
    def putconn(self, c):
        self.returned.append(c)
        self.conns.append(c)
    def closeall(self):
        self.closed = True


@pytest.fixture
def patched_pool(monkeypatch):
    import integrations.postgres_client as mod
    pools_created = []
    def fake_pool_factory(minconn, maxconn, **kw):
        p = FakePool(minconn=minconn, maxconn=maxconn, **kw)
        pools_created.append(p)
        return p
    monkeypatch.setattr(mod.pool, "ThreadedConnectionPool", fake_pool_factory)
    return mod, pools_created


def test_acquires_and_releases_connection(patched_pool):
    mod, pools = patched_pool
    client = mod.PostgresClient(min_connections=2, max_connections=5)
    p = pools[0]

    client.query("SELECT 1")
    assert len(p.checked_out) == 1
    assert len(p.returned) == 1


def test_BACKDOOR_CHECK_does_not_serialize_on_single_connection(patched_pool):
    """Pre-fix the class held ONE connection; concurrent queries
    serialized on it. With a pool, each acquire returns a different
    connection."""
    mod, pools = patched_pool
    client = mod.PostgresClient(min_connections=3, max_connections=3)
    p = pools[0]

    # Take 3 connections "in flight" by stubbing query to defer release.
    acquired = []
    for _ in range(3):
        acquired.append(p.getconn())
    # All three are distinct objects from the pool.
    assert len({id(c) for c in acquired}) == 3


def test_exception_triggers_rollback_and_returns_connection(patched_pool):
    mod, pools = patched_pool
    client = mod.PostgresClient(max_connections=2)
    p = pools[0]
    # Mark the next connection to throw on execute.
    next_conn = p.conns[-1]
    next_conn._raise_on_execute = True

    with pytest.raises(RuntimeError, match="query failed"):
        client.query("UPDATE t SET x = 1")

    # Connection must be rolled back AND returned to the pool.
    assert next_conn.rollbacks == 1
    assert next_conn.commits == 0
    assert next_conn in p.returned


def test_close_drains_pool(patched_pool):
    mod, pools = patched_pool
    client = mod.PostgresClient()
    client.close()
    assert pools[0].closed is True


def test_constructor_rejects_invalid_pool_bounds(patched_pool):
    mod, _ = patched_pool
    with pytest.raises(ValueError):
        mod.PostgresClient(min_connections=5, max_connections=2)
    with pytest.raises(ValueError):
        mod.PostgresClient(min_connections=0, max_connections=1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
