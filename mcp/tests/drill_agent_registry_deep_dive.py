#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Agent registry deep-dive page contract.

Locks /admin/agent-registry/deep covering both shipped registries —
orchestrator agents (AgentRoleSpec + 4 default specs) and sidecar
council (chair / authors / cross-reviewer pattern). Without this
deep-dive, operators have no canonical answer to "which agents
exist + what each can do + what each logs".

Negative assertions cover: page absent; sidebar entry missing;
compose-footer stripped; canonical universal-framework fields
absent; placeholder text remaining; orchestrator agent_registry.py
file path not cited (so drift between page + code is detectable);
sidecar council pattern not cited.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "agent-registry" / "deep" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
ORCH_REG = REPO / "services" / "agent-orchestrator-svc" / "app" / "agent_registry.py"
SIDECAR_ADV = REPO / "services" / "sidecar-advisor" / "advisor.py"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: agent-registry deep-dive page exists --")
    if not PAGE.exists():
        raise AssertionError(f"missing page: {PAGE.relative_to(REPO)}")
    page = PAGE.read_text(encoding="utf-8")
    print("  ok: page file exists")

    print("-- 2. POSITIVE: page imports the canonical deep-dive infra --")
    require(page, "UniversalDeepDive", "UniversalDeepDive import")
    require(page, "DeepDiveCrossRefs", "DeepDiveCrossRefs import")
    print("  ok: canonical infra imported")

    print("-- 3. POSITIVE: page covers both registries --")
    require(page, "agent-registry-orchestrator", "orchestrator registry topic")
    require(page, "sidecar-council-roles", "sidecar council topic")
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
    require(sidebar, "/admin/agent-registry/deep", "sidebar /admin/agent-registry/deep link")
    print("  ok: sidebar entry registered")

    print("-- 7. NEGATIVE: page must cite the actual orchestrator registry source --")
    # If the page drifts and stops citing the canonical file, drift between
    # page narrative + code becomes invisible.
    require(page, "agent_registry.py", "orchestrator agent_registry.py citation")
    require(page, "DEFAULT_AGENT_SPECS", "DEFAULT_AGENT_SPECS reference")
    if not ORCH_REG.exists():
        raise AssertionError(
            f"page cites {ORCH_REG.relative_to(REPO)} but file does not exist"
        )
    print("  ok: orchestrator registry source cited and exists")

    print("-- 8. NEGATIVE: page must cite the sidecar council pattern --")
    require(page, "advisor.py", "sidecar advisor.py citation")
    require(page, "drill_sidecar_pr_review_council", "council drill citation")
    if not SIDECAR_ADV.exists():
        raise AssertionError(
            f"page cites {SIDECAR_ADV.relative_to(REPO)} but file does not exist"
        )
    print("  ok: sidecar council pattern cited and source exists")

    print("-- 9. NEGATIVE: page must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in page:
            raise AssertionError(f"forbidden placeholder in page: {forbidden}")
    print("  ok: no placeholder language remains")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
