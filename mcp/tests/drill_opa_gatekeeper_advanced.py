#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: OPA Gatekeeper admission-policy pack.

Locks Kubernetes admission controls for DocuMind without requiring a
live cluster. The drill validates manifests, Gatekeeper binding, deny
enforcement, namespace scoping, and embedded Rego compilation.

NEGATIVE: invalid or unbound Gatekeeper constraints must not be reported shipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

CONSTRAINTS = REPO / "infra" / "k8s" / "gatekeeper" / "constraints.yaml"
KUSTOMIZATION = REPO / "infra" / "k8s" / "gatekeeper" / "kustomization.yaml"


def main() -> int:
    print("-- 1. POSITIVE: Gatekeeper manifest pack exists --")
    if not CONSTRAINTS.exists() or not KUSTOMIZATION.exists():
        print("x infra/k8s/gatekeeper constraints or kustomization missing")
        return 1
    print("  ok: Gatekeeper manifests present")

    print("-- 2. POSITIVE: status checker exports offline-safe status --")
    import opa_gatekeeper_status

    payload = opa_gatekeeper_status.status()
    for key in ("gatekeeper", "counts", "coverage", "rego"):
        if key not in payload:
            print(f"x status missing key: {key}")
            return 1
    print("  ok: status shape is stable")

    print("-- 3. POSITIVE: four ConstraintTemplates and four Constraints --")
    counts = payload["counts"]
    if counts["constraint_templates"] != 4 or counts["constraints"] != 4:
        print(f"x expected 4 templates + 4 constraints; got {counts}")
        return 1
    print("  ok: four controls registered")

    print("-- 4. NEGATIVE: every constraint is deny-enforced and documind-scoped --")
    if counts["deny_constraints"] != counts["constraints"]:
        print(f"x every constraint must use enforcementAction=deny: {counts}")
        return 1
    if counts["namespace_scoped"] != counts["constraints"]:
        print(f"x every constraint must scope to documind namespace: {counts}")
        return 1
    print("  ok: deny action + namespace scope preserved")

    print("-- 5. NEGATIVE: every template kind has a matching constraint --")
    coverage = payload["coverage"]
    if not coverage["all_templates_bound"]:
        print(f"x template/constraint kind mismatch: {coverage}")
        return 1
    print("  ok: all ConstraintTemplates are bound")

    print("-- 6. POSITIVE: required admission controls are covered --")
    required = {
        "required_labels",
        "no_host_namespace",
        "non_root_readonly_no_privilege_escalation",
        "allowed_image_registries",
    }
    if set(coverage["controls"]) != required:
        print(f"x control coverage drifted: {coverage['controls']}")
        return 1
    print("  ok: label/runtime/namespace/registry controls covered")

    print("-- 7. NEGATIVE: embedded Rego compiles and sample bad pod violates --")
    bad = [item for item in payload["rego"] if not item["compiled"]]
    if bad:
        print(f"x Rego compile failures: {bad}")
        return 1
    if not all(item["sample_violation_count"] >= 1 for item in payload["rego"]):
        print(f"x every template must flag sample bad admission: {payload['rego']}")
        return 1
    print("  ok: Rego compiles and denies sample bad input")

    print("-- 8. POSITIVE: ready_for_apply is true when OPA validates pack --")
    if not payload["gatekeeper"]["ready_for_apply"]:
        print(f"x Gatekeeper pack not ready: {payload['gatekeeper']}")
        return 1
    print("  ok: pack is ready for cluster apply after Gatekeeper install")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
