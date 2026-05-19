# Audit tests (Tool Set 36 §4 + Iter 14 additions for tenant filter + retention).

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.immutable_audit_store import (
    ImmutableAuditStore,
    AuditAccessDeniedError,
)
from audit.audit_exporter import AuditExporter


def test_hash_chain_round_trip():
    store = ImmutableAuditStore()
    exporter = AuditExporter()

    store.append(trace_id="trace_001", actor="runtime",
                 event_type="session_started",
                 payload={"session_id": "session_001"},
                 tenant_id="tenant-A")
    store.append(trace_id="trace_001", actor="governance_agent",
                 event_type="policy_checked",
                 payload={"policy_passed": True},
                 tenant_id="tenant-A")
    store.append(trace_id="trace_001", actor="council",
                 event_type="vote_completed",
                 payload={"decision": "approved"},
                 tenant_id="tenant-A")

    verification = store.verify_integrity()
    assert verification["valid"] is True
    assert verification["records_checked"] == 3

    exported = exporter.export_by_trace(
        "trace_001",
        store.list_records(caller_tenant_id="tenant-A"),
    )
    assert "trace_001" in exported


def test_verify_integrity_reports_all_failed_records():
    store = ImmutableAuditStore()
    store.append(trace_id="t", actor="r", event_type="e",
                 payload={"n": 1}, tenant_id="tenant-A")
    store.append(trace_id="t", actor="r", event_type="e",
                 payload={"n": 2}, tenant_id="tenant-A")
    store.append(trace_id="t", actor="r", event_type="e",
                 payload={"n": 3}, tenant_id="tenant-A")

    store._records[0]["payload"]["payload"]["n"] = 99
    store._records[2]["previous_hash"] = "tampered-previous"
    store._records[2]["current_hash"] = "tampered-current"

    verification = store.verify_integrity()

    assert verification["valid"] is False
    assert verification["records_checked"] == 3
    assert verification["failed_index"] == 0
    assert [failure["index"] for failure in verification["failures"]] == [0, 2]
    assert verification["failures"][0]["reasons"] == ["current_hash_mismatch"]
    assert set(verification["failures"][1]["reasons"]) == {
        "previous_hash_mismatch", "current_hash_mismatch",
    }


def test_list_records_returns_defensive_copies():
    store = ImmutableAuditStore()
    record = store.append(
        trace_id="trace_copy", actor="runtime",
        event_type="session_started",
        payload={"session_id": "session_001"},
        tenant_id="tenant-A",
    )

    record["payload"]["trace_id"] = "tampered"
    listed = store.list_records(caller_tenant_id="tenant-A")
    listed[0]["payload"]["trace_id"] = "tampered_again"

    found = store.search_by_trace("trace_copy", caller_tenant_id="tenant-A")
    assert found[0]["payload"]["trace_id"] == "trace_copy"
    assert store.verify_integrity()["valid"] is True


# ---------- Iter 14: tenant filter (P0) ----------

def test_list_records_filters_by_tenant():
    """BACKDOOR CHECK: pre-fix list_records returned ALL records."""
    store = ImmutableAuditStore()
    store.append(trace_id="t1", actor="r", event_type="e",
                 payload={"k": "v1"}, tenant_id="tenant-A")
    store.append(trace_id="t2", actor="r", event_type="e",
                 payload={"k": "v2"}, tenant_id="tenant-B")

    a_view = store.list_records(caller_tenant_id="tenant-A")
    b_view = store.list_records(caller_tenant_id="tenant-B")
    assert len(a_view) == 1
    assert len(b_view) == 1
    # Audit row nests user payload under payload.payload (outer is
    # the audit envelope; inner is the user-supplied dict).
    assert a_view[0]["payload"]["payload"]["k"] == "v1"
    assert b_view[0]["payload"]["payload"]["k"] == "v2"


def test_search_by_trace_filters_by_tenant():
    """Same trace_id used across tenants — must be isolated."""
    store = ImmutableAuditStore()
    store.append(trace_id="trace_shared", actor="r", event_type="e",
                 payload={"who": "A"}, tenant_id="tenant-A")
    store.append(trace_id="trace_shared", actor="r", event_type="e",
                 payload={"who": "B"}, tenant_id="tenant-B")

    a_view = store.search_by_trace("trace_shared", caller_tenant_id="tenant-A")
    assert len(a_view) == 1
    assert a_view[0]["payload"]["payload"]["who"] == "A"


def test_empty_caller_tenant_id_rejected():
    """A blank caller_tenant_id must NOT be treated as 'global read'."""
    store = ImmutableAuditStore()
    store.append(trace_id="t1", actor="r", event_type="e",
                 payload={}, tenant_id="tenant-A")
    with pytest.raises(AuditAccessDeniedError):
        store.list_records(caller_tenant_id="")
    with pytest.raises(AuditAccessDeniedError):
        store.search_by_trace("t1", caller_tenant_id="")


def test_append_requires_tenant_id():
    store = ImmutableAuditStore()
    with pytest.raises(ValueError, match="tenant_id is required"):
        store.append(trace_id="t1", actor="r", event_type="e",
                     payload={}, tenant_id="")


# ---------- Iter 14: retention (P1) ----------

def test_purge_expired_removes_old_records_and_rebuilds_chain():
    store = ImmutableAuditStore(retention_days=30)
    # Insert 3 records; the test fixture-injects an old created_at on
    # the first two to fake "they are 40 days old".
    r1 = store.append(trace_id="t", actor="r", event_type="e",
                      payload={"n": 1}, tenant_id="tenant-A")
    r2 = store.append(trace_id="t", actor="r", event_type="e",
                      payload={"n": 2}, tenant_id="tenant-A")
    r3 = store.append(trace_id="t", actor="r", event_type="e",
                      payload={"n": 3}, tenant_id="tenant-A")
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    # Direct manipulation for test (purposeful — production code never
    # mutates _records, but the test needs to fake aging).
    store._records[0]["payload"]["created_at"] = old
    store._records[1]["payload"]["created_at"] = old

    purged = store.purge_expired()
    assert purged == 2
    survivors = store.list_records(caller_tenant_id="tenant-A")
    assert len(survivors) == 1
    assert survivors[0]["payload"]["payload"] == {"n": 3}

    # Verify the chain rebuilt correctly so future appends still work.
    assert store.verify_integrity()["valid"] is True
    store.append(trace_id="t", actor="r", event_type="e",
                 payload={"n": 4}, tenant_id="tenant-A")
    assert store.verify_integrity()["valid"] is True


def test_constructor_rejects_zero_retention():
    with pytest.raises(ValueError):
        ImmutableAuditStore(retention_days=0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
