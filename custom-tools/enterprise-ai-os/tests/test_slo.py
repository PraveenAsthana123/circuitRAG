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
        failed_requests=800,
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


if __name__ == "__main__":
    test_slo_report_and_alert_rules()
    print("OK")
