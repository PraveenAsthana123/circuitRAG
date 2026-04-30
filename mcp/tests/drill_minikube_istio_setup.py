#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: minikube + Istio local deploy contract.

Locks scripts/istio-up.sh + scripts/istio-down.sh + the operator
runbook. Without this drill, the up/down scripts can silently drift
from the actual infra/istio/ YAML structure or lose key invariants
(idempotent re-run, sidecar-injection label, profile=demo install).

Negative assertions cover: scripts absent or non-executable; missing
tool checks; non-idempotent install; missing istio-injection label;
runbook stripped of the resource-use warning + minikube alternative.
"""
from __future__ import annotations

import os
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
UP = REPO / "scripts" / "istio-up.sh"
DOWN = REPO / "scripts" / "istio-down.sh"
RUNBOOK = REPO / "docs" / "runbooks" / "istio-local-deploy.md"
ISTIO_DIR = REPO / "infra" / "istio"
KIALI_DIR = REPO / "infra" / "kiali"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: up + down scripts + runbook all exist --")
    for p in (UP, DOWN, RUNBOOK):
        if not p.exists():
            raise AssertionError(f"missing {p.relative_to(REPO)}")
    print("  ok: up/down scripts + runbook present")

    print("-- 2. POSITIVE: scripts are executable --")
    for p in (UP, DOWN):
        st = os.stat(p)
        if not (st.st_mode & 0o111):
            raise AssertionError(f"{p.relative_to(REPO)} is not executable")
    print("  ok: both scripts have +x")

    print("-- 3. POSITIVE: istio-up.sh checks for required tools --")
    up = UP.read_text(encoding="utf-8")
    for needle, label in [
        ("require_tool minikube", "minikube tool check"),
        ("require_tool kubectl", "kubectl tool check"),
        ("ISTIO_VERSION", "istio version variable"),
    ]:
        require(up, needle, label)
    print("  ok: tool checks present")

    print("-- 4. POSITIVE: istio-up.sh applies project YAMLs --")
    require(up, "infra/istio/", "infra/istio apply")
    require(up, "infra/kiali/", "infra/kiali apply")
    require(up, "kubectl apply -f", "kubectl apply call")
    print("  ok: applies infra/istio/ + infra/kiali/")

    print("-- 5. NEGATIVE: install MUST be idempotent --")
    # Re-running istio-up.sh on a healthy cluster should NOT re-install
    # istiod (kubectl apply is idempotent already; istioctl install is
    # the risk). Drill checks both early-return paths exist.
    require(up, "minikube -p \"$MINIKUBE_PROFILE\" status", "minikube status check")
    require(up, "already running", "minikube idempotent path message")
    require(up, "already running in istio-system", "istiod idempotent path message")
    print("  ok: idempotent re-run paths present")

    print("-- 6. NEGATIVE: namespace MUST get istio-injection label --")
    # Without the label, sidecars won't inject and the mesh has no
    # data plane. Most-load-bearing single line in the script.
    require(up, "istio-injection=enabled", "istio-injection label")
    require(up, "kubectl label ns", "kubectl label ns call")
    print("  ok: namespace istio-injection=enabled label set")

    print("-- 7. POSITIVE: runbook documents prerequisites + verify steps --")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for needle, label in [
        ("Prerequisites", "prerequisites section"),
        ("minikube", "minikube reference"),
        ("istioctl", "istioctl reference"),
        ("kubectl", "kubectl reference"),
        ("Verify", "verify section"),
        ("Tear down", "tear-down section"),
        ("Failure modes", "failure-modes table"),
    ]:
        require(runbook, needle, label)
    print("  ok: runbook has prereqs + verify + teardown + failure modes")

    print("-- 8. NEGATIVE: runbook MUST warn about resource usage --")
    # 6 GB RAM cost is significant; operator must consent. Without the
    # warning + override path, runbook leaves operators surprised.
    require(runbook, "6 GB RAM", "resource-use warning")
    require(runbook, "MINIKUBE_MEMORY", "memory override env-var")
    print("  ok: runbook documents resource cost + override")

    print("-- 9. NEGATIVE: runbook MUST cite the brutal rule --")
    # Without it, operators may run minikube continuously instead of
    # only when mesh enforcement is being tested. The cost-benefit
    # framing is the operator-decision anchor.
    require(runbook, "brutal rule", "brutal-rule heading")
    # Phrase line-wraps in markdown; check the constituent parts.
    require(runbook, "80%", "alternative-stack value claim")
    require(runbook, "Istio's value", "Istio reference in brutal rule")
    require(runbook, "5% of the operational cost", "alternative-stack cost claim")
    print("  ok: brutal rule + alternative-stack claim present")

    print("-- 10. POSITIVE: infra/istio/ + infra/kiali/ exist with content --")
    if not ISTIO_DIR.exists():
        raise AssertionError(f"missing {ISTIO_DIR.relative_to(REPO)}")
    if not KIALI_DIR.exists():
        raise AssertionError(f"missing {KIALI_DIR.relative_to(REPO)}")
    istio_files = list(ISTIO_DIR.rglob("*.yaml"))
    kiali_files = list(KIALI_DIR.rglob("*.yaml"))
    if len(istio_files) < 3:
        raise AssertionError(
            f"infra/istio/ has only {len(istio_files)} YAML files; "
            f"expected at least 3 (namespace/peer-auth/authz)"
        )
    if not kiali_files:
        raise AssertionError("infra/kiali/ has no YAML files")
    print(f"  ok: infra/istio/ has {len(istio_files)} YAMLs; "
          f"infra/kiali/ has {len(kiali_files)}")

    print("-- 11. NEGATIVE: down script MUST handle missing minikube gracefully --")
    down = DOWN.read_text(encoding="utf-8")
    require(down, "command -v minikube", "minikube presence check in down")
    require(down, "nothing to delete", "graceful no-op message")
    print("  ok: down script no-ops cleanly when minikube absent")

    print("\nALL 11 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
