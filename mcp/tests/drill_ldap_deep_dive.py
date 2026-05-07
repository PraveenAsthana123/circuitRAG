#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: LDAP deep-dive page contract.

Locks the /admin/ldap/deep surface. The page already exists with the
universal-framework topic + compose-with footer; without this drill,
both can silently regress when someone refactors the deep-dive
catalog.

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; tombstone-on-delete contract
not documented (the most-load-bearing LDAP invariant).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "ldap" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: LDAP deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers the LDAP enterprise-sync topic --")
    require(page, "LDAP — enterprise identity sync", "LDAP topic title")
    print("  ok: LDAP topic present")

    print("-- 4. POSITIVE: topic includes the universal-framework canonical fields --")
    for needle, label in [
        ("interviewLine", "interview-line section"),
        ("starStory", "STAR-format story"),
        ("failureModes", "failure modes table"),
        ("implementationSteps", "implementation steps"),
        ("monitoring", "monitoring metrics"),
        ("testing", "testing references"),
    ]:
        require(page, needle, label)
    print("  ok: 6 canonical universal-framework fields present")

    print("-- 5. POSITIVE: compose-with footer (§49) renders with 3-7 refs --")
    why_count = page.count("why:")
    if not (3 <= why_count <= 7):
        raise AssertionError(
            f"compose footer must have 3-7 refs (§49); got {why_count}"
        )
    print(f"  ok: compose footer has {why_count} refs (in [3,7] range)")

    print("-- 6. POSITIVE: sidebar registers the deep-dive entry --")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    require(sidebar, "/admin/ldap/deep", "sidebar /admin/ldap/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: tombstone-on-delete invariant must be documented --")
    # Without tombstoning, audit_log rows lose username resolution and
    # historical decisions become unattributable. Most-load-bearing LDAP
    # invariant in this codebase.
    require(page, "tombstone", "tombstone-on-delete invariant")
    require(page, "objectGUID", "objectGUID-as-identity invariant")
    print("  ok: tombstone + objectGUID invariants documented")

    print("-- 8. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 9. NEGATIVE: SOC2 CC6.1 offboarding tie-back must be cited --")
    # LDAP offboarding closure is the §47 / §38 SOC2 evidence path.
    # If the page drifts and stops citing this, the audit trail breaks.
    require(page, "SOC2", "SOC2 audit citation")
    print("  ok: SOC2 audit tie-back present")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
