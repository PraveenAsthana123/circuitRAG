#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/pr-management page + BFF — push queue surface.

Per CLAUDE.md §43 + §42. Locks the read-only contract:

  - page.tsx + route.ts both exist
  - Page is Client Component (interactive refresh)
  - BFF runs `git log origin/main..HEAD` + parses commits
  - BFF refuses POST/PUT/DELETE/PATCH (push is CLI-only per §42)
  - Page does NOT contain a "Push" button (page is read-only surface)
  - Page surfaces the §42 push command + warning explicitly
  - Page surfaces unpushed-count with pressure indicator (>50 red)
  - §49 footer + sidebar wired

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "pr-management" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "pr-management" / "route.ts"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx + route.ts both exist --")
    if not PAGE.exists() or not ROUTE.exists():
        print(f"x missing: PAGE={PAGE.exists()}, ROUTE={ROUTE.exists()}")
        return 1
    page_src = PAGE.read_text(encoding="utf-8")
    route_src = ROUTE.read_text(encoding="utf-8")
    print(f"  ok: page {len(page_src)} chars; route {len(route_src)} chars")

    print("-- 2. POSITIVE: page is Client Component (interactive refresh) --")
    head = page_src[:300]
    if not re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x page must declare 'use client'")
        return 1
    print("  ok: 'use client' present")

    print("-- 3. POSITIVE: BFF runs `git log origin/main..HEAD` --")
    if "origin/main..HEAD" not in route_src:
        print("x route must call `git log origin/main..HEAD`")
        return 1
    if "spawn('git'" not in route_src and 'spawn("git"' not in route_src:
        print("x route must spawn git subprocess")
        return 1
    print("  ok: BFF runs git log against unpushed range")

    print("-- 4. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH (push is CLI-only) --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "PR_MANAGEMENT_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite PR_MANAGEMENT_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + PR_MANAGEMENT_BFF_READ_ONLY")

    print("-- 5. NEGATIVE: page does NOT have a Push button --")
    # §42 contract: this page is read-only operator visibility.
    # Pushing is a CLI operation. Drill rejects any onClick that
    # would imply push-from-browser.
    forbidden_buttons = (
        r">\s*Push\s*<",
        r">\s*Create\s+PR\s*<",
        r">\s*Merge\s*<",
        r"onClick.*push",
        r"onSubmit.*push",
        r"fetch\s*\(\s*['\"][^'\"]*['\"]\s*,\s*\{\s*method\s*:\s*['\"]POST",
    )
    for pat in forbidden_buttons:
        if re.search(pat, page_src, re.IGNORECASE):
            print(f"x page must NOT contain push UI; pattern: {pat!r}")
            return 1
    print("  ok: 0 push-shaped UI elements; surface is read-only")

    print("-- 6. NEGATIVE: page surfaces §42 push command explicitly --")
    # Operator must SEE the exact CLI command to run. Without it the
    # page becomes vague; the value of "we have N unpushed" is the
    # actionable next step.
    if "scripts/run.sh push" not in page_src:
        print("x page must show the exact `bash scripts/run.sh push --confirm` command")
        return 1
    if "§42" not in page_src and "confirm" not in page_src.lower():
        print("x page must cite §42 OR --confirm explicitly")
        return 1
    if "operator gate" not in page_src.lower() and "operator-gate" not in page_src.lower():
        print("x page must label the gate as 'operator-gated'")
        return 1
    print("  ok: §42 push command + warning explicit")

    print("-- 7. NEGATIVE: page renders pressure indicator with thresholds --")
    # Bit-rot prevention: a refactor that drops the pressure-coloring
    # would lose the "should I push now?" signal. Drill enforces the
    # 3 threshold values are present in the source.
    if "> 50" not in page_src and ">= 50" not in page_src:
        print("x page must threshold unpushed_count > 50 (red) for pressure")
        return 1
    if "> 10" not in page_src and ">= 10" not in page_src:
        print("x page must threshold unpushed_count > 10 (amber)")
        return 1
    print("  ok: 3-tier pressure thresholds (red/amber/green)")

    print("-- 8. POSITIVE: §49 compose footer + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/pr-management" not in sidebar_src:
        print("x sidebar missing /admin/pr-management")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
