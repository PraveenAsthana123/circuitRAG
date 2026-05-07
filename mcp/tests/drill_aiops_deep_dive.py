#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: AIOps deep-dive page contract.

Locks the /admin/aiops/deep surface so the ratchet-pattern drift
detector + planned LLM incident summarizer remain documented
together. AIOps in this codebase is the ratchet pattern (§ADR-015)
applied to operational thresholds, not an external SaaS — the
deep-dive is the only place that explains the discipline.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder language remaining; 'planned' status not
honest about NOT YET SHIPPED.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "aiops" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: aiops deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers both AIOps surfaces --")
    require(page, "autonomous-drift-detection", "autonomous drift detection topic")
    require(page, "llm-incident-summarization", "LLM incident summarization topic")
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
    require(sidebar, "/admin/aiops/deep", "sidebar /admin/aiops/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: planned topic must be honest about NOT-YET-SHIPPED --")
    # If the LLM-summarization topic claims status='shipped', that's a
    # §45.4 honesty violation — the surface doesn't exist in code yet.
    if "status: 'planned'" not in page and "status: \"planned\"" not in page:
        raise AssertionError(
            "LLM incident summarization must declare status='planned' "
            "until the service is implemented; otherwise the page lies"
        )
    require(page, "NOT YET SHIPPED", "explicit not-yet-shipped marker in body")
    print("  ok: planned topic honestly marked")

    print("-- 8. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 9. NEGATIVE: ratchet-pattern citation must point at ADR-015 --")
    # AIOps narrative without ADR reference = ungrounded. Drill rejects.
    require(page, "ADR-015", "ADR-015 ratchet-pattern citation")
    print("  ok: ratchet-pattern citation present")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
