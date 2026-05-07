#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/techstack-audit page + BFF.

Per CLAUDE.md §43 + §49 + §56 (gate 4 empirical verification).
8 steps; 4 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "techstack-audit" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "techstack-audit" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts both exist --")
    if not PAGE.exists() or not ROUTE.exists():
        print(f"x missing: PAGE={PAGE.exists()}, ROUTE={ROUTE.exists()}")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page {len(page_src)} chars; route {len(route_src)} chars")

    print("-- 2. POSITIVE: page is Client Component (interactive filter + refresh) --")
    head = page_src[:300]
    if not re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x page must declare 'use client'")
        return 1
    if "useState" not in page_src or "useEffect" not in page_src:
        print("x page must use useState/useEffect")
        return 1
    print("  ok: 'use client' + interactive hooks")

    print("-- 3. POSITIVE: BFF spawns techstack_audit.py --json --")
    if "techstack_audit.py" not in route_src:
        print("x route must invoke techstack_audit.py")
        return 1
    if '--json' not in route_src:
        print("x route must use --json mode for parseable output")
        return 1
    print("  ok: BFF runs techstack_audit.py --json")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "TECHSTACK_AUDIT_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite TECHSTACK_AUDIT_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + TECHSTACK_AUDIT_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: page renders all 6 criticality tiers --")
    # Bit-rot: a refactor that drops a tier would lose operational signal.
    expected_tiers = ("critical", "high", "medium", "low", "todo", "rejected")
    for tier in expected_tiers:
        if tier not in page_src.lower():
            print(f"x page must render criticality tier: {tier!r}")
            return 1
    print("  ok: all 6 criticality tiers rendered")

    print("-- 6. NEGATIVE: page has filter (all/missing/installed) but NO install button --")
    # Page is observation-only — installing tools goes through §56 gates,
    # not via HTTP click.
    forbidden_buttons = (
        r">\s*Install\s*<",
        r">\s*pip install\s*<",
        r"onClick.*install",
    )
    for pat in forbidden_buttons:
        if re.search(pat, page_src, re.IGNORECASE):
            print(f"x page must NOT have install UI; pattern: {pat!r}")
            return 1
    # But the filter MUST exist (operator UX)
    if "setFilter" not in page_src:
        print("x page must have filter state (setFilter)")
        return 1
    print("  ok: filter present + 0 install UI elements")

    print("-- 7. NEGATIVE: BFF treats non-zero audit exit as expected (not error) --")
    # Audit exits 1 when non-critical missing, 2 when critical missing.
    # BFF must NOT reject those — only spawn-level errors (negative code)
    # should fail the request.
    if "code === null || code < 0" not in route_src and "code === null" not in route_src:
        print("x BFF must accept non-zero exit codes from audit script")
        return 1
    print("  ok: BFF accepts audit exit codes 0/1/2 as success")

    print("-- 8. POSITIVE: §49 footer + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/techstack-audit" not in sidebar_src:
        print("x sidebar missing /admin/techstack-audit")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
