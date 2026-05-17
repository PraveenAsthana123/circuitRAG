from datetime import datetime
from typing import Dict, Any, List


class SLOReport:
    def generate(
        self,
        service_name: str,
        evaluations: List[Dict[str, Any]],
        error_budget: Dict[str, Any]
    ) -> Dict[str, Any]:

        failed = [
            item for item in evaluations
            if item["passed"] is False
        ]

        return {
            "report_type": "slo_report",
            "service_name": service_name,
            "overall_passed": len(failed) == 0,
            "failed_slos": failed,
            "evaluations": evaluations,
            "error_budget": error_budget,
            "created_at": datetime.utcnow().isoformat(),
        }
