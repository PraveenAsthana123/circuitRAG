# Test script from Tool Set 38 §5 — reformatted as a runnable pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slo.slo_policy import SLOPolicyRegistry
from slo.error_budget import ErrorBudget
from slo.slo_report import SLOReport
from slo.alert_rules import AlertRules


def test_slo_report_and_alert_rules():
    registry = SLOPolicyRegistry()
    budget = ErrorBudget()
    reporter = SLOReport()
    alerts = AlertRules()

    metrics = {
        "availability_percent": 99.95,
        "p95_latency_ms": 1800,
        "p99_latency_ms": 4700,
        "error_rate_percent": 0.8,
        "grounding_score": 0.92,
        "citation_coverage": 0.96,
        "cost_usd": 0.018,
    }

    evaluations = [
        registry.evaluate(policy, metrics[policy.metric_name])
        for policy in registry.default_policies()
    ]

    error_budget = budget.calculate(
        total_requests=100000,
        failed_requests=100,
        allowed_error_rate_percent=1.0
    )

    slo_report = reporter.generate(
        service_name="enterprise-ai-os",
        evaluations=evaluations,
        error_budget=error_budget
    )

    assert slo_report["overall_passed"] is True
    assert slo_report["failed_slos"] == []

    alert_list = alerts.evaluate(slo_report)
    assert alert_list == []


def test_slo_violation_triggers_high_alert():
    reporter = SLOReport()
    alerts = AlertRules()

    slo_report = reporter.generate(
        service_name="enterprise-ai-os",
        evaluations=[{
            "slo": "availability",
            "metric": "availability_percent",
            "target": 99.9,
            "actual": 99.0,
            "passed": False,
            "window": "30d",
        }],
        error_budget={"budget_exhausted": False, "budget_remaining_percent": 50.0},
    )

    alert_list = alerts.evaluate(slo_report)

    assert any(alert["type"] == "slo_violation" for alert in alert_list)
    assert any(alert["severity"] == "high" for alert in alert_list)


def test_error_budget_warning_and_exhaustion_alerts():
    alerts = AlertRules()
    reporter = SLOReport()

    warning_report = reporter.generate(
        service_name="enterprise-ai-os",
        evaluations=[],
        error_budget={"budget_exhausted": False, "budget_remaining_percent": 0.1, "allowed_error_rate_percent": 1.0},
    )
    warning_alerts = alerts.evaluate(warning_report)
    assert warning_alerts[0]["type"] == "error_budget_low"
    assert warning_alerts[0]["severity"] == "warning"

    critical_report = reporter.generate(
        service_name="enterprise-ai-os",
        evaluations=[],
        error_budget={"budget_exhausted": True, "budget_remaining_percent": 0.0, "allowed_error_rate_percent": 1.0},
    )
    critical_alerts = alerts.evaluate(critical_report)
    assert critical_alerts[0]["type"] == "error_budget_exhausted"
    assert critical_alerts[0]["severity"] == "critical"


if __name__ == "__main__":
    test_slo_report_and_alert_rules()
    print("OK")
