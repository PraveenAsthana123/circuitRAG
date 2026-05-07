#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Ops fabric deep-dive page contract.

Locks /admin/ops-fabric/deep covering three operational substrates —
runbooks catalog, integrations (webhooks + MCP + RAG), and
correlation_id-led debugging. All three SHIPPED. Drill enforces
canonical citations to docs/runbooks/ + observability.py +
.loop/<service>.env pattern so the page can't drift away from the
substrates it documents.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; runbook directory citation
missing; correlation_id source citation missing.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "ops-fabric" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
RUNBOOKS_DIR = REPO / "docs" / "runbooks"
OBSERVABILITY = REPO / "libs" / "py" / "documind_core" / "observability.py"
ALERTMGR_RUNBOOK = REPO / "docs" / "runbooks" / "alertmanager-webhook.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: ops-fabric deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers all 3 substrates --")
    require(page, "operations-runbooks", "runbooks topic")
    require(page, "integrations", "integrations topic")
    require(page, "debugging-fixing", "debugging topic")
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
    require(sidebar, "/admin/ops-fabric/deep", "sidebar /admin/ops-fabric/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: page must cite docs/runbooks/ + key runbook files --")
    require(page, "docs/runbooks/", "docs/runbooks/ directory citation")
    require(page, "alertmanager-webhook.md", "alertmanager runbook citation")
    if not RUNBOOKS_DIR.exists():
        raise AssertionError("docs/runbooks/ missing")
    if not ALERTMGR_RUNBOOK.exists():
        raise AssertionError("alertmanager-webhook.md runbook missing")
    print("  ok: runbooks dir + key file cited and exist")

    print("-- 8. NEGATIVE: page must cite observability.py for correlation_id source --")
    require(page, "observability.py", "observability.py citation")
    require(page, "correlation_id", "correlation_id pattern")
    require(page, "OTel baggage", "OTel baggage propagation reference")
    if not OBSERVABILITY.exists():
        raise AssertionError(
            f"page cites observability.py but {OBSERVABILITY.relative_to(REPO)} missing"
        )
    print("  ok: observability.py + correlation_id + baggage all referenced + source exists")

    print("-- 9. NEGATIVE: integration secret pattern .loop/<svc>.env must be cited --")
    # The .loop/<service>.env (chmod 600) pattern is the integration secret
    # discipline. If the page drops this, integrations may regress to
    # hardcoded URLs.
    require(page, ".loop/", ".loop/ secret pattern")
    require(page, "chmod 600", "chmod 600 discipline")
    print("  ok: .loop/<svc>.env (chmod 600) secret pattern cited")

    print("-- 10. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
