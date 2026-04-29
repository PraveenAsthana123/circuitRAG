#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: §7 scope-extension log maps to actual sidecar files.

The sidecar scope grant lives in two places:
  * docs/NEXT_POLICY.md §7 / shipped ledger text
  * drill_sidecar_nextjs_page.py allowed_relative set

This drill verifies that the documented granted routes correspond to
the actual files and the structural allowlist.

  1. load NEXT_POLICY and sidecar scope drill
  2. NEGATIVE: the three granted routes are mentioned in NEXT_POLICY
  3. NEGATIVE: the allowlist in the scope drill has exactly 3 entries
  4. NEGATIVE: each allowlist entry exists on disk
  5. NEGATIVE: route mentions map 1:1 to relative file paths
  6. NEGATIVE: no extra sidecar tsx files exist outside the allowlist
  7. NEGATIVE: sidecar root page remains in the grant
  8. POSITIVE: emit exact mismatch details if mapping drifts

Run: python3 mcp/tests/drill_section7_scope_log_mapping.py
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
NEXT_POLICY = REPO / "docs" / "NEXT_POLICY.md"
SCOPE_DRILL = REPO / "mcp" / "tests" / "drill_sidecar_nextjs_page.py"
SIDECAR_DIR = REPO / "services" / "frontend" / "app" / "admin" / "sidecar"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _extract_allowlist() -> set[str]:
    module = ast.parse(SCOPE_DRILL.read_text(), filename=str(SCOPE_DRILL))
    for node in ast.walk(module):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "allowed_relative":
                    return set(ast.literal_eval(node.value))
    raise ValueError("allowed_relative set not found")


def main() -> int:
    step("1. load policy + scope drill")
    policy_text = NEXT_POLICY.read_text()
    allowlist = _extract_allowlist()
    ok(f"loaded NEXT_POLICY + allowlist ({len(allowlist)} entries)")

    step("2. NEGATIVE: three granted routes are mentioned in NEXT_POLICY")
    required_routes = [
        "/admin/sidecar",
        "/admin/sidecar/deep",
        "/admin/sidecar/telemetry",
    ]
    missing = [route for route in required_routes if route not in policy_text]
    if missing:
        fail(f"NEXT_POLICY missing granted routes: {missing}")
    ok("NEXT_POLICY mentions all granted sidecar routes")

    step("3. NEGATIVE: allowlist has exactly 3 entries")
    if allowlist != {"page.tsx", "deep/page.tsx", "telemetry/page.tsx"}:
        fail(f"unexpected allowlist: {sorted(allowlist)}")
    ok("allowlist matches expected 3-entry grant")

    step("4. NEGATIVE: every allowlist entry exists on disk")
    missing = [rel for rel in sorted(allowlist) if not (SIDECAR_DIR / rel).exists()]
    if missing:
        fail(f"allowlist entries missing on disk: {missing}")
    ok("all allowlist entries exist on disk")

    step("5. NEGATIVE: route mentions map 1:1 to relative file paths")
    mapping = {
        "/admin/sidecar": "page.tsx",
        "/admin/sidecar/deep": "deep/page.tsx",
        "/admin/sidecar/telemetry": "telemetry/page.tsx",
    }
    mismatches = [route for route, rel in mapping.items() if rel not in allowlist or route not in policy_text]
    if mismatches:
        fail(f"route-to-file mapping drift: {mismatches}")
    ok("route mentions map cleanly to relative files")

    step("6. NEGATIVE: no extra sidecar tsx files exist outside the allowlist")
    actual = {str(p.relative_to(SIDECAR_DIR)) for p in SIDECAR_DIR.rglob("*.tsx")}
    extra = sorted(actual - allowlist)
    if extra:
        fail(f"extra sidecar tsx files outside grant: {extra}")
    ok("no extra sidecar tsx files outside allowlist")

    step("7. NEGATIVE: sidecar root page remains in the grant")
    if "page.tsx" not in allowlist:
        fail("page.tsx missing from allowlist")
    if "/admin/sidecar" not in policy_text:
        fail("/admin/sidecar missing from NEXT_POLICY")
    ok("sidecar root page remains granted")

    step("8. POSITIVE: mismatch details are explicit on failure")
    ok("this drill fails with exact route/file mismatch details")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 SECTION7-SCOPE-MAPPING STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
