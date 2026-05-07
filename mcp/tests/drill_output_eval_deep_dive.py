#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Output evaluation deep-dive page contract.

Locks the /admin/output-eval/deep surface so the citation-discipline
hallucination guardrail (shipped) and the golden-set regression
harness (partial) remain documented together. Output evaluation is
a §38 governance gate — without the deep-dive, operators have no
canonical reference for either layer.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; PARTIAL surface not honestly
marked; references to §38 / §48 governance gates absent.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "output-eval" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: output-eval deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers both eval surfaces --")
    require(page, "hallucination-citation-eval", "hallucination/citation topic")
    require(page, "evaluation-harness", "evaluation harness topic")
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
    require(sidebar, "/admin/output-eval/deep", "sidebar /admin/output-eval/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: harness must declare PARTIAL status honestly --")
    if "status: 'partial'" not in page and "status: \"partial\"" not in page:
        raise AssertionError(
            "evaluation-harness must declare status='partial' until the "
            "golden set + CI integration ship; otherwise the page lies"
        )
    require(page, "PARTIAL", "explicit PARTIAL marker in body")
    print("  ok: harness honestly marked partial")

    print("-- 8. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 9. NEGATIVE: governance gates must be cited (§38 + §48) --")
    require(page, "§38", "§38 governance-gate citation")
    require(page, "§48", "§48 explainability citation")
    print("  ok: both governance gates cited")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
