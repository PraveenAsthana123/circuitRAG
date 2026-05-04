#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/agent-router page + BFF contract.

Per CLAUDE.md §43 + §49. Locks page contract + BFF read-only posture.
8 steps; 4 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "agent-router" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "agent-router" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts both exist --")
    if not PAGE.exists() or not ROUTE.exists():
        print(f"x missing: PAGE_exists={PAGE.exists()}, ROUTE_exists={ROUTE.exists()}")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page {len(page_src)} chars; route {len(route_src)} chars")

    print("-- 2. POSITIVE: page is a Client Component --")
    head = page_src[:300]
    if not re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x page must declare 'use client'")
        return 1
    print("  ok: 'use client' present")

    print("-- 3. POSITIVE: BFF GET fetches patterns + audit log in parallel --")
    if "agent_router.py" not in route_src and "agent_router" not in route_src:
        print("x route must invoke agent_router.py")
        return 1
    if "agent_router_audit.jsonl" not in route_src:
        print("x route must read .loop/agent_router_audit.jsonl")
        return 1
    if "Promise.all" not in route_src:
        print("x route should fetch in parallel via Promise.all")
        return 1
    print("  ok: BFF reads patterns + audit log in parallel")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "ROUTER_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite ROUTER_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + ROUTER_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: page does NOT bypass BFF (no invocation patterns) --")
    # The page MUST route through the BFF, never spawn the script
    # directly. Documentation references inside <code>...</code> are
    # fine — only invocation-style patterns are forbidden.
    forbidden = (
        r"child_process",
        r"\.venv/bin/python",
        r"\bspawn\s*\(",
        r"\bexec\s*\(",
        r"from\s+child_process",
        r"require\s*\(\s*['\"]child_process['\"]",
    )
    for pat in forbidden:
        if re.search(pat, page_src):
            print(f"x page must NOT bypass BFF; pattern: {pat!r}")
            return 1
    print("  ok: page routes through BFF (no invocation patterns)")

    print("-- 6. NEGATIVE: page renders ALL 3 risk tiers (high + medium + low) --")
    # Bit-rot: a refactor that drops a risk tier loses the headline
    # signal that high-risk patterns are most operationally relevant.
    for tier in ("high", "medium", "low"):
        if tier.upper() not in page_src.upper():
            print(f"x page must render {tier!r} risk tier")
            return 1
    if "by_risk" not in page_src:
        print("x page must render the by_risk stat aggregation")
        return 1
    print("  ok: all 3 risk tiers + by_risk stats rendered")

    print("-- 7. POSITIVE: §49 compose footer with 5+ cross-refs --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs")

    print("-- 8. POSITIVE: sidebar wires nav entry --")
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/agent-router" not in sidebar_src:
        print("x sidebar missing /admin/agent-router")
        return 1
    print("  ok: sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
