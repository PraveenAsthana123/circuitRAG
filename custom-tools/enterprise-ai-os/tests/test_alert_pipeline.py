# Negative drills for Iter 39 (2026-05-17): AlertPipeline wiring.

import sys
import io
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slo.alert_pipeline import AlertPipeline
from slo.notifier import LogNotifier, SeverityRouter


def _passing_slo_report():
    return {
        "overall_passed": True,
        "error_budget": {"budget_exhausted": False, "budget_remaining_percent": 90, "allowed_error_rate_percent": 1},
    }


def _failing_slo_report():
    return {
        "overall_passed": False,
        "failed_slos": [{"slo": "p95_latency"}],
        "error_budget": {"budget_exhausted": True, "budget_remaining_percent": 0, "allowed_error_rate_percent": 1},
    }


def test_no_alerts_no_notifications():
    inbox = LogNotifier(stream=io.StringIO())
    p = AlertPipeline(notifier=inbox)
    alerts = p.evaluate_and_notify(_passing_slo_report())
    assert alerts == []
    assert len(inbox.sent) == 0


def test_BACKDOOR_CHECK_failing_slo_routes_to_notifier():
    """Pre-fix the alert dicts were a return value the caller had to
    remember to fan out. Now the pipeline does it."""
    inbox = LogNotifier(stream=io.StringIO())
    p = AlertPipeline(notifier=inbox)
    alerts = p.evaluate_and_notify(_failing_slo_report())
    assert len(alerts) == 2  # slo_violation + error_budget_exhausted
    assert len(inbox.sent) == 2


def test_burn_rate_alerts_also_routed():
    inbox = LogNotifier(stream=io.StringIO())
    p = AlertPipeline(notifier=inbox)
    alerts = p.evaluate_and_notify(
        _passing_slo_report(),
        short_window_error_rates={60: 0.02, 360: 0.001, 4320: 0.0005},
        slo_target_error_rate=0.001,  # 99.9% SLO
    )
    # 0.02 / 0.001 = 20× burn → fires fast_page (>14.4× threshold)
    fast = [a for a in alerts if a.get("window") == "fast_page"]
    assert len(fast) == 1
    assert len(inbox.sent) == len(alerts)


def test_pipeline_with_severity_router():
    """End-to-end: pipeline → severity router → per-severity inbox."""
    page_inbox = LogNotifier(stream=io.StringIO())
    critical_inbox = LogNotifier(stream=io.StringIO())
    default_inbox = LogNotifier(stream=io.StringIO())

    router = SeverityRouter(
        routes={"page": page_inbox, "critical": critical_inbox},
        default=default_inbox,
    )
    p = AlertPipeline(notifier=router)
    p.evaluate_and_notify(
        _failing_slo_report(),
        short_window_error_rates={60: 0.02, 360: 0.001, 4320: 0.0005},
        slo_target_error_rate=0.001,
    )

    # slo_violation has severity 'high' → default
    # error_budget_exhausted has severity 'critical' → critical inbox
    # fast_page burn-rate has severity 'page' → page inbox
    assert len(critical_inbox.sent) >= 1
    assert len(page_inbox.sent) == 1


def test_burn_rate_args_optional():
    """If burn-rate inputs aren't supplied, pipeline only runs
    AlertRules — backwards compat for callers that aren't yet
    tracking short-window rates."""
    inbox = LogNotifier(stream=io.StringIO())
    p = AlertPipeline(notifier=inbox)
    alerts = p.evaluate_and_notify(_failing_slo_report())
    # Should fire on slo_violation + error_budget but NOT burn_rate.
    assert all(a.get("type") != "burn_rate" for a in alerts)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
