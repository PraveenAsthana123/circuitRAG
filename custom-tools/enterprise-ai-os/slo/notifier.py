# Added Iter 28 (2026-05-17) — pluggable Notifier interface for SLO
# + burn-rate alerts. Pre-fix the AlertRules class returned a list
# of alert dicts; nothing routed them anywhere.
#
# Why an abstract base + log-only default:
#   - Real production wires concrete subclasses to PagerDuty / Slack
#     / Opsgenie / email. Those need credentials + network.
#   - The default LogNotifier emits structured JSON so even without
#     a real router, alerts are GREPpable from the app log — which
#     is the difference between "an alert was raised" (observable)
#     and "an alert was raised but nobody saw it" (not).
#   - Severity-based routing: a single Notifier can fan out to
#     different destinations per severity (page → PagerDuty,
#     ticket → JIRA, info → log only).

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sys
from typing import Any, Dict, List, Optional


@dataclass
class AlertEvent:
    severity: str          # "info" | "warning" | "ticket" | "page" | "critical"
    alert_type: str        # "slo_violation" | "burn_rate" | etc.
    message: str
    payload: Dict[str, Any]
    fired_at: str

    @classmethod
    def from_alert(cls, alert: Dict[str, Any]) -> "AlertEvent":
        return cls(
            severity=alert.get("severity", "info"),
            alert_type=alert.get("type", "unknown"),
            message=alert.get("message", ""),
            payload={k: v for k, v in alert.items()
                     if k not in ("severity", "type", "message")},
            fired_at=datetime.now(timezone.utc).isoformat(),
        )


class Notifier(ABC):
    @abstractmethod
    def notify(self, event: AlertEvent) -> None:
        ...

    def notify_all(self, alerts: List[Dict[str, Any]]) -> int:
        """Convenience: convert each dict to AlertEvent and notify.
        Returns count of events sent."""
        events = [AlertEvent.from_alert(a) for a in alerts]
        for e in events:
            self.notify(e)
        return len(events)


class LogNotifier(Notifier):
    """Default — writes structured JSON to a stream. Useful when no
    real router is wired yet; ensures alerts are at least
    GREPpable."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stderr
        self.sent: List[AlertEvent] = []  # in-memory for tests

    def notify(self, event: AlertEvent) -> None:
        self.sent.append(event)
        self.stream.write(json.dumps({
            "type": "alert_routed",
            "severity": event.severity,
            "alert_type": event.alert_type,
            "message": event.message,
            "payload": event.payload,
            "fired_at": event.fired_at,
        }) + "\n")
        self.stream.flush()


class SeverityRouter(Notifier):
    """Routes alerts to different Notifiers based on severity.
    Unmapped severities fall back to `default`."""

    def __init__(
        self,
        routes: Dict[str, Notifier],
        default: Optional[Notifier] = None,
    ):
        self.routes = routes
        self.default = default or LogNotifier()

    def notify(self, event: AlertEvent) -> None:
        target = self.routes.get(event.severity, self.default)
        target.notify(event)
