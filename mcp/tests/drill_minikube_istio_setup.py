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

    print("-- 12. POSITIVE: kiali.yaml has required signing_key (v1.86 contract) --")
    kiali_yaml = (KIALI_DIR / "kiali.yaml").read_text(encoding="utf-8")
    require(kiali_yaml, "login_token:", "login_token block in kiali.yaml")
    require(kiali_yaml, "signing_key:", "signing_key field in kiali.yaml")
    # Extract the signing_key value and verify it's 16/24/32 bytes
    import re
    m = re.search(r'signing_key:\s*"?([a-fA-F0-9]+)"?', kiali_yaml)
    if not m:
        raise AssertionError("signing_key value not extractable from kiali.yaml")
    key_len = len(m.group(1))
    # hex chars / 2 = bytes; v1.86 requires 16, 24, or 32 BYTES
    key_bytes = key_len // 2 if all(c in "0123456789abcdefABCDEF" for c in m.group(1)) else key_len
    if key_bytes not in (16, 24, 32):
        raise AssertionError(
            f"signing_key length {key_bytes} bytes; "
            f"Kiali v1.86 requires exactly 16, 24, or 32 bytes"
        )
    print(f"  ok: signing_key present, length={key_bytes} bytes (v1.86-compliant)")

    print("-- 13. POSITIVE: kiali docker-compose entry gated by 'mesh' profile --")
    compose_yaml = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    # Find the kiali service block
    m = re.search(
        r'^  kiali:.*?^  [a-z][a-z0-9_-]*:',
        compose_yaml,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise AssertionError("kiali service block not found in docker-compose.yml")
    kiali_block = m.group(0)
    if 'profiles:' not in kiali_block or '"mesh"' not in kiali_block:
        raise AssertionError(
            "kiali docker-compose entry must have profiles: [\"mesh\"]; "
            "without it, `docker compose up` would auto-start a Kiali "
            "that hard-blocks on a K8s cache sync that cannot complete"
        )
    print("  ok: kiali gated by --profile mesh (compose-mode K8s incompatibility)")

    print("-- 14. NEGATIVE: kiali.yaml MUST NOT claim 'non-mesh metrics work' --")
    # The original comment claimed Kiali in compose-mode would still serve
    # Prom + Jaeger panels — empirically false in v1.86 (cache sync blocks
    # HTTP server). Drill enforces the comment is updated to reflect reality.
    if "non-mesh metrics + traces for quick visual debugging" in kiali_yaml:
        raise AssertionError(
            "kiali.yaml still has the misleading 'non-mesh metrics' claim — "
            "Kiali v1.86 does NOT serve HTTP without K8s. Update the comment "
            "to reflect the istio-up.sh requirement."
        )
    if "serves /kiali/healthz under degraded" in kiali_yaml:
        raise AssertionError(
            "kiali.yaml still claims cache_enabled=false is a degraded "
            "compose-mode serving path. Kiali v1.86 needs a responsive K8s API."
        )
    if "scripts/istio-up.sh" not in kiali_yaml:
        raise AssertionError(
            "kiali.yaml comment must reference scripts/istio-up.sh as the "
            "operator entry point for getting Kiali fully functional"
        )
    print("  ok: kiali.yaml comment reflects reality; references istio-up.sh")

    print("-- 15. POSITIVE: Makefile exposes istio-status target used by scripts --")
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    require(makefile, "istio-status:", "istio-status Makefile target")
    require(makefile, "proxy-status", "istioctl proxy-status check")
    require(makefile, "authorizationpolicy", "mesh policy status check")
    print("  ok: Makefile has read-only istio-status target")

    print("-- 16. POSITIVE: runbook documents kiali-via-profile-mesh workflow --")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    require(runbook, "--profile mesh", "kiali profile-mesh instruction in runbook")
    print("  ok: runbook documents `docker compose --profile mesh up kiali`")

    print("\nALL 16 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
