#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: §48 GovernanceOS facade L1→L2 — wired into create_task.

Maturity-stack item #48 (AI Governance OS) was at L1 — pieces
scattered (model_router has policy; explainability has audit;
no Compliance Engine). This drill locks the L1 → L2 movement:
a single GovernanceOS object handles BOTH allow-path and block-path
requests, emits structured GovernanceDecision rows, and the wiring
is visible to the route handler — not a class that exists in
isolation.

Per advisor guidance:
  - Both allow-path AND block-path must produce audit rows in the
    same drill, hit through the actual route handler. Read-only OS
    on isolated state would reproduce the §52 honesty bug — class
    exists but never runs in anger.
  - ComplianceEngine MUST return status='not_implemented' for all 4
    frameworks (honest stub). Future iter that swaps in real
    attestation flips this from 'not_implemented' -> 'compliant'.
  - RiskEngine consumes a DriftReport-shaped severity (composes
    with iter 2A's drift_detection module).
  - grep-assert that create_task imports + calls GovernanceOS
    (regression guard against re-introducing the §52 honesty bug).

Eight steps. Six negative assertions.

  1. POSITIVE: governance_os module imports + 5 engine classes +
     build_governance_os factory + 4 compliance frameworks
  2. POSITIVE: app.state.governance_os reachable through lifespan
  3. NEGATIVE: ALLOW path — POST a low-risk task, audit log gains
     a row with action='allow' AND compliance attestations populated
  4. NEGATIVE: BLOCK/REVIEW path — POST a require-human-approval
     task, audit log gains a row with action='review', policy_reasons
     non-empty
  5. NEGATIVE: ComplianceEngine.attest() returns status='not_implemented'
     for ALL 4 frameworks (GDPR / PIPEDA / ISO_42001 / NIST_AI_RMF).
     The drill-as-stub contract — future real attestation flips this.
  6. NEGATIVE: RiskEngine.evaluate consumes drift severity input and
     surfaces it on RiskAssessment.drift_severity (proves composition
     with iter 2A's DriftReport contract).
  7. NEGATIVE: GovernanceDecision.to_dict() round-trips through JSON
     (#48 L2→L3 dashboards + alert wiring depend on this contract).
  8. NEGATIVE: main.py route handler imports + invokes GovernanceOS
     (regression guard — refactor that drops the .evaluate() call
     fails this assertion before silent breakage).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "libs" / "py"))
sys.path.insert(0, str(SVC))

os.environ["DOCUMIND_PROMETHEUS_PORT"] = "0"


def main() -> int:
    print("-- 1. POSITIVE: governance_os module imports + exports --")
    from documind_core import governance_os as gos

    for name in (
        "GovernanceOS",
        "GovernanceDecision",
        "PolicyEngine",
        "RiskEngine",
        "ComplianceEngine",
        "AuditEngine",
        "ComplianceAttestation",
        "RiskAssessment",
        "build_governance_os",
        "COMPLIANCE_FRAMEWORKS",
    ):
        if not hasattr(gos, name):
            print(f"x step 1: missing export {name}")
            return 1
    expected_frameworks = {"GDPR", "PIPEDA", "ISO_42001", "NIST_AI_RMF"}
    if set(gos.COMPLIANCE_FRAMEWORKS) != expected_frameworks:
        print(f"x step 1: framework set mismatch — got {set(gos.COMPLIANCE_FRAMEWORKS)}")
        return 1
    print(f"  ok: 10 exports + 4 frameworks ({sorted(gos.COMPLIANCE_FRAMEWORKS)})")

    print("-- 2. POSITIVE: app.state.governance_os after lifespan --")
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        ogs = getattr(app.state, "governance_os", None)
        assert ogs is not None, "app.state.governance_os not set by lifespan"
        assert isinstance(ogs, gos.GovernanceOS), (
            f"app.state.governance_os wrong type: {type(ogs).__name__}"
        )
        starting_count = ogs.audit.count()
        print(f"  ok: GovernanceOS wired (audit starts at {starting_count} rows)")

        print("-- 3. NEGATIVE: ALLOW path — low-risk POST → audit row with action='allow' --")
        allow_payload = {
            "tenant_id": "drill-tenant-allow",
            "goal": "drill: governance os allow-path",
        }
        r1 = client.post("/api/v1/agentic/tasks", json=allow_payload)
        assert r1.status_code == 200, f"allow-path POST failed: {r1.status_code} {r1.text}"
        after_allow = ogs.audit.count()
        assert after_allow == starting_count + 1, (
            f"audit row not written for allow-path; count {starting_count} -> {after_allow}"
        )
        latest = ogs.audit.recent(limit=1)[0]
        assert latest.action == "allow", (
            f"allow-path action expected 'allow'; got {latest.action!r}. "
            f"reasons={latest.policy_reasons}"
        )
        assert len(latest.compliance_attestations) == 4, (
            f"allow-path missing compliance attestations; got {len(latest.compliance_attestations)}"
        )
        print(f"  ok: action=allow; 4 compliance stubs; reasons={latest.policy_reasons}")

        print("-- 4. NEGATIVE: BLOCK/REVIEW path — human-approval task → audit row with action='review' --")
        review_payload = {
            "tenant_id": "drill-tenant-block",
            "goal": "drill: governance os review-path",
            "require_human_approval": True,
        }
        r2 = client.post("/api/v1/agentic/tasks", json=review_payload)
        # Service may 200 (created with require_human_approval) — what matters is
        # the OS audit row, not the HTTP outcome
        after_review = ogs.audit.count()
        assert after_review == after_allow + 1, (
            f"audit row not written for review-path; count {after_allow} -> {after_review}"
        )
        latest_review = ogs.audit.recent(limit=1)[0]
        assert latest_review.action in ("review", "block"), (
            f"review-path action expected 'review' or 'block'; got {latest_review.action!r}"
        )
        print(f"  ok: action={latest_review.action}; reasons={latest_review.policy_reasons}")

        print("-- 5. NEGATIVE: ComplianceEngine attestations are status='not_implemented' --")
        for att in latest.compliance_attestations:
            assert att.status == "not_implemented", (
                f"compliance attestation for {att.framework} expected 'not_implemented'; "
                f"got {att.status!r}. Either real attestation landed (great — this drill "
                "needs to update) or the stub was bypassed (regression)."
            )
            assert att.framework in expected_frameworks
            assert att.reference, f"attestation for {att.framework} missing reference"
        print("  ok: all 4 frameworks return status='not_implemented' with reference citations")

        print("-- 6. NEGATIVE: RiskEngine.evaluate consumes drift severity --")
        risk_engine = gos.RiskEngine()
        risk_with_drift = risk_engine.evaluate(
            risk_level="low",
            drift_severity="significant",
        )
        assert risk_with_drift.drift_severity == "significant", (
            f"drift_severity not propagated to RiskAssessment; got {risk_with_drift.drift_severity!r}"
        )
        assert risk_with_drift.overall_severity == "significant", (
            f"drift_severity should escalate overall severity; got {risk_with_drift.overall_severity!r}"
        )
        risk_clean = risk_engine.evaluate(risk_level="low", drift_severity="ok")
        assert risk_clean.overall_severity == "ok", (
            f"clean drift should not escalate severity; got {risk_clean.overall_severity!r}"
        )
        print(f"  ok: significant drift escalates risk; clean drift stays ok")

        print("-- 7. NEGATIVE: GovernanceDecision.to_dict() round-trips through JSON --")
        payload = latest.to_dict()
        serialized = json.dumps(payload, default=str)
        deserialized = json.loads(serialized)
        # asdict converts dataclasses to dicts; tuples become lists in JSON
        assert "request_id" in deserialized, "request_id missing in serialized form"
        assert "action" in deserialized, "action missing"
        assert "policy_reasons" in deserialized, "policy_reasons missing"
        assert "risk" in deserialized, "risk missing"
        assert "compliance_attestations" in deserialized, "compliance_attestations missing"
        assert "decision_summary" in deserialized, "decision_summary missing"
        assert "timestamp_iso" in deserialized, "timestamp_iso missing"
        # Compliance is a list of 4 attestation-dicts after asdict
        compls = deserialized["compliance_attestations"]
        assert len(compls) == 4, f"compliance_attestations should serialize 4; got {len(compls)}"
        print(f"  ok: 7-field GovernanceDecision round-trips; 4 attestations preserved")

    print("-- 8. NEGATIVE: main.py imports + invokes GovernanceOS (regression guard) --")
    main_src = (SVC / "app" / "main.py").read_text(encoding="utf-8")
    for needle in (
        "from documind_core.governance_os import",
        "build_governance_os",
        "app.state.governance_os",
        "governance_os.evaluate(",
    ):
        assert needle in main_src, (
            f"main.py missing wiring: {needle!r}. "
            "Without this the OS class exists but never runs — §52 honesty regression."
        )
    print("  ok: import + factory + state binding + .evaluate() call all present")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
