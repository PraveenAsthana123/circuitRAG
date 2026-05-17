# Test script from Tool Set 36 §4 — reformatted as a runnable pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.immutable_audit_store import ImmutableAuditStore
from audit.audit_exporter import AuditExporter


def test_hash_chain_round_trip():
    store = ImmutableAuditStore()
    exporter = AuditExporter()

    store.append(
        trace_id="trace_001",
        actor="runtime",
        event_type="session_started",
        payload={"session_id": "session_001"}
    )

    store.append(
        trace_id="trace_001",
        actor="governance_agent",
        event_type="policy_checked",
        payload={"policy_passed": True}
    )

    store.append(
        trace_id="trace_001",
        actor="council",
        event_type="vote_completed",
        payload={"decision": "approved"}
    )

    verification = store.verify_integrity()
    assert verification["valid"] is True
    assert verification["records_checked"] == 3

    exported = exporter.export_by_trace("trace_001", store.list_records())
    assert "trace_001" in exported


def test_list_records_returns_defensive_copies():
    store = ImmutableAuditStore()
    record = store.append(
        trace_id="trace_copy",
        actor="runtime",
        event_type="session_started",
        payload={"session_id": "session_001"}
    )

    record["payload"]["trace_id"] = "tampered"
    listed = store.list_records()
    listed[0]["payload"]["trace_id"] = "tampered_again"

    assert store.search_by_trace("trace_copy")[0]["payload"]["trace_id"] == "trace_copy"
    assert store.verify_integrity()["valid"] is True


if __name__ == "__main__":
    test_hash_chain_round_trip()
    print("OK")
