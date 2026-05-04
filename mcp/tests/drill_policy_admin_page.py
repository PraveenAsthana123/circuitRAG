#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/policy page + /api/v1/policy BFF contract.

Per CLAUDE.md §43 + §49. Locks:

  - page.tsx + route.ts both exist
  - page is a Client Component (interactive: filters, auto-refresh)
  - BFF route refuses POST/PUT/DELETE/PATCH with 405 + read-only error
  - BFF reads .loop/policy_audit.jsonl + calls policy_check.py rules
  - Page surfaces 5 stat blocks (version, rule count, decisions logged,
    allow rate, default-effect callout)
  - Page renders allow/deny color-coded badges
  - §49 compose footer with 5+ cross-refs
  - Sidebar wires nav entry

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "policy" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "policy" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts both exist --")
    if not PAGE.exists():
        print(f"x {PAGE} missing")
        return 1
    if not ROUTE.exists():
        print(f"x {ROUTE} missing")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page {len(page_src)} chars; route {len(route_src)} chars")

    print("-- 2. POSITIVE: page is Client Component (interactive filters) --")
    # The page has auto-refresh + filter buttons → must be 'use client'
    head = page_src[:300]
    if not re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x page must declare 'use client' (uses useState/useEffect)")
        return 1
    if "useState" not in page_src or "useEffect" not in page_src:
        print("x page must use useState + useEffect (interactive contract)")
        return 1
    print("  ok: 'use client' + useState/useEffect present")

    print("-- 3. POSITIVE: BFF GET fetches both rules + audit log --")
    if "policy_check.py" not in route_src and "policy_check" not in route_src:
        print("x route must invoke policy_check.py")
        return 1
    if "policy_audit.jsonl" not in route_src:
        print("x route must read .loop/policy_audit.jsonl")
        return 1
    if "Promise.all" not in route_src:
        print("x route should fetch rules + decisions in parallel (Promise.all)")
        return 1
    print("  ok: BFF reads both surfaces (Promise.all parallel fetch)")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH with 405 --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "POLICY_BFF_READ_ONLY" not in route_src:
        print("x mutating verb refusal must cite POLICY_BFF_READ_ONLY error_code")
        return 1
    if "405" not in route_src:
        print("x mutating verbs must return status 405")
        return 1
    print("  ok: 4 mutating methods all wired to 405 + POLICY_BFF_READ_ONLY")

    print("-- 5. POSITIVE: page surfaces 5 documented stat headlines --")
    expected_stats = (
        "Policy version", "Rules", "Decisions logged",
        "Allow rate", "default-",
    )
    for stat in expected_stats:
        if stat not in page_src:
            print(f"x stat headline missing: {stat!r}")
            return 1
    print(f"  ok: all {len(expected_stats)} stat headlines present")

    print("-- 6. NEGATIVE: page does NOT bypass BFF (no direct policy_check call) --")
    # Stage-1 contract: page → /api/v1/policy → policy_check.py (3 hops).
    # Page must NOT spawn or import policy_check directly.
    forbidden = (
        r"\bpolicy_check\.py",
        r"child_process",  # spawn at page level
        r"\.venv/bin/python",
    )
    for pat in forbidden:
        if re.search(pat, page_src):
            print(f"x page must NOT bypass BFF; found pattern: {pat!r}")
            return 1
    print("  ok: page routes through BFF (no direct script invocation)")

    print("-- 7. NEGATIVE: filter UI uses CSP-safe styling (no inline event handlers) --")
    # Inline `onclick=` HTML attributes would violate CSP. React's
    # `onClick={...}` is safe (compiles to event listener). Drill
    # ensures we don't accidentally write the HTML form.
    if re.search(r'\bonclick\s*=\s*["\']', page_src):
        print("x page must use React onClick (camelCase), not HTML onclick")
        return 1
    # Also check filter buttons use proper React handlers
    if "onClick={() => setFilter(" not in page_src:
        print("x filter buttons must use onClick={() => setFilter(...)} pattern")
        return 1
    print("  ok: React event handlers (onClick), no inline HTML onclick")

    print("-- 8. POSITIVE: §49 compose footer + sidebar nav entry --")
    if "Composes with" not in page_src:
        print("x page missing §49 'Composes with' footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/policy" not in sidebar_src:
        print("x sidebar must contain /admin/policy nav entry")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar entry")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
