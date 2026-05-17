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

        return alerts
