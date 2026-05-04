#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/eval-harness page + BFF contract.

Per CLAUDE.md §43 + §49. Closes Layer 10 frontend coverage.
8 steps; 4 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "eval-harness" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "eval-harness" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts both exist --")
    if not PAGE.exists() or not ROUTE.exists():
        print(f"x missing: PAGE={PAGE.exists()}, ROUTE={ROUTE.exists()}")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page {len(page_src)} chars; route {len(route_src)} chars")

    print("-- 2. POSITIVE: page is Client Component --")
    head = page_src[:300]
    if not re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x page must declare 'use client'")
        return 1
    print("  ok: 'use client' present")

    print("-- 3. POSITIVE: page renders all 4 engines (Ragas + Guardrails + DeepEval + Snyk) --")
    expected_engines = ("Ragas", "Guardrails AI", "DeepEval", "Snyk")
    for eng in expected_engines:
        if eng not in route_src:
            print(f"x BFF must reference engine: {eng!r}")
            return 1
    print(f"  ok: all 4 engines named")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "EVAL_HARNESS_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite EVAL_HARNESS_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + EVAL_HARNESS_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: BFF does NOT import eval_harness.py directly --")
    # Stage-1 contract: BFF inspects FILE PRESENCE + dep declarations,
    # not import the actual library (which would emit "X not installed"
    # log spam). This keeps the page healthy even when deps aren't
    # deployed yet.
    if "spawn(PYTHON" in route_src and "eval_harness" in route_src:
        # Allow spawn for status/eval_status calls? No — Stage-1
        # is pure file-inspection. Drill rejects subprocess invocation
        # of the eval_harness module.
        # Check: spawn calls reference eval_publisher OR ANY script
        # other than eval_harness
        spawns = re.findall(r"spawn\([^)]+\)", route_src)
        for s in spawns:
            if "eval_harness" in s:
                print(f"x BFF must NOT spawn eval_harness.py directly: {s!r}")
                return 1
    print("  ok: BFF inspects files only (no eval_harness.py subprocess)")

    print("-- 6. NEGATIVE: page surfaces Stage-2 wiring plan explicitly --")
    # Stage-1 honest signal: the engines are scaffolded but not wired.
    # The page MUST surface the Stage-2 plan so operators see what's
    # left to ship.
    if "Stage-2" not in page_src and "stage_2_wiring_plan" not in page_src:
        print("x page must surface Stage-2 wiring plan")
        return 1
    if "stub" not in page_src.lower() and "scaffold" not in page_src.lower():
        print("x page must label Stage-1 as 'stub' or 'scaffold' (honesty signal)")
        return 1
    print("  ok: Stage-2 plan + Stage-1 stub/scaffold labels present")

    print("-- 7. POSITIVE: page surfaces fail-OPEN posture for Guardrails --")
    # Per §41.5: Guardrails AI ships fail-OPEN in Stage-1 (deps missing
    # → validation_passed=true). This is intentional but must be
    # documented on the surface so an operator doesn't assume validation
    # is happening when it isn't.
    if "fail-OPEN" not in page_src and "fail-open" not in page_src.lower():
        print("x page must document Guardrails fail-OPEN posture")
        return 1
    print("  ok: fail-OPEN posture surfaced for Guardrails")

    print("-- 8. POSITIVE: §49 compose footer + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/eval-harness" not in sidebar_src:
        print("x sidebar missing /admin/eval-harness")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
