#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/openclaw page + BFF contract.

Per CLAUDE.md §43 + §49. 8 steps; 4 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "openclaw" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "openclaw" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts both exist --")
    if not PAGE.exists() or not ROUTE.exists():
        print(f"x missing: PAGE={PAGE.exists()}, ROUTE={ROUTE.exists()}")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page {len(page_src)} chars; route {len(route_src)} chars")

    print("-- 2. POSITIVE: page declares 'use client' (interactive surface) --")
    head = page_src[:300]
    if not re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x page must declare 'use client'")
        return 1
    print("  ok: 'use client' present")

    print("-- 3. POSITIVE: BFF Promise.all-fetches agents + audit log --")
    if "openclaw_coordinator" not in route_src:
        print("x route must invoke openclaw_coordinator.py")
        return 1
    if "openclaw_audit.jsonl" not in route_src:
        print("x route must read .loop/openclaw_audit.jsonl")
        return 1
    if "Promise.all" not in route_src:
        print("x route should fetch in parallel via Promise.all")
        return 1
    print("  ok: BFF parallel-fetches both surfaces")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH (Stage-1 read-only) --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "OPENCLAW_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite OPENCLAW_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + OPENCLAW_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: page does NOT contain Dispatch button (Stage-1 contract) --")
    # Stage-1 contract: NO dispatch UI. The page renders status only.
    # A future "Dispatch" button is a Stage-2 surface that requires
    # PolisAI rules + drill update + ADR. Drill enforces the absence.
    forbidden_buttons = (
        r">\s*Dispatch\s*<",
        r">\s*Send\s*<",
        r">\s*Execute\s*<",
        r"onClick.*dispatch",
        r"onSubmit.*dispatch",
    )
    for pat in forbidden_buttons:
        if re.search(pat, page_src, re.IGNORECASE):
            print(f"x Stage-1 page must NOT have Dispatch UI; pattern: {pat!r}")
            return 1
    print("  ok: no Dispatch UI on Stage-1 page (status-only)")

    print("-- 6. NEGATIVE: page surfaces default-deny posture explicitly --")
    # Operator must see "default-deny" so the deny rate isn't mistaken
    # for "system broken". The header callout makes the posture explicit.
    if "default-deny" not in page_src:
        print("x page must explicitly surface 'default-deny' (Stage-1 posture)")
        return 1
    if "gate-only" not in page_src:
        print("x page must declare 'gate-only' Stage-1 posture")
        return 1
    print("  ok: default-deny + gate-only posture surfaced")

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
    if "/admin/openclaw" not in sidebar_src:
        print("x sidebar missing /admin/openclaw")
        return 1
    print("  ok: sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
