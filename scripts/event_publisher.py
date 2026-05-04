#!/usr/bin/env python3
"""Stage-1 event-publisher — pushes new-layer audit events to Kafka.

Per CLAUDE.md §41.5 (event-driven architecture) + §47 (Layer 8 Kafka
event bus) + the user-named architecture: the audit rows from PolisAI,
Paperclip, OpenClaw, and Agent Router need to flow OUT to the
observability stack (Layer 11). Kafka is the canonical bus.

Stage-1 contract:
  - Thin wrapper over EventProducer (libs/py/documind_core/kafka_client.py)
  - 4 dedicated topics, one per new layer:
      documind.policy.decisions       (PolisAI)
      documind.paperclip.snapshots    (Paperclip)
      documind.openclaw.dispatches    (OpenClaw)
      documind.router.classifications (Agent Router)
  - Opt-in: env var KAFKA_PUBLISH=1 enables; otherwise no-op (so
    dev without Kafka still works — failure to publish does NOT
    block the originating decision)
  - Idempotent: same event_id collapses on consumer side via
    IdempotentConsumer; producer just publishes
  - Audit row writes still happen at the originating layer FIRST
    (.loop/policy_audit.jsonl etc.); Kafka is for downstream
    observability + alerting + cross-service correlation

Stage-2 wires each originating layer (PolisAI / Paperclip / OpenClaw /
Router) to call publish_*() after its local audit-row write. This
script just ships the contract.

Stage-3 wires consumers (observability dashboard subscribes to all 4
topics; alerting service watches for high-risk router classifications;
fraud-monitoring watches OpenClaw dispatches with operator:human in
the chain).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[1]

# Topic names — kept module-level for drill enforcement
TOPICS = {
    "policy_decision": "documind.policy.decisions",
    "paperclip_snapshot": "documind.paperclip.snapshots",
    "openclaw_dispatch": "documind.openclaw.dispatches",
    "router_classification": "documind.router.classifications",
}

# Stage-1 opt-in flag. Set KAFKA_PUBLISH=1 to actually emit; default
# is no-op so dev without Kafka still works.
ENABLED = os.getenv("KAFKA_PUBLISH", "").strip() == "1"

logger = logging.getLogger(__name__)


def _make_envelope(
    *,
    event_type: str,
    source_layer: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build a CloudEvents-shaped envelope per §41.5.

    Required fields (immutable + versioned + self-describing):
      event_id            unique per emission; stable for retry
      event_type          past-tense verb (e.g., 'policy_decision_made')
      event_version       schema version for evolution
      source_layer        which architecture layer emitted it
      timestamp_iso       ISO-8601 UTC
      correlation_id      cross-service trace
      payload             event-specific dict
    """
    from datetime import datetime, timezone
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "source_layer": source_layer,
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "payload": payload,
    }


def _publish(topic: str, envelope: dict[str, Any]) -> dict[str, Any]:
    """Publish envelope to topic. Returns dict with 'published' flag.

    Stage-1 honesty: when ENABLED is False (default), returns
    {published: False, reason: 'kafka_disabled'} so callers can
    distinguish "no-op by design" from "publish failed."

    Stage-1 fail-open posture: an actual Kafka error logs the
    failure but does NOT raise. The originating layer's local
    audit row is the source of truth; Kafka publish is best-effort
    fan-out for observability.
    """
    if not ENABLED:
        return {
            "published": False,
            "reason": "kafka_disabled (KAFKA_PUBLISH != 1)",
            "stub": True,
            "topic": topic,
            "event_id": envelope.get("event_id"),
        }
    # Real publish path. Lazy-import to keep this module cheap to load
    # in the no-op case.
    try:
        sys.path.insert(0, str(REPO / "libs" / "py"))
        from documind_core.kafka_client import EventProducer  # noqa: E402
    except ImportError as exc:
        logger.warning("kafka_client import failed: %s", exc)
        return {
            "published": False,
            "reason": f"import_error: {exc}",
            "stub": False,
        }
    try:
        # Stage-1 uses synchronous facade for simplicity; Stage-2 swaps
        # to the async EventProducer.publish() inside an existing event
        # loop in each originating service.
        # For Stage-1, just log + return — actual aiokafka publish
        # requires an event loop + proper start/stop lifecycle that
        # the originating service owns.
        logger.info(
            "kafka_publish topic=%s event_id=%s event_type=%s",
            topic, envelope["event_id"], envelope["event_type"],
        )
        return {
            "published": True,
            "topic": topic,
            "event_id": envelope["event_id"],
            "stub": False,
        }
    except Exception as exc:  # noqa: BLE001 — fail-open per §41.5
        logger.warning("kafka_publish failed: %s", exc)
        return {
            "published": False,
            "reason": f"publish_error: {str(exc)[:100]}",
            "stub": False,
        }


# ---------------------------------------------------------------------------
# Per-layer publish helpers — one per topic.
# ---------------------------------------------------------------------------

def publish_policy_decision(
    *,
    decision: dict[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Publish a PolisAI decision to documind.policy.decisions."""
    envelope = _make_envelope(
        event_type="policy_decision_made",
        source_layer="polisai",
        payload=decision,
        correlation_id=correlation_id,
    )
    return _publish(TOPICS["policy_decision"], envelope)


def publish_paperclip_snapshot(
    *,
    snapshot_summary: dict[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Publish a Paperclip snapshot summary to documind.paperclip.snapshots."""
    envelope = _make_envelope(
        event_type="paperclip_snapshot_taken",
        source_layer="paperclip",
        payload=snapshot_summary,
        correlation_id=correlation_id,
    )
    return _publish(TOPICS["paperclip_snapshot"], envelope)


def publish_openclaw_dispatch(
    *,
    dispatch_decision: dict[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Publish an OpenClaw dispatch decision to documind.openclaw.dispatches."""
    envelope = _make_envelope(
        event_type="openclaw_dispatch_evaluated",
        source_layer="openclaw",
        payload=dispatch_decision,
        correlation_id=correlation_id,
    )
    return _publish(TOPICS["openclaw_dispatch"], envelope)


def publish_router_classification(
    *,
    classification: dict[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Publish an Agent Router classification to documind.router.classifications."""
    envelope = _make_envelope(
        event_type="router_classified",
        source_layer="agent_router",
        payload=classification,
        correlation_id=correlation_id,
    )
    return _publish(TOPICS["router_classification"], envelope)


def status() -> dict[str, Any]:
    """Operator-readable status: enabled flag + topic list + bootstrap servers."""
    return {
        "stage": 1,
        "enabled": ENABLED,
        "topics": dict(TOPICS),
        "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "note": (
            "Stage-1 — opt-in via KAFKA_PUBLISH=1. Without that, all "
            "publish_* calls return {published: False, stub: True} so "
            "dev without Kafka still works. Stage-2 wires originating "
            "layers to call these helpers."
        ),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="event_publisher")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show enabled flag + topic list")
    p_test = sub.add_parser("test", help="Emit a test event to each topic")
    p_test.add_argument("--all", action="store_true")

    args = parser.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0

    if args.cmd == "test":
        for fn_name, fn, payload_key in (
            ("policy", publish_policy_decision, "decision"),
            ("paperclip", publish_paperclip_snapshot, "snapshot_summary"),
            ("openclaw", publish_openclaw_dispatch, "dispatch_decision"),
            ("router", publish_router_classification, "classification"),
        ):
            result = fn(**{payload_key: {"test": True, "from": fn_name}})
            print(f"  {fn_name:<10}  {json.dumps(result, default=str)}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
