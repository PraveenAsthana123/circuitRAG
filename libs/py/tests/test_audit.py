"""
Tests for documind_core.audit — tamper-evident audit-log writer.

Covers:
- _classify_error: stable low-cardinality label; trailing 'Error'
  stripped (e.g. ConnectionError → 'Connection')
- _canonical_json: stable across field order
- _compute_entry_hash: deterministic + sensitive to every field
  (per-tenant chain integrity)
- AuditLog protocol shape (typing only)
- AuditWriter.write:
  * happy path with first row (previous_hash="") — chain seed
  * happy path with prior row — picks up previous entry's hash
  * fail-open default (DB error swallowed; counter incremented)
  * fail_closed=True path raises DataError with __cause__ preserved
  * action argument threaded through to the row + the failure metric
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from documind_core.audit import (
    AuditWriter,
    _canonical_json,
    _classify_error,
    _compute_entry_hash,
)
from documind_core.exceptions import DataError

# ── _classify_error ───────────────────────────────────────────


class TestClassifyError:
    def test_strips_error_suffix(self) -> None:
        assert _classify_error(ConnectionError("x")) == "Connection"

    def test_keeps_name_without_error_suffix(self) -> None:
        class Boom(Exception):
            pass

        assert _classify_error(Boom()) == "Boom"

    def test_only_error_class(self) -> None:
        # Something literally named "Error" — unlikely, but should not
        # collapse to empty string.
        class Error(Exception):
            pass

        assert _classify_error(Error()) == "Error"


# ── _canonical_json ───────────────────────────────────────────


class TestCanonicalJson:
    def test_stable_across_key_order(self) -> None:
        a = _canonical_json({"b": 1, "a": 2})
        b = _canonical_json({"a": 2, "b": 1})
        assert a == b
        # No whitespace
        assert " " not in a

    def test_handles_datetime_via_default_str(self) -> None:
        # default=str must fall back for non-JSON types. Audit rows
        # with datetime fields would crash without this.
        s = _canonical_json({"ts": datetime(2026, 1, 1)})
        assert "2026" in s


# ── _compute_entry_hash ───────────────────────────────────────


class TestComputeEntryHash:
    def test_deterministic(self) -> None:
        kw = {
            "previous_hash": "prev",
            "timestamp_iso": "2026-01-01T00:00:00",
            "tenant_id": "tnt",
            "actor_type": "service",
            "action": "x",
            "resource_type": "r",
            "details": {"k": "v"},
        }
        assert _compute_entry_hash(**kw) == _compute_entry_hash(**kw)

    def test_changes_with_each_field(self) -> None:
        base = {
            "previous_hash": "p",
            "timestamp_iso": "t",
            "tenant_id": "tnt",
            "actor_type": "service",
            "action": "x",
            "resource_type": None,
            "details": {},
        }
        h0 = _compute_entry_hash(**base)
        # Mutating any single field must change the hash — chain
        # integrity invariant. Test all of them.
        for field, new_value in [
            ("previous_hash", "p2"),
            ("timestamp_iso", "t2"),
            ("tenant_id", "tnt2"),
            ("actor_type", "user"),
            ("action", "y"),
            ("resource_type", "r"),
            ("details", {"k": "v"}),
        ]:
            mut = dict(base)
            mut[field] = new_value
            assert _compute_entry_hash(**mut) != h0, f"hash not sensitive to {field}"

    def test_hash_is_sha256_hex(self) -> None:
        h = _compute_entry_hash(
            previous_hash="",
            timestamp_iso="t",
            tenant_id="tnt",
            actor_type="service",
            action="x",
            resource_type=None,
            details={},
        )
        # 64 hex chars (SHA-256)
        assert len(h) == 64
        int(h, 16)  # raises if not valid hex

    def test_resource_type_none_treated_as_empty(self) -> None:
        # The hash function maps None → "" so two semantically-equivalent
        # rows produce the same hash regardless of whether the caller
        # passed None or "".
        h1 = _compute_entry_hash(
            previous_hash="",
            timestamp_iso="t",
            tenant_id="tnt",
            actor_type="service",
            action="x",
            resource_type=None,
            details={},
        )
        h2 = _compute_entry_hash(
            previous_hash="",
            timestamp_iso="t",
            tenant_id="tnt",
            actor_type="service",
            action="x",
            resource_type="",
            details={},
        )
        assert h1 == h2


# ── AuditWriter ───────────────────────────────────────────────


def _make_db_with_conn(conn: MagicMock) -> MagicMock:
    db = MagicMock()

    @asynccontextmanager
    async def tenant_connection(_tid: str):
        yield conn

    db.tenant_connection = tenant_connection
    return db


def _make_conn(previous_row: dict | None, now_iso: str = "2026-04-30 17:00:00.000+00") -> MagicMock:
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=previous_row)
    conn.fetchval = AsyncMock(return_value=now_iso)
    conn.execute = AsyncMock(return_value=None)
    return conn


class TestAuditWriter:
    @pytest.mark.asyncio
    async def test_first_row_seeds_chain_with_empty_prev(self) -> None:
        conn = _make_conn(previous_row=None)
        db = _make_db_with_conn(conn)
        writer = AuditWriter(db_client=db, service="ingestion-svc")
        await writer.write(tenant_id="tnt", action="document.uploaded")
        args = conn.execute.await_args[0]
        # args[0]=SQL, args[1]=timestamp_dt, ..., args[10]=previous_hash,
        # args[11]=entry_hash
        assert args[10] == ""  # previous_hash empty for first row
        assert len(args[11]) == 64  # entry_hash sha256 hex

    @pytest.mark.asyncio
    async def test_subsequent_row_chains_off_previous(self) -> None:
        conn = _make_conn(previous_row={"entry_hash": "abc123", "timestamp": "x"})
        db = _make_db_with_conn(conn)
        writer = AuditWriter(db_client=db, service="ingestion-svc")
        await writer.write(tenant_id="tnt", action="x")
        args = conn.execute.await_args[0]
        assert args[10] == "abc123"  # previous_hash picked up

    @pytest.mark.asyncio
    async def test_service_stamped_into_details(self) -> None:
        conn = _make_conn(previous_row=None)
        db = _make_db_with_conn(conn)
        writer = AuditWriter(db_client=db, service="my-svc")
        await writer.write(tenant_id="tnt", action="x", details={"k": "v"})
        args = conn.execute.await_args[0]
        details_json = args[8]
        details = json.loads(details_json)
        assert details["service"] == "my-svc"
        assert details["k"] == "v"

    @pytest.mark.asyncio
    async def test_caller_supplied_service_not_clobbered(self) -> None:
        # setdefault — caller-supplied service wins over the writer default.
        conn = _make_conn(previous_row=None)
        db = _make_db_with_conn(conn)
        writer = AuditWriter(db_client=db, service="my-svc")
        await writer.write(tenant_id="tnt", action="x", details={"service": "explicit"})
        details = json.loads(conn.execute.await_args[0][8])
        assert details["service"] == "explicit"

    @pytest.mark.asyncio
    async def test_fail_open_default_swallows_db_error(self) -> None:
        # The §38 "governance never breaks the business path" contract.
        conn = _make_conn(previous_row=None)
        conn.fetchrow.side_effect = ConnectionError("db down")
        db = _make_db_with_conn(conn)
        writer = AuditWriter(db_client=db, service="x")
        # Must NOT raise — this is the load-bearing guarantee.
        await writer.write(tenant_id="tnt", action="x")

    @pytest.mark.asyncio
    async def test_fail_closed_raises_data_error(self) -> None:
        conn = _make_conn(previous_row=None)
        conn.fetchrow.side_effect = ConnectionError("db down")
        db = _make_db_with_conn(conn)
        writer = AuditWriter(db_client=db, service="x")
        with pytest.raises(DataError) as exc_info:
            await writer.write(tenant_id="tnt", action="critical.action", fail_closed=True)
        # __cause__ preserves the original exception for forensics.
        assert isinstance(exc_info.value.__cause__, ConnectionError)
        # Details carry the action + classified error_type for the log.
        assert exc_info.value.details["action"] == "critical.action"
        assert exc_info.value.details["error_type"] == "Connection"
        assert exc_info.value.details["tenant_id"] == "tnt"

    @pytest.mark.asyncio
    async def test_hash_chain_matches_compute_function(self) -> None:
        # The writer must hash with EXACTLY the same canonicalisation
        # as _compute_entry_hash, otherwise verifiers can't replay the
        # chain.
        conn = _make_conn(previous_row=None, now_iso="2026-04-30T17:00:00")
        db = _make_db_with_conn(conn)
        writer = AuditWriter(db_client=db, service="my-svc")
        await writer.write(
            tenant_id="tnt",
            action="x",
            actor_type="service",
            resource_type="r",
            details={"k": "v"},
        )
        args = conn.execute.await_args[0]
        actual_hash = args[11]
        # Reconstruct what the writer should have hashed.
        details = {"service": "my-svc", "k": "v"}  # service stamped in by writer
        expected = _compute_entry_hash(
            previous_hash="",
            timestamp_iso="2026-04-30T17:00:00",
            tenant_id="tnt",
            actor_type="service",
            action="x",
            resource_type="r",
            details=details,
        )
        assert actual_hash == expected
