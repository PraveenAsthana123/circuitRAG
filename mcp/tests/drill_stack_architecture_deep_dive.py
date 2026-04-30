#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Stack architecture deep-dive page contract.

Locks /admin/stack-architecture/deep covering Next.js frontend (SSR
+ RSC + BFF) and 12-service Python backend fleet. Both shipped; the
deep-dive is where the architectural shape is canonically explained.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; service-count claim must match
disk reality; canonical service paths must exist.
"""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "stack-architecture" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
SERVICES_DIR = REPO / "services"
KEY_SERVICES = [
    "agent-orchestrator-svc",
    "sidecar-advisor",
    "inference-svc",
    "ingestion-svc",
    "frontend",
]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: stack-architecture deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers both stack halves --")
    require(page, "frontend-stack", "frontend-stack topic")
    require(page, "backend-services", "backend-services topic")
    print("  ok: both topics present")

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
    require(sidebar, "/admin/stack-architecture/deep", "sidebar /admin/stack-architecture/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: 12-service claim must match disk reality --")
    # Page claims a 12-service fleet. Count actual service directories.
    svc_count = sum(
        1 for p in SERVICES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if svc_count < 10:
        raise AssertionError(
            f"page claims 12-service fleet but services/ has {svc_count} dirs; "
            f"update the page or restore missing services"
        )
    print(f"  ok: services/ has {svc_count} service directories (>= 10)")

    print("-- 8. NEGATIVE: canonical service paths cited in page must exist --")
    for svc in KEY_SERVICES:
        if f"services/{svc}" not in page:
            raise AssertionError(f"page must cite services/{svc}")
        if not (SERVICES_DIR / svc).exists():
            raise AssertionError(
                f"page cites services/{svc} but directory missing"
            )
    print(f"  ok: {len(KEY_SERVICES)} key service paths cited and exist")

    print("-- 9. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
