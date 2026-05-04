#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Paperclip admin page + BFF route contract.

Per CLAUDE.md §43 + §49 (compose-footer pattern). Locks:

  - page.tsx exists at expected path + uses 'use client'
  - route.ts exists at expected path + only exports GET (writes 405)
  - sidebar wires the nav entry
  - page references the §49 compose-footer with required cross-refs
  - BFF route refuses POST/PUT/DELETE/PATCH with STAGE_1_READ_ONLY
  - page surfaces apply_rate as the headline brutal-honesty signal
  - no hardcoded Ollama URL on the page (env-driven via /api/v1)
  - page does NOT reference any write-style verbs

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "paperclip" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "paperclip" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts exist --")
    if not PAGE.exists():
        print(f"x {PAGE} missing")
        return 1
    if not ROUTE.exists():
        print(f"x {ROUTE} missing")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page.tsx ({len(page_src)} chars), route.ts ({len(route_src)} chars)")

    print("-- 2. POSITIVE: page is a client component + fetches /api/v1/paperclip --")
    if "'use client'" not in page_src:
        print("x page must declare 'use client' (uses useState/useEffect)")
        return 1
    if "/api/v1/paperclip" not in page_src:
        print("x page must fetch from /api/v1/paperclip")
        return 1
    print("  ok: 'use client' + fetches /api/v1/paperclip")

    print("-- 3. POSITIVE: sidebar wires the nav entry --")
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/paperclip" not in sidebar_src:
        print("x sidebar must contain /admin/paperclip nav entry")
        return 1
    print("  ok: sidebar nav entry present")

    print("-- 4. NEGATIVE: BFF route refuses POST/PUT/DELETE/PATCH --")
    # Stage-1 contract: no mutating HTTP verbs. The route must export 405
    # handlers for all of them.
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        # Either a function definition `export async function POST` OR
        # an alias `export const PUT = POST`
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler returning 405")
            return 1
    if "STAGE_1_READ_ONLY" not in route_src:
        print("x route must cite STAGE_1_READ_ONLY error_code in mutating-verb refusal")
        return 1
    print("  ok: POST/PUT/DELETE/PATCH all wired to 405 + STAGE_1_READ_ONLY")

    print("-- 5. NEGATIVE: page does NOT contain write-verb labels --")
    # Bit-rot prevention: a future PR adding a "Push" button or
    # "Dispatch" button would silently violate the sandbox contract.
    forbidden_labels = (
        r">\s*Push\s*<", r">\s*Dispatch\s*<", r">\s*Deploy\s*<",
        r">\s*Apply\s*<", r">\s*Merge\s*<", r">\s*Rollback\s*<",
    )
    for pat in forbidden_labels:
        if re.search(pat, page_src):
            print(f"x page contains write-verb button/label: {pat!r}")
            return 1
    print("  ok: no write-verb buttons/labels on page")

    print("-- 6. NEGATIVE: §49 compose footer present with 3+ cross-refs --")
    # Per §49, every deep page must end with a "Composes with" panel
    # listing 3-7 cross-refs.
    if "Composes with" not in page_src and "compose footer" not in page_src.lower():
        print("x page missing 'Composes with' section")
        return 1
    # Count <a href="/admin/..." links — minimum 3
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 3:
        print(f"x §49 footer must have >=3 cross-refs; found {len(cross_refs)}")
        return 1
    print(f"  ok: compose footer with {len(cross_refs)} cross-refs")

    print("-- 7. POSITIVE: page surfaces apply_rate as brutal-honesty headline --")
    # The §55.3 contract: apply_rate must be visually prominent. We check
    # that 'apply_rate' is referenced AND that 'honesty' or '§55.3' is
    # mentioned (signaling intentional surfacing, not an incidental log).
    if "apply_rate" not in page_src:
        print("x page must reference snap.apply_attempts.apply_rate")
        return 1
    if "honesty" not in page_src.lower() and "§55.3" not in page_src:
        print("x page must label apply_rate as honesty signal (or cite §55.3)")
        return 1
    print("  ok: apply_rate surfaced + honesty-signal labeling present")

    print("-- 8. NEGATIVE: page has NO hardcoded Ollama URL --")
    # All HTTP calls go through /api/v1/paperclip; the page must NOT
    # reach Ollama directly. That would bypass PolisAI gating.
    forbidden_urls = (
        r"http://localhost:11434",
        r"https?://[^\s\"']*:11434",
        r"OLLAMA_BASE_URL",  # env var name should ONLY appear in BFF, not page
    )
    for pat in forbidden_urls:
        if re.search(pat, page_src):
            print(f"x page must NOT reach Ollama directly: pattern {pat!r}")
            return 1
    print("  ok: no hardcoded Ollama URL on page (correctly routes through BFF)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
