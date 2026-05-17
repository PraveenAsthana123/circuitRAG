# ✅ P0 FIXED (2026-05-17): recommendation no longer relies on
#     confidence_score alone. The pre-fix version returned "release"
#     for any confidence_score >= 0.8 — silently bypassing the
#     responsible_ai_passed and governance_passed flags.
#
#     Recommendation now requires ALL of:
#       * confidence_score >= 0.8
#       * evaluation_passed is True
#       * responsible_ai_passed is True
#       * governance_passed is True
#
#     If ANY gate fails, recommendation is "block" (with reason).
#     If gates pass but confidence < threshold, recommendation is "review".
#     Only when both conditions hold is recommendation "release".
#
#     Negative drill: tests/test_confidence_no_governance_bypass.py

from typing import Dict, Any


_RELEASE_CONFIDENCE_THRESHOLD = 0.8


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

        evaluation_passed = bool(
            evaluation_result.get("quality_gate", {}).get("passed")
        )
        responsible_ai_passed = bool(responsible_ai_result.get("overall_passed"))
        governance_passed = bool(governance_result.get("policy_passed"))

        gates_failed = []
        if not evaluation_passed:
            gates_failed.append("evaluation")
        if not responsible_ai_passed:
            gates_failed.append("responsible_ai")
        if not governance_passed:
            gates_failed.append("governance")

        if gates_failed:
            recommendation = "block"
            reason = f"gates failed: {', '.join(gates_failed)}"
        elif confidence_score < _RELEASE_CONFIDENCE_THRESHOLD:
            recommendation = "review"
            reason = (
                f"confidence {confidence_score:.2f} below release "
                f"threshold {_RELEASE_CONFIDENCE_THRESHOLD}"
            )
        else:
            recommendation = "release"
            reason = (
                f"all gates passed and confidence {confidence_score:.2f} "
                f">= {_RELEASE_CONFIDENCE_THRESHOLD}"
            )

        return {
            "confidence_score": confidence_score,
            "confidence_level": level,
            "evaluation_passed": evaluation_passed,
            "responsible_ai_passed": responsible_ai_passed,
            "governance_passed": governance_passed,
            "recommendation": recommendation,
            "recommendation_reason": reason,
        }
