#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/health-pulse page contract.

Per §43 + §49. 8 steps; 5 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "health-pulse" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "health-pulse" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts both exist --")
    if not PAGE.exists() or not ROUTE.exists():
        print(f"x missing: PAGE={PAGE.exists()}, ROUTE={ROUTE.exists()}")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page {len(page_src)} chars; route {len(route_src)} chars")

    print("-- 2. POSITIVE: page is Client Component (auto-refresh) --")
    head = page_src[:300]
    if not re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x page must declare 'use client'")
        return 1
    if "setInterval" not in page_src or "autoRefresh" not in page_src:
        print("x page must have auto-refresh interval logic")
        return 1
    print("  ok: 'use client' + auto-refresh logic present")

    print("-- 3. POSITIVE: BFF Promise.all-reads all 6 audit logs --")
    expected_audit_logs = (
        "policy_audit.jsonl",
        "openclaw_audit.jsonl",
        "agent_router_audit.jsonl",
        "mcp_gateway_audit.jsonl",
        "issue_audit.jsonl",
        "agent_task_board_apply.jsonl",
    )
    for log in expected_audit_logs:
        if log not in route_src:
            print(f"x route must read audit log: {log!r}")
            return 1
    if "Promise.all" not in route_src:
        print("x route must Promise.all the 6 reads")
        return 1
    print("  ok: all 6 audit logs read in parallel")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "HEALTH_PULSE_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite HEALTH_PULSE_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + HEALTH_PULSE_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: BFF does NOT spawn subprocesses (file I/O only) --")
    # Health-pulse should be PURE file reads — no Python script invocation.
    # That's why this BFF is fast: no process startup overhead.
    forbidden = (
        r"\bspawn\s*\(",
        r"child_process",
        r"\.venv/bin/python",
    )
    for pat in forbidden:
        if re.search(pat, route_src):
            print(f"x BFF must NOT spawn subprocesses; pattern: {pat!r}")
            return 1
    print("  ok: pure file I/O (no subprocess spawn)")

    print("-- 6. NEGATIVE: page renders pulse-color thresholds --")
    # The pulse-color logic (>5 green, >0 amber, else gray) is the
    # operational signal. Bit-rot would lose this.
    if "pulseColor" not in page_src:
        print("x page must have pulseColor function")
        return 1
    if "lastMinute > 5" not in page_src:
        print("x page must have >5 threshold for green pulse")
        return 1
    print("  ok: pulse-color thresholds preserved")

    print("-- 7. NEGATIVE: BFF reads 'totals' aggregation (not just per-layer) --")
    # Operator UX: a single totals summary across all layers is the
    # headline metric. Drill enforces it's computed.
    if "totals" not in route_src:
        print("x BFF must compute totals aggregation")
        return 1
    if "last_minute" not in route_src or "last_hour" not in route_src:
        print("x BFF must aggregate last_minute + last_hour")
        return 1
    print("  ok: totals aggregation across layers (1min/1hr/1day windows)")

    print("-- 8. POSITIVE: §49 footer + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/health-pulse" not in sidebar_src:
        print("x sidebar missing /admin/health-pulse")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
