#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Knowledge graph deep-dive page contract.

Locks /admin/knowledge-graph/deep covering ontology design + graph
construction. Both topics PLANNED — ADR-008 transport-breaker is
the contract-foundation already shipped; the graph + ontology build
is roadmap. Drill enforces honest status markers + ADR-008 citation
so the dependency on the breaker pattern can't be silently dropped.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; both topics must be PLANNED;
ADR-008 transport-breaker citation missing.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "knowledge-graph" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
ADR_008 = REPO / "docs" / "architecture" / "adr" / "008-transport-breakers-vector-graph.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: knowledge-graph deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers both KG topics --")
    require(page, "ontology-design", "ontology-design topic")
    require(page, "graph-construction", "graph-construction topic")
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
    require(sidebar, "/admin/knowledge-graph/deep", "sidebar /admin/knowledge-graph/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: both topics must declare PLANNED honestly --")
    planned = page.count("status: 'planned'") + page.count("status: \"planned\"")
    if planned < 2:
        raise AssertionError(
            f"both KG topics must declare status='planned' (got {planned}); "
            f"neither ontology nor graph construction has shipped"
        )
    require(page, "NOT YET SHIPPED", "explicit not-yet-shipped marker")
    print(f"  ok: {planned} topics honestly marked planned")

    print("-- 8. NEGATIVE: ADR-008 transport-breaker citation must be present --")
    # The graph half of ADR-008 transport-breaker is the contract this page
    # depends on. Without ADR-008 cited, the page floats free of the
    # foundation it requires.
    require(page, "ADR-008", "ADR-008 citation")
    if not ADR_008.exists():
        raise AssertionError(
            f"page cites ADR-008 but {ADR_008.relative_to(REPO)} missing"
        )
    print("  ok: ADR-008 cited and exists")

    print("-- 9. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 10. NEGATIVE: §39 'ontology before graph' rule must be cited --")
    # Per global §39 RAG architecture standards: define ontology BEFORE
    # building graph. If the page drifts and stops citing this, designers
    # may build graph-first.
    require(page, "BEFORE building", "§39 'ontology before graph' rule")
    print("  ok: §39 'ontology before graph' rule cited")

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
