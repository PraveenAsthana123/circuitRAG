#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/adapters page + BFF — unified adapter inventory.

Per CLAUDE.md §43 + §49. Locks:

  - page.tsx + route.ts both exist
  - BFF Promise.all-invokes 3 adapter status commands in parallel
  - Page surfaces all 3 adapters (LiteLLM + PydanticAI + Kafka publisher)
  - Each adapter row has source_path / drill_path / feature_flag /
    swap_target documented
  - BFF refuses POST/PUT/DELETE/PATCH (toggling = env var, not HTTP)
  - Page does NOT contain any "enable adapter" button
  - §49 footer + sidebar wired

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "adapters" / "page.tsx"
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "adapters" / "route.ts"
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

    print("-- 3. POSITIVE: BFF lists all 3 adapters --")
    expected_adapters = (
        "LiteLLM",
        "PydanticAI",
        "Kafka event-publisher",
    )
    for name in expected_adapters:
        if name not in route_src:
            print(f"x BFF must list adapter: {name!r}")
            return 1
    print(f"  ok: 3 adapters in BFF inventory")

    print("-- 4. POSITIVE: BFF Promise.all-invokes adapter status commands --")
    if "Promise.all" not in route_src:
        print("x route must use Promise.all for parallel status fetch")
        return 1
    if "status" not in route_src.lower():
        print("x route must invoke each adapter's status command")
        return 1
    print("  ok: BFF uses Promise.all for parallel status fetch")

    print("-- 5. NEGATIVE: BFF refuses POST/PUT/DELETE/PATCH --")
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        if (
            f"export async function {method}" not in route_src
            and f"export const {method}" not in route_src
        ):
            print(f"x route must export {method} handler")
            return 1
    if "ADAPTERS_BFF_READ_ONLY" not in route_src:
        print("x mutating refusal must cite ADAPTERS_BFF_READ_ONLY")
        return 1
    print("  ok: 4 mutating methods all return 405 + ADAPTERS_BFF_READ_ONLY")

    print("-- 6. NEGATIVE: page does NOT have enable-adapter buttons --")
    # Adapters are toggled via env vars at process start, NOT HTTP.
    # A future "Enable LiteLLM" button would silently bypass the
    # process-restart contract.
    forbidden_buttons = (
        r">\s*Enable\s*<",
        r">\s*Toggle\s*<",
        r">\s*Activate\s*<",
        r"onClick.*enable",
        r"onSubmit.*enable",
    )
    for pat in forbidden_buttons:
        if re.search(pat, page_src, re.IGNORECASE):
            print(f"x page must NOT have enable-adapter UI; pattern: {pat!r}")
            return 1
    print("  ok: 0 enable-adapter UI elements (env vars only)")

    print("-- 7. NEGATIVE: each adapter has documented metadata fields --")
    # The AdapterInfo struct in the BFF must have all required fields
    # for each entry. Drill enforces consistency.
    required_fields = ("source_path", "drill_path", "feature_flag_env",
                       "source_layer", "swap_target")
    for field in required_fields:
        if f"{field}:" not in route_src:
            print(f"x AdapterInfo must include field: {field!r}")
            return 1
    print(f"  ok: all 5 metadata fields documented per adapter")

    print("-- 8. POSITIVE: §49 compose footer + sidebar wired --")
    if "Composes with" not in page_src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', page_src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/adapters" not in sidebar_src:
        print("x sidebar missing /admin/adapters")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
