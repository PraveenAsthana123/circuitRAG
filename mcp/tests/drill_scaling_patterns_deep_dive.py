#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Scaling-patterns deep-dive page contract.

Locks the /admin/scaling-patterns/deep surface covering three
adjacent scaling concerns: load balancing (Phase-2 k8s), page-level
RAG index (two-stage retrieval, planned), and vectorless RAG
(graph traversal, planned). All three are PLANNED or PARTIAL — the
drill enforces honest status markers so operators are never told
features are shipped that don't exist.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; status honesty (all three
PLANNED or PARTIAL); §48 explainability tie-back missing.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "scaling-patterns" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: scaling-patterns deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers all three scaling-pattern surfaces --")
    require(page, "load-balancing", "load-balancing topic")
    require(page, "page-index-rag", "page-index-rag topic")
    require(page, "vectorless-rag", "vectorless-rag topic")
    print("  ok: all 3 topics present")

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
    require(sidebar, "/admin/scaling-patterns/deep", "sidebar /admin/scaling-patterns/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: all three topics must be PARTIAL or PLANNED --")
    # None of the three are shipped end-to-end. Lying about this is a
    # §45.4 honesty violation.
    partial = page.count("status: 'partial'") + page.count("status: \"partial\"")
    planned = page.count("status: 'planned'") + page.count("status: \"planned\"")
    if partial + planned < 3:
        raise AssertionError(
            f"expected 3 partial/planned statuses (got {partial} partial + "
            f"{planned} planned); none of these surfaces are shipped end-to-end"
        )
    require(page, "NOT YET SHIPPED", "explicit not-yet-shipped marker")
    print(f"  ok: {partial} partial + {planned} planned (>= 3)")

    print("-- 8. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 9. NEGATIVE: explainability tie-back (§48) must be present --")
    # Page-citation chain + graph traversal audit are §48 explainability
    # requirements. Without those references the page drifts into a
    # marketing surface.
    require(page, "§48", "§48 explainability citation")
    require(page, "explainability", "explainability concept reference")
    print("  ok: §48 explainability tie-back present")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
