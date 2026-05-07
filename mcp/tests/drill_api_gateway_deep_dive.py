#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: API gateway deep-dive page contract.

Locks the /admin/api-gateway/deep surface. The current state is
"Next.js BFF acts as the gateway" (shipped); the future state is
"dedicated NGINX + Go gateway tier" (planned). Both must be
documented honestly so operators know which surface is active.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; status honesty (current=shipped,
future=planned); correlation_id contract not documented.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "api-gateway" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
BFF_DIR = REPO / "services" / "frontend" / "app" / "api" / "v1"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: api-gateway deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers both gateway surfaces --")
    require(page, "next-bff-gateway", "Next.js BFF gateway topic")
    require(page, "dedicated-gateway-future", "dedicated gateway topic")
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
    require(sidebar, "/admin/api-gateway/deep", "sidebar /admin/api-gateway/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: BFF must be marked shipped, dedicated gateway must be planned --")
    if "status: 'shipped'" not in page and "status: \"shipped\"" not in page:
        raise AssertionError(
            "Next.js BFF gateway must declare status='shipped' "
            "(BFF routes exist under app/api/v1/)"
        )
    if "status: 'planned'" not in page and "status: \"planned\"" not in page:
        raise AssertionError(
            "dedicated gateway must declare status='planned' "
            "(NGINX + Go gateway not yet shipped)"
        )
    require(page, "NOT YET SHIPPED", "explicit not-yet-shipped marker for future tier")
    print("  ok: status honestly differentiated (shipped vs planned)")

    print("-- 8. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 9. NEGATIVE: correlation_id contract must be documented --")
    # The whole gateway → BFF → backend story turns on correlation_id
    # propagation. Without that, traces fragment.
    require(page, "correlation_id", "correlation_id propagation contract")
    require(page, "canonical error envelope", "canonical error envelope contract")
    print("  ok: correlation_id + canonical envelope contracts documented")

    print("-- 10. NEGATIVE: BFF surface must actually exist on disk --")
    if not BFF_DIR.exists() or not BFF_DIR.is_dir():
        raise AssertionError(
            f"page claims Next.js BFF gateway is shipped but {BFF_DIR.relative_to(REPO)} "
            f"does not exist"
        )
    print("  ok: BFF surface exists at app/api/v1/")

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
