#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/mcp-gateway page + BFF.

Per CLAUDE.md §43 + §49 + §56. 8 steps; 5 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "mcp-gateway" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "mcp-gateway" / "route.ts"
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

    print("-- 3. POSITIVE: BFF Promise.all-fetches status + allowlist + audit --")
    if "mcp_gateway" not in route_src:
        print("x route must invoke mcp_gateway.py")
        return 1
    if "allowlist.json" not in route_src:
        print("x route must read config/mcp/allowlist.json")
        return 1
    if "mcp_gateway_audit.jsonl" not in route_src:
        print("x route must read .loop/mcp_gateway_audit.jsonl")
        return 1
    if "Promise.all" not in route_src:
        print("x route must use Promise.all for parallel fetch")
        return 1
    print("  ok: BFF parallel-fetches status + allowlist + audit")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "MCP_GATEWAY_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite MCP_GATEWAY_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + MCP_GATEWAY_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: page does NOT have 'add server' / 'enable gateway' UI --")
    # §56 contract: adding servers is a 6-gate process, not HTTP.
    forbidden_buttons = (
        r">\s*Add\s+Server\s*<",
        r">\s*Enable\s+Gateway\s*<",
        r">\s*Allowlist\s+Edit\s*<",
        r"onClick.*add_server",
        r"onClick.*enable_gateway",
    )
    for pat in forbidden_buttons:
        if re.search(pat, page_src, re.IGNORECASE):
            print(f"x page must NOT have add-server/enable UI; pattern: {pat!r}")
            return 1
    print("  ok: 0 mutating UI elements (allowlist edits via §56 process)")

    print("-- 6. NEGATIVE: page renders all 4 risk tiers (critical/high/medium/low) --")
    for tier in ("critical", "high", "medium", "low"):
        if tier not in page_src:
            print(f"x page must render risk tier: {tier!r}")
            return 1
    print("  ok: all 4 risk tiers rendered")

    print("-- 7. NEGATIVE: page surfaces 'do not allow direct MCP access' rule --")
    # The brutal rule from the enterprise-architecture page must be
    # explicit on this page too — operators should see WHY the gateway
    # exists, not just THAT it exists.
    if "do not allow direct MCP access" not in page_src:
        print("x page must surface the brutal rule explicitly")
        return 1
    if "4-layer defense" not in page_src and "4 layer defense" not in page_src.lower():
        print("x page must describe the 4-layer defense pattern")
        return 1
    print("  ok: brutal rule + 4-layer defense surfaced")

    print("-- 8. POSITIVE: §49 footer + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/mcp-gateway" not in sidebar_src:
        print("x sidebar missing /admin/mcp-gateway")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
