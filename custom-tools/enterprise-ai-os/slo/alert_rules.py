from typing import Dict, Any, List


class AlertRules:
    def evaluate(self, slo_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts = []

        if not slo_report.get("overall_passed"):
            alerts.append({
                "severity": "high",
                "type": "slo_violation",
                "message": "One or more SLOs failed",
                "failed_slos": slo_report.get("failed_slos", []),
            })

        error_budget = slo_report.get("error_budget", {})

        if error_budget.get("budget_exhausted"):
            alerts.append({
                "severity": "critical",
                "type": "error_budget_exhausted",
                "message": "Error budget exhausted. Freeze risky releases.",
                "error_budget": error_budget,
            })

        elif error_budget.get("budget_remaining_percent", 100.0) <= (error_budget.get("allowed_error_rate_percent", 100.0) * 0.2):
            alerts.append({
                "severity": "warning",
                "type": "error_budget_low",
                "message": "Error budget below 20 percent.",
                "error_budget": error_budget,
            })

        return alerts
