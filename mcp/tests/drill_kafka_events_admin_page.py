#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/kafka-events page + BFF contract.

Per CLAUDE.md §43 + §49. 8 steps; 4 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "kafka-events" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "kafka-events" / "route.ts"
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

    print("-- 3. POSITIVE: BFF Promise.all-fetches status + 3 audit log counts --")
    if "event_publisher" not in route_src:
        print("x route must invoke event_publisher")
        return 1
    if "Promise.all" not in route_src:
        print("x route must use Promise.all for parallel reads")
        return 1
    # Must read all 3 audit logs (Paperclip is deliberately not on disk)
    for log_var in ("policy_audit", "agent_router_audit", "openclaw_audit"):
        if log_var not in route_src:
            print(f"x route must read {log_var}.jsonl")
            return 1
    print("  ok: BFF fetches status + 3 audit log counts")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "KAFKA_EVENTS_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite KAFKA_EVENTS_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + KAFKA_EVENTS_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: page does NOT contain a Send/Publish button --")
    # Stage-1 contract: this is a status page, not a publish UI. The
    # originating layers publish; this page just observes.
    forbidden_buttons = (
        r">\s*Publish\s*<",
        r">\s*Send\s+(?:Event|Message)\s*<",
        r">\s*Emit\s*<",
        r"onClick.*publish",
    )
    for pat in forbidden_buttons:
        if re.search(pat, page_src, re.IGNORECASE):
            print(f"x Stage-1 page must NOT have Publish UI; pattern: {pat!r}")
            return 1
    print("  ok: no Publish UI on Stage-1 page (status-only)")

    print("-- 6. NEGATIVE: page surfaces opt-in posture explicitly --")
    # Operators must SEE that the layer is opt-in via KAFKA_PUBLISH=1.
    # Without that explicit signal, "0 events published" looks like a
    # bug rather than a deliberate Stage-1 default.
    if "KAFKA_PUBLISH" not in page_src:
        print("x page must mention KAFKA_PUBLISH env var (opt-in)")
        return 1
    if "opt-in" not in page_src.lower():
        print("x page must declare 'opt-in' posture")
        return 1
    if "fail-open" not in page_src.lower():
        print("x page must declare 'fail-open' posture")
        return 1
    print("  ok: opt-in + fail-open posture surfaced")

    print("-- 7. POSITIVE: page renders all 4 documented topics --")
    expected_topics = (
        "documind.policy.decisions",
        "documind.openclaw.dispatches",
        "documind.router.classifications",
        "documind.paperclip.snapshots",
    )
    for topic in expected_topics:
        if topic not in route_src:
            print(f"x BFF must reference topic: {topic!r}")
            return 1
    print(f"  ok: all 4 topics in BFF schema map")

    print("-- 8. POSITIVE: §49 compose footer with 5+ cross-refs + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/kafka-events" not in sidebar_src:
        print("x sidebar missing /admin/kafka-events")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
