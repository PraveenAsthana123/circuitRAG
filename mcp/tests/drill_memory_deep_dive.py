#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Memory deep-dive page contract.

Locks the /admin/memory/deep surface so a future refactor cannot
silently strip the compose-with footer (§49) or drop the two
canonical topics (sidecar event memory + orchestrator project
memory). Without this drill, the page is a leaf node — disconnected
from the dependency graph the rest of the architecture relies on.

Negative assertions cover: page absent; sidebar entry missing;
DeepDiveCrossRefs import / render missing; canonical section
substrings (interviewLine / starStory / failureModes) absent.
Without these, the page can drift into a marketing surface that
doesn't compose with the rest of the deep-dive catalog.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "memory" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: memory deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers both memory surfaces --")
    require(page, "sidecar-event-memory", "sidecar event memory topic slug")
    require(page, "orchestrator-project-memory", "orchestrator project memory topic slug")
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
    require(page, "DeepDiveCrossRefs\n", "DeepDiveCrossRefs render")
    # Each ref entry has `href:` `label:` `why:` triple. Count the why: lines.
    why_count = page.count("why:")
    if not (3 <= why_count <= 7):
        raise AssertionError(
            f"compose footer must have 3-7 refs (§49); got {why_count}"
        )
    print(f"  ok: compose footer has {why_count} refs (in [3,7] range)")

    print("-- 6. POSITIVE: sidebar registers the new deep-dive entry --")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    require(sidebar, "/admin/memory/deep", "sidebar /admin/memory/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: page must NOT cite a non-existent compose-target --")
    # All compose-footer hrefs must resolve. Spot-check the high-traffic ones.
    must_resolve = [
        ("/admin/sidecar/deep", "services/frontend/app/admin/sidecar/deep/page.tsx"),
        ("/admin/agentic/control-plane", "services/frontend/app/admin/agentic/control-plane/page.tsx"),
        ("/admin/explainability/deep", "services/frontend/app/admin/explainability/deep/page.tsx"),
        ("/admin/checklist/deep", "services/frontend/app/admin/checklist/deep/page.tsx"),
    ]
    for href, file_path in must_resolve:
        if href in page and not (REPO / file_path).exists():
            raise AssertionError(
                f"compose footer cites {href} but {file_path} is missing"
            )
    print("  ok: all spot-checked compose-footer hrefs resolve to existing pages")

    print("-- 8. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
