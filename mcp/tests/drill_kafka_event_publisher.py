#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Kafka event-publisher Stage-1 contract.

Per CLAUDE.md §43 + §41.5 (event-driven) + §47 (Layer 8 Kafka bus).
Locks the contract that:

  - 4 publish_* helpers exist (policy / paperclip / openclaw / router)
  - Each helper builds a CloudEvents-shaped envelope with required fields
    (event_id, event_type, event_version, source_layer, timestamp_iso,
    correlation_id, payload)
  - Stage-1 opt-in: KAFKA_PUBLISH=1 enables; default is no-op stub
  - No-op stubs return {published: False, stub: True} so callers can
    distinguish "no-op by design" from "publish failed"
  - Each publish call generates a unique event_id (UUIDs)
  - 4 topic names match the documented architecture (documind.<layer>.<plural-noun>)
  - Module import is side-effect-free (no Kafka connection on import)
  - Failures don't raise — fail-open posture per §41.5

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: event_publisher imports + exports the 4 helpers + status --")
    # Reset env to ensure no-op default
    os.environ.pop("KAFKA_PUBLISH", None)
    import event_publisher  # noqa: E402
    for name in (
        "publish_policy_decision",
        "publish_paperclip_snapshot",
        "publish_openclaw_dispatch",
        "publish_router_classification",
        "status", "TOPICS", "_make_envelope",
    ):
        if not hasattr(event_publisher, name):
            print(f"x event_publisher.{name} missing")
            return 1
    print("  ok: 4 publishers + status + TOPICS + _make_envelope exported")

    print("-- 2. POSITIVE: 4 topics follow documind.<layer>.<noun> naming --")
    topics = event_publisher.TOPICS
    expected_topics = {
        "policy_decision": "documind.policy.decisions",
        "paperclip_snapshot": "documind.paperclip.snapshots",
        "openclaw_dispatch": "documind.openclaw.dispatches",
        "router_classification": "documind.router.classifications",
    }
    if topics != expected_topics:
        print(f"x topic names mismatch; expected {expected_topics}, got {topics}")
        return 1
    # Each topic must follow documind.<layer>.<noun> pattern
    for _k, v in topics.items():
        if not re.fullmatch(r"documind\.[a-z]+\.[a-z_]+", v):
            print(f"x topic {v!r} doesn't match documind.<layer>.<noun> pattern")
            return 1
    print("  ok: 4 topics with correct naming")

    print("-- 3. NEGATIVE: default behavior is no-op (KAFKA_PUBLISH unset → stub=True) --")
    # Re-import to reload module-level ENABLED flag
    import importlib
    importlib.reload(event_publisher)
    if event_publisher.ENABLED:
        print("x ENABLED should be False when KAFKA_PUBLISH is unset")
        return 1
    result = event_publisher.publish_policy_decision(
        decision={"test": True}, correlation_id="drill-test",
    )
    if result.get("published"):
        print("x default publish should be no-op; got published=True")
        return 1
    if not result.get("stub"):
        print(f"x default publish must set stub=True; got {result}")
        return 1
    if "kafka_disabled" not in result.get("reason", ""):
        print(f"x reason must cite kafka_disabled; got {result.get('reason')!r}")
        return 1
    print("  ok: default no-op posture; published=False; stub=True; reason cites kafka_disabled")

    print("-- 4. POSITIVE: each publish call generates a unique event_id --")
    ids = set()
    for _ in range(5):
        r = event_publisher.publish_router_classification(
            classification={"sample": True},
        )
        eid = r.get("event_id")
        if not eid:
            print(f"x publish must return event_id; got {r}")
            return 1
        ids.add(eid)
    if len(ids) != 5:
        print(f"x event_ids must be unique; got {len(ids)} distinct from 5 calls")
        return 1
    # event_ids must look like UUIDs (8-4-4-4-12)
    for eid in ids:
        if not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", eid):
            print(f"x event_id {eid!r} doesn't look like UUID")
            return 1
    print("  ok: 5 calls produced 5 distinct UUID event_ids")

    print("-- 5. NEGATIVE: envelope must include all 7 CloudEvents fields --")
    envelope = event_publisher._make_envelope(
        event_type="test_event_type",
        source_layer="test_layer",
        payload={"k": "v"},
    )
    required = {
        "event_id", "event_type", "event_version",
        "source_layer", "timestamp_iso", "correlation_id", "payload",
    }
    missing = required - set(envelope.keys())
    if missing:
        print(f"x envelope missing CloudEvents fields: {missing}")
        return 1
    # event_version must be an int (schema evolution per §41.5)
    if not isinstance(envelope["event_version"], int):
        print(f"x event_version must be int; got {type(envelope['event_version']).__name__}")
        return 1
    # timestamp_iso must look like ISO-8601 with timezone
    if not re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", envelope["timestamp_iso"]):
        print(f"x timestamp_iso wrong format: {envelope['timestamp_iso']!r}")
        return 1
    print("  ok: all 7 CloudEvents fields + event_version=int + ISO-8601 timestamp")

    print("-- 6. NEGATIVE: importing module does NOT connect to Kafka --")
    # Stage-1 contract: module import is cheap. The Kafka client is
    # only loaded when ENABLED + an actual publish fires. Drill via
    # subprocess to get a clean import.
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{SCRIPTS}'); "
         f"import time; t0 = time.time(); "
         f"import event_publisher; "
         f"print(f'IMPORT_OK {{(time.time() - t0):.3f}}')"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
        env={**os.environ, "KAFKA_PUBLISH": ""},  # ensure default
    )
    if proc.returncode != 0:
        print(f"x fresh import failed: {proc.stderr[:200]}")
        return 1
    if "IMPORT_OK" not in proc.stdout:
        print(f"x import sentinel missing: {proc.stdout[:200]}")
        return 1
    m = re.search(r"IMPORT_OK\s+([\d.]+)", proc.stdout)
    if m:
        elapsed = float(m.group(1))
        if elapsed > 2.0:
            print(f"x import took {elapsed:.3f}s; expected <2s (no kafka connect)")
            return 1
        print(f"  ok: import {elapsed:.3f}s; no Kafka connection on module load")
    else:
        print("  ok: import OK (timing not parsed)")

    print("-- 7. NEGATIVE: 4 publishers all use distinct topics --")
    # Bit-rot prevention: a refactor that accidentally points two
    # publishers at the same topic would cross-pollute event streams.
    used_topics = set()
    test_calls = (
        (event_publisher.publish_policy_decision, {"decision": {}}),
        (event_publisher.publish_paperclip_snapshot, {"snapshot_summary": {}}),
        (event_publisher.publish_openclaw_dispatch, {"dispatch_decision": {}}),
        (event_publisher.publish_router_classification, {"classification": {}}),
    )
    for fn, kwargs in test_calls:
        r = fn(**kwargs)
        topic = r.get("topic")
        if not topic:
            print(f"x publish result missing topic field: {r}")
            return 1
        if topic in used_topics:
            print(f"x topic {topic!r} used by multiple publishers")
            return 1
        used_topics.add(topic)
    if len(used_topics) != 4:
        print(f"x expected 4 distinct topics; got {len(used_topics)}")
        return 1
    print("  ok: 4 publishers use 4 distinct topics")

    print("-- 8. NEGATIVE: publish_* calls do NOT raise on stub mode --")
    # Fail-open posture per §41.5 — a publish failure must NEVER
    # block the originating decision. Stage-1 stubs always return
    # a dict; drill verifies no exception path.
    try:
        event_publisher.publish_policy_decision(decision={})
        event_publisher.publish_paperclip_snapshot(snapshot_summary={})
        event_publisher.publish_openclaw_dispatch(dispatch_decision={})
        event_publisher.publish_router_classification(classification={})
        # Edge cases: empty dict, None correlation, very long payload
        event_publisher.publish_policy_decision(
            decision={"x": "y" * 10_000}, correlation_id=None,
        )
    except Exception as exc:
        print(f"x publish helpers must NOT raise; got {exc!r}")
        return 1
    print("  ok: 5 publish calls (incl. edge cases) all returned without raising")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
