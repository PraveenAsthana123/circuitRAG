#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: services/frontend/app/admin/sidecar/deep/page.tsx structural
contract.

Per the user's "add c4 mode for each UI for each scenario" +
"data flow form one class to other call or other component"
directives: this drill verifies the deep-dive page:

  * Lives at the §7-granted path
  * Includes C4 L1 (System Context) + L2 (Container) diagrams
  * Has 4 named scenarios (auto-feed, backlog, verdict-revert,
    retention) with sequence diagrams showing class-to-class flow
  * Mermaid component imported correctly
  * Compose-footer present with cross-refs

Eight steps. Six negative assertions.

  1. deep/page.tsx exists at the expected path.
  2. NEGATIVE: 'use client' directive present (Mermaid is client-
     side; the page must opt out of Server Component mode).
  3. NEGATIVE: imports the canonical Mermaid component (not
     re-implementing rendering inline).
  4. NEGATIVE: exactly 2 C4 diagrams (L1 + L2). More would be
     scope-creep into L3-L7 not covered by this iteration.
  5. NEGATIVE: 4 scenario sequence diagrams (sequenceDiagram blocks).
     Fewer means a scenario was dropped silently.
  6. NEGATIVE: each scenario references CONCRETE class names from
     the codebase (Advisor, AdvisorMemory, PrReviewCouncil,
     LoopWatcher, DispatchPool). Class-to-class data flow IS the
     point of these diagrams; generic boxes wouldn't satisfy the
     user's directive.
  7. NEGATIVE: compose-footer present per §49 (links to sibling
     deep-dives + the live /admin/sidecar page).
  8. NEGATIVE: file lives ONLY under
     services/frontend/app/admin/sidecar/deep/. The §7 grant is
     path-specific; no other new files under services/frontend/.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "sidecar" / "deep" / "page.tsx"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def main():
    # Step 1: file exists
    step("1. deep/page.tsx exists at the §7-granted path")
    if not PAGE.exists():
        fail(f"page.tsx missing: {PAGE}")
    text = PAGE.read_text()
    if len(text) < 2000:
        fail(f"deep page suspiciously short: {len(text)} chars")
    ok(f"deep/page.tsx exists ({len(text)} chars)")

    # Step 2: 'use client' present
    step("2. NEGATIVE: 'use client' directive present (Mermaid client-side)")
    if not re.search(r"^['\"]use client['\"]", text, re.MULTILINE):
        fail(
            "deep/page.tsx missing 'use client' - Mermaid runs client-side; "
            "without 'use client' the page renders raw mermaid source as "
            "<pre> instead of SVG diagrams"
        )
    ok("'use client' directive present")

    # Step 3: imports Mermaid component (not inline)
    step("3. NEGATIVE: imports the canonical Mermaid component")
    if not re.search(r"import\s+Mermaid\s+from", text):
        fail(
            "deep/page.tsx doesn't import Mermaid component. The "
            "canonical client-side renderer is at "
            "components/Mermaid.tsx; reusing it ensures consistent "
            "security level + asset loading."
        )
    ok("Mermaid component imported")

    # Step 4: exactly 2 C4 diagrams (flowchart)
    step("4. NEGATIVE: exactly 2 C4 flowchart diagrams (L1 + L2)")
    flowchart_count = len(re.findall(r"flowchart\s+(LR|TB|TD|RL|BT)", text))
    if flowchart_count != 2:
        fail(
            f"expected 2 C4 flowchart diagrams (L1 context + L2 container), "
            f"got {flowchart_count}. The user's directive was 'C4 mode' "
            f"per UI per scenario - L1+L2 is the foundation; per-scenario "
            f"diagrams use sequenceDiagram (different shape)."
        )
    ok(f"exactly 2 flowchart diagrams (C4 L1 + L2)")

    # Step 5: 6 sequenceDiagram scenarios. Phase 5S added the
    # telemetry-pipeline scenario as the 5th; Phase 5AA added the
    # self-healing-arc scenario (5S→5Z→5Y verdict-log replay) as
    # the 6th.
    step("5. NEGATIVE: 6 scenario sequenceDiagram blocks")
    seq_count = len(re.findall(r"sequenceDiagram", text))
    if seq_count != 6:
        fail(
            f"expected 6 scenario sequence diagrams (auto-feed, backlog, "
            f"verdict-revert, retention, telemetry-pipeline, self-healing-arc), "
            f"got {seq_count}. Each represents a distinct operator workflow; "
            f"dropping one silently reduces coverage. Adding more should bump "
            f"this drill — and the count should match the scenarios listed in "
            f"Phase 5AA's ledger entry."
        )
    ok(f"6 sequenceDiagram blocks (one per scenario, incl. Phase 5AA self-healing)")

    # Step 6: NEGATIVE - concrete class names in diagrams
    step(
        "6. NEGATIVE: scenarios reference concrete class names "
        "(class-to-class data flow, not generic boxes)"
    )
    expected_classes = [
        "AdvisorMemory",
        "PrReviewCouncil",
        "LoopWatcher",
        "DispatchPool",
    ]
    missing = [c for c in expected_classes if c not in text]
    if missing:
        fail(
            f"deep page missing concrete class names: {missing}. "
            f"User asked for 'data flow from one class to other call or "
            f"other component' - generic boxes wouldn't satisfy that. "
            f"Each named class should appear at least once in some "
            f"sequence diagram."
        )
    ok(f"all {len(expected_classes)} expected class names referenced")

    # Step 7: compose-footer present per §49
    step("7. NEGATIVE: compose-footer with cross-refs to sibling deep-dives")
    if "compose-footer" not in text.lower() and "Composes with" not in text:
        fail(
            "compose-footer missing - §49 mandate. Without it the page "
            "is a leaf node disconnected from the dependency graph."
        )
    # At least 2 sibling links
    links = re.findall(r"href=['\"]/admin/[^'\"]+['\"]", text)
    if len(links) < 2:
        fail(
            f"compose-footer should have >=2 sibling /admin/ links "
            f"(per §49 \"3-7 entries\"), found {len(links)}: {links}"
        )
    ok(f"compose-footer with {len(links)} cross-refs")

    # Step 8: NEGATIVE - file lives ONLY under deep/ (scope check)
    step("8. NEGATIVE: file lives ONLY at .../sidecar/deep/page.tsx")
    deep_dir = PAGE.parent
    files = list(deep_dir.rglob("*.tsx"))
    if len(files) != 1:
        fail(
            f"expected exactly 1 .tsx in deep/, got {len(files)}: "
            f"{[f.name for f in files]}. §7 grant is path-specific."
        )
    if files[0] != PAGE:
        fail(f"unexpected file: {files[0]}")
    if deep_dir.name != "deep" or deep_dir.parent.name != "sidecar":
        fail(f"path drift: {deep_dir}")
    ok(f"single page.tsx under .../sidecar/deep/ (scope respected)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 SIDECAR-DEEP-PAGE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
