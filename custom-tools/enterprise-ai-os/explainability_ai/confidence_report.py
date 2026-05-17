from typing import Dict, Any


class ConfidenceReport:
    def generate(
        self,
        confidence_score: float,
        evaluation_result: Dict[str, Any],
        responsible_ai_result: Dict[str, Any],
        governance_result: Dict[str, Any]
    ) -> Dict[str, Any]:

        if confidence_score >= 0.85:
            level = "high"
        elif confidence_score >= 0.65:
            level = "medium"
        else:
            level = "low"

        return {
            "confidence_score": confidence_score,
            "confidence_level": level,
            "evaluation_passed": evaluation_result.get("quality_gate", {}).get("passed"),
            "responsible_ai_passed": responsible_ai_result.get("overall_passed"),
            "governance_passed": governance_result.get("policy_passed"),
            "recommendation": "release" if confidence_score >= 0.8 else "review"
        }
