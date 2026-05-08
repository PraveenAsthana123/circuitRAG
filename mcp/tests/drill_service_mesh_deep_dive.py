#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Service mesh deep-dive page contract.

Locks the /admin/service-mesh/deep surface so the mesh-pattern + Istio-
in-codebase narrative remain documented together. The trust-boundary
YAML at infra/istio/50-authorization.yaml is canonical reference; the
deep-dive is the only place that explains the pattern + naming
convention + PERMISSIVE → STRICT migration path.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields absent;
placeholder text remaining; PARTIAL surface not honestly marked;
actual Istio config file path not cited.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "service-mesh" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
ISTIO_CONFIG = REPO / "infra" / "istio" / "50-authorization.yaml"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: service-mesh deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers all three mesh surfaces --")
    require(page, "service-mesh-pattern", "service-mesh-pattern topic")
    require(page, "istio-this-codebase", "Istio-in-this-codebase topic")
    require(page, "kiali-integration", "Kiali-integration topic (commits d3ca211 + c8ee4fe + eab8204)")
    print("  ok: all three topics present (mesh pattern + Istio code + Kiali)")

    print("-- 4. POSITIVE: each topic includes the universal-framework canonical fields --")
    for needle, label in [
        ("interviewLine", "interview-line section"),
        ("starStory", "STAR-format story"),
        ("failureModes", "failure modes table"),
        ("implementationSteps", "implementation steps"),
        ("codeExample", "code example"),
        ("monitoring", "monitoring metrics"),
        ("testing", "testing references"),
    ]:
        require(page, needle, label)
    print("  ok: 7 canonical universal-framework fields present")

    print("-- 5. POSITIVE: compose-with footer (§49) renders with 3-7 refs --")
    why_count = page.count("why:")
    if not (3 <= why_count <= 7):
        raise AssertionError(
            f"compose footer must have 3-7 refs (§49); got {why_count}"
        )
    print(f"  ok: compose footer has {why_count} refs (in [3,7] range)")

    print("-- 6. POSITIVE: sidebar registers the new deep-dive entry --")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    require(sidebar, "/admin/service-mesh/deep", "sidebar /admin/service-mesh/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: mesh-pattern + istio-codebase topics must stay PARTIAL --")
    # Mesh control plane is now actually deployed (kiali-integration topic
    # is `shipped`), but the underlying mesh control plane on docker-compose
    # is still NOT active — the kiali-integration uses a SEPARATE minikube
    # cluster (dm-istio profile). The first two topics describe the
    # docker-compose-mesh state which is still partial. Lying about this
    # would mislead operators about which compose services are actually
    # speaking mTLS.
    partial_count = page.count("status: 'partial'") + page.count("status: \"partial\"")
    if partial_count < 2:
        raise AssertionError(
            f"expected mesh-pattern + istio-codebase topics partial (got {partial_count}); "
            f"control plane not deployed in compose stack"
        )
    require(page, "PARTIAL", "explicit PARTIAL marker in body")
    # Additionally: kiali-integration MUST be `shipped` (commits d3ca211 +
    # c8ee4fe + eab8204 already landed; claiming partial would be dishonest).
    shipped_count = page.count("status: 'shipped'") + page.count("status: \"shipped\"")
    if shipped_count < 1:
        raise AssertionError(
            "expected kiali-integration topic with status='shipped' "
            "(per d3ca211 + c8ee4fe + eab8204); claiming partial would be dishonest"
        )
    print(f"  ok: {partial_count} topics partial · {shipped_count} shipped")

    print("-- 8. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 9. NEGATIVE: page must cite the actual Istio config file --")
    require(page, "infra/istio/50-authorization.yaml", "istio config citation")
    if not ISTIO_CONFIG.exists():
        raise AssertionError(
            f"page cites {ISTIO_CONFIG.relative_to(REPO)} but file does not exist"
        )
    print("  ok: Istio config file cited and exists")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
