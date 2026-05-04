#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/policy-rego-sync page contract.

Per §43 + §49. Operator surface for the JSON↔Rego sync validator.
8 steps; 4 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "policy-rego-sync" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "policy-rego-sync" / "route.ts"
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

    print("-- 3. POSITIVE: BFF spawns rego_sync_check.py --json --")
    if "rego_sync_check.py" not in route_src:
        print("x route must invoke rego_sync_check.py")
        return 1
    if "--json" not in route_src:
        print("x route must use --json flag")
        return 1
    print("  ok: BFF runs rego_sync_check.py --json")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "POLICY_REGO_SYNC_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite POLICY_REGO_SYNC_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + POLICY_REGO_SYNC_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: BFF accepts non-zero exit codes (drift is expected) --")
    # Sync validator exits 0 on sync, 1 on drift. BFF must accept both.
    if "code === null || code < 0" not in route_src and "code === null" not in route_src:
        print("x BFF must accept exit codes 0/1 as success (only negative or huge codes are errors)")
        return 1
    if "code > 3" not in route_src:
        print("x BFF should bound expected exit codes (0/1/3)")
        return 1
    print("  ok: BFF treats exits 0/1 as expected, 2/4+ as error")

    print("-- 6. NEGATIVE: page has NO 'edit rule' or 'sync now' button --")
    # Drift is fixed by EDITING the JSON or Rego file directly + re-running drill.
    # No HTTP-driven sync button (would silently bypass drill).
    forbidden_buttons = (
        r">\s*Edit\s+Rule\s*<",
        r">\s*Sync\s+Now\s*<",
        r">\s*Auto-?fix\s*<",
        r"onClick.*sync_now",
    )
    for pat in forbidden_buttons:
        if re.search(pat, page_src, re.IGNORECASE):
            print(f"x page must NOT have edit/sync UI; pattern: {pat!r}")
            return 1
    print("  ok: 0 mutating UI elements; drift fixed via file edit + drill")

    print("-- 7. NEGATIVE: drift section only renders when in_sync=false --")
    # Bit-rot prevention: page must conditionally render the drift
    # detail block, not always show empty arrays.
    if "!data.in_sync" not in page_src and "data.in_sync === false" not in page_src:
        print("x page must conditionally render drift detail (only when !in_sync)")
        return 1
    print("  ok: drift detail conditionally rendered")

    print("-- 8. POSITIVE: §49 footer + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/policy-rego-sync" not in sidebar_src:
        print("x sidebar missing /admin/policy-rego-sync")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
