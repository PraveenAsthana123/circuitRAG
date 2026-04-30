"""
Tests for documind_core.db_client — asyncpg pool + tenant RLS context.

Covers:
- DbClient.__init__ stores config without opening a connection
- connect() creates the pool; idempotent on second call
- close() closes the pool and clears it
- pool property raises DataError if not connected (clear errors > NoneType)
- tenant_connection runs SET LOCAL app.current_tenant (RLS handshake)
- tenant_connection NEGATIVE: empty tenant_id raises
  TenantIsolationError before any DB call (catch the bug at the door)
- admin_connection skips the RLS handshake (intentional)
- Repository._to_dict converts Record → dict, None → None
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from documind_core.db_client import DbClient, Repository
from documind_core.exceptions import DataError, TenantIsolationError

# ── DbClient lifecycle ────────────────────────────────────────


class TestLifecycle:
    def test_init_does_not_connect(self) -> None:
        client = DbClient(dsn="postgresql://u:p@h:5432/d")
        # Pool only opens on connect(); init is cheap.
        assert client._pool is None  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_pool_property_before_connect_raises(self) -> None:
        client = DbClient(dsn="postgresql://u:p@h:5432/d")
        with pytest.raises(DataError, match="connect"):
            _ = client.pool

    @pytest.mark.asyncio
    async def test_connect_creates_pool(self) -> None:
        with patch("documind_core.db_client.asyncpg.create_pool", new=AsyncMock()) as mock_create:
            mock_create.return_value = MagicMock(name="pool")
            client = DbClient(dsn="dsn://", min_size=2, max_size=20)
            await client.connect()
            mock_create.assert_awaited_once()
            assert client._pool is not None  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_connect_is_idempotent(self) -> None:
        with patch("documind_core.db_client.asyncpg.create_pool", new=AsyncMock()) as mock_create:
            mock_create.return_value = MagicMock()
            client = DbClient(dsn="dsn://")
            await client.connect()
            await client.connect()
            # Second call must NOT open another pool — idempotency saves
            # us from accidental double-init in lifespan handlers.
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_clears_pool(self) -> None:
        client = DbClient(dsn="dsn://")
        pool_mock = MagicMock()
        pool_mock.close = AsyncMock()
        client._pool = pool_mock  # type: ignore[attr-defined]
        await client.close()
        pool_mock.close.assert_awaited_once()
        assert client._pool is None  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_close_when_never_connected_is_noop(self) -> None:
        client = DbClient(dsn="dsn://")
        await client.close()  # no exception


# ── tenant_connection ─────────────────────────────────────────


class TestTenantConnection:
    @pytest.mark.asyncio
    async def test_empty_tenant_id_rejected(self) -> None:
        # NEGATIVE: catch the bug at the door — empty tenant must NOT
        # leak into a query where RLS would silently match nothing.
        client = DbClient(dsn="dsn://")
        with pytest.raises(TenantIsolationError):
            async with client.tenant_connection(""):
                pass

    @pytest.mark.asyncio
    async def test_sets_current_tenant_via_set_config(self) -> None:
        # The handshake: every tenant-scoped query flows through this
        # path. A regression here defeats RLS.
        client = DbClient(dsn="dsn://")
        conn = MagicMock()
        conn.execute = AsyncMock()

        @asynccontextmanager
        async def fake_txn():
            yield None

        conn.transaction = fake_txn

        @asynccontextmanager
        async def fake_acquire():
            yield conn

        pool = MagicMock()
        pool.acquire = fake_acquire
        client._pool = pool  # type: ignore[attr-defined]

        async with client.tenant_connection("tnt-42"):
            pass
        # The tenant ID must have flowed into set_config.
        called_sql, called_arg = conn.execute.await_args[0]
        assert "set_config" in called_sql
        assert "app.current_tenant" in called_sql
        assert called_arg == "tnt-42"


# ── admin_connection ──────────────────────────────────────────


class TestAdminConnection:
    @pytest.mark.asyncio
    async def test_no_set_config_call(self) -> None:
        # Admin connection MUST NOT issue the RLS handshake — by design,
        # this is the un-scoped path.
        client = DbClient(dsn="dsn://")
        conn = MagicMock()
        conn.execute = AsyncMock()

        @asynccontextmanager
        async def fake_acquire():
            yield conn

        pool = MagicMock()
        pool.acquire = fake_acquire
        client._pool = pool  # type: ignore[attr-defined]

        async with client.admin_connection():
            pass
        # Zero execute calls in the wrapper itself — caller drives the
        # SQL directly.
        conn.execute.assert_not_called()


# ── Repository helpers ────────────────────────────────────────


class TestRepository:
    def test_to_dict_with_record(self) -> None:
        # asyncpg.Record is dict-compatible; dict(rec) is the canonical
        # way to materialize it for response serialization.
        record = {"id": 1, "name": "x"}
        assert Repository._to_dict(record) == {"id": 1, "name": "x"}

    def test_to_dict_with_none(self) -> None:
        # SELECT-zero-rows must NOT crash; None → None passes through.
        assert Repository._to_dict(None) is None

    def test_init_stores_db(self) -> None:
        db = DbClient(dsn="dsn://")
        repo = Repository(db)
        assert repo._db is db  # type: ignore[attr-defined]
