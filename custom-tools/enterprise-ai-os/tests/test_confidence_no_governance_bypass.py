# Negative drill for the P0 governance-bypass fix in
# explainability_ai/confidence_report.py (2026-05-17).
#
# The pre-fix bug: `recommendation = "release" if confidence_score >= 0.8
# else "review"` — silently ignored evaluation_passed,
# responsible_ai_passed, and governance_passed. So a high-confidence
# model output could be "released" even when governance had failed it.
#
# Each test asserts a NEGATIVE case that would have produced "release"
# under the pre-fix logic but now correctly returns "block".

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from explainability_ai.confidence_report import ConfidenceReport


def _gate(passed: bool) -> dict:
    return {"quality_gate": {"passed": passed}}


def _rai(passed: bool) -> dict:
    return {"overall_passed": passed}


def _gov(passed: bool) -> dict:
    return {"policy_passed": passed}


def test_all_gates_pass_high_confidence_releases():
    """Sanity: when everything passes, recommend release."""
    r = ConfidenceReport()
    out = r.generate(0.95, _gate(True), _rai(True), _gov(True))
    assert out["recommendation"] == "release"


# ---------- The 3 critical bypass-bug regressions ----------

def test_governance_failure_blocks_release_even_at_high_confidence():
    """
    BACKDOOR REGRESSION: high confidence + governance_passed=False
    must produce 'block', NOT 'release'.
    Pre-fix: returned 'release' because only confidence was checked.
    """
    r = ConfidenceReport()
    out = r.generate(0.95, _gate(True), _rai(True), _gov(False))
    assert out["recommendation"] == "block", (
        "BACKDOOR REGRESSED: high confidence overrode governance failure"
    )
    assert "governance" in out["recommendation_reason"]


def test_responsible_ai_failure_blocks_release():
    """High confidence + responsible_ai_passed=False must block."""
    r = ConfidenceReport()
    out = r.generate(0.95, _gate(True), _rai(False), _gov(True))
    assert out["recommendation"] == "block"
    assert "responsible_ai" in out["recommendation_reason"]


def test_evaluation_failure_blocks_release():
    """High confidence + evaluation_gate failed must block."""
    r = ConfidenceReport()
    out = r.generate(0.95, _gate(False), _rai(True), _gov(True))
    assert out["recommendation"] == "block"
    assert "evaluation" in out["recommendation_reason"]


def test_missing_gate_field_treated_as_failed():
    """If a gate dict is missing the expected key, treat as failed (fail closed)."""
    r = ConfidenceReport()
    out = r.generate(0.95, {}, _rai(True), _gov(True))
    assert out["recommendation"] == "block"


def test_low_confidence_with_all_gates_passed_recommends_review():
    """Below threshold + all gates pass → review, not release."""
    r = ConfidenceReport()
    out = r.generate(0.5, _gate(True), _rai(True), _gov(True))
    assert out["recommendation"] == "review"
    assert "below release threshold" in out["recommendation_reason"]


def test_multiple_gates_failing_lists_all_in_reason():
    """When multiple gates fail, the reason should list each."""
    r = ConfidenceReport()
    out = r.generate(0.95, _gate(False), _rai(False), _gov(False))
    assert out["recommendation"] == "block"
    reason = out["recommendation_reason"]
    assert "evaluation" in reason
    assert "responsible_ai" in reason
    assert "governance" in reason


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
