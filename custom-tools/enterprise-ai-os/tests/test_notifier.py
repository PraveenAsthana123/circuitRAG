# Negative drills for Iter 28 (2026-05-17): pluggable Notifier.

import sys
import io
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slo.notifier import (
    Notifier,
    AlertEvent,
    LogNotifier,
    SeverityRouter,
)


def test_log_notifier_writes_json():
    buf = io.StringIO()
    n = LogNotifier(stream=buf)
    n.notify(AlertEvent(
        severity="page",
        alert_type="burn_rate",
        message="fast burn",
        payload={"window": "1h", "rate": 15.2},
        fired_at="2026-05-17T00:00:00Z",
    ))
    line = buf.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["type"] == "alert_routed"
    assert parsed["severity"] == "page"
    assert parsed["payload"]["rate"] == 15.2
    assert n.sent[0].severity == "page"


def test_notify_all_converts_dicts_and_returns_count():
    n = LogNotifier(stream=io.StringIO())
    alerts = [
        {"severity": "page", "type": "burn_rate", "message": "x", "k": 1},
        {"severity": "ticket", "type": "slo_violation", "message": "y", "k": 2},
    ]
    count = n.notify_all(alerts)
    assert count == 2
    assert n.sent[0].severity == "page"
    assert n.sent[1].alert_type == "slo_violation"
    # Payload should NOT re-include severity/type/message (already
    # promoted to top-level event fields).
    assert "severity" not in n.sent[0].payload
    assert "k" in n.sent[0].payload


def test_BACKDOOR_CHECK_severity_router_dispatches_per_severity():
    """Pre-fix: a single notify path treated every alert the same."""
    page_inbox = LogNotifier(stream=io.StringIO())
    ticket_inbox = LogNotifier(stream=io.StringIO())
    default_inbox = LogNotifier(stream=io.StringIO())
    router = SeverityRouter(
        routes={"page": page_inbox, "ticket": ticket_inbox},
        default=default_inbox,
    )
    router.notify_all([
        {"severity": "page", "type": "burn_rate", "message": "x"},
        {"severity": "ticket", "type": "slo_violation", "message": "y"},
        {"severity": "info", "type": "info", "message": "z"},
    ])
    assert len(page_inbox.sent) == 1
    assert len(ticket_inbox.sent) == 1
    assert len(default_inbox.sent) == 1  # info → default


def test_default_when_route_missing():
    default_inbox = LogNotifier(stream=io.StringIO())
    router = SeverityRouter(routes={}, default=default_inbox)
    router.notify(AlertEvent(
        severity="page", alert_type="x", message="y",
        payload={}, fired_at="t",
    ))
    assert len(default_inbox.sent) == 1


def test_alert_event_from_dict_round_trip():
    e = AlertEvent.from_alert({
        "severity": "critical",
        "type": "error_budget_exhausted",
        "message": "freeze releases",
        "extra": {"foo": "bar"},
    })
    assert e.severity == "critical"
    assert e.alert_type == "error_budget_exhausted"
    assert e.payload == {"extra": {"foo": "bar"}}


def test_notifier_abc_cannot_be_constructed_directly():
    with pytest.raises(TypeError):
        Notifier()  # abstract


def test_router_with_only_default():
    """A router with no per-severity routes still works (all go to default)."""
    default_inbox = LogNotifier(stream=io.StringIO())
    router = SeverityRouter(routes={}, default=default_inbox)
    router.notify_all([
        {"severity": "page", "type": "x", "message": "x"},
        {"severity": "ticket", "type": "y", "message": "y"},
        {"severity": "info", "type": "z", "message": "z"},
    ])
    assert len(default_inbox.sent) == 3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
