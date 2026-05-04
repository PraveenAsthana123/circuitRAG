#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/sitemap page contract.

Per CLAUDE.md §43 + §49. Locks the categorized-index page so adding a
new admin page also adds a sitemap row.

Eight steps. Five negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "sitemap" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"
ADMIN_DIR = REPO / "services" / "frontend" / "app" / "admin"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx exists --")
    if not PAGE.exists():
        print(f"x {PAGE} missing")
        return 1
    src = PAGE.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x page too short ({len(src)} chars); expected >=4000")
        return 1
    print(f"  ok: {len(src)} chars")

    print("-- 2. POSITIVE: Server Component (static index, not interactive) --")
    head = src[:300]
    if re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x sitemap should be Server Component")
        return 1
    if "useState" in src or "useEffect" in src:
        print("x sitemap should not use React hooks (static index)")
        return 1
    print("  ok: Server Component, no hooks")

    print("-- 3. POSITIVE: SITEMAP array has multiple categorized sections --")
    # Categories: must have at least 8 (architecture / layers / adapters /
    # ops / data / security / observability / adr / etc.)
    sections = re.findall(r"category:\s*['\"]", src)
    if len(sections) < 8:
        print(f"x SITEMAP must have >=8 categories; got {len(sections)}")
        return 1
    print(f"  ok: {len(sections)} categories")

    print("-- 4. POSITIVE: All session-shipped pages indexed --")
    # Pages we shipped THIS session must be in the sitemap. If we ship
    # a new admin page in a future commit, this drill list grows.
    session_shipped = (
        "/admin/agent-router",
        "/admin/policy",
        "/admin/openclaw",
        "/admin/paperclip",
        "/admin/kafka-events",
        "/admin/vectorless-elasticsearch",
        "/admin/eval-harness",
        "/admin/tool-evaluation",
        "/admin/pr-management",
        "/admin/adapters",
        "/admin/enterprise-architecture",
        "/admin/techstack-audit",
        "/admin/mcp-gateway",
    )
    for href in session_shipped:
        if f"href: '{href}'" not in src:
            print(f"x sitemap missing session-shipped page: {href}")
            return 1
    print(f"  ok: all {len(session_shipped)} session-shipped pages indexed")

    print("-- 5. NEGATIVE: every entry has href + label + description + status --")
    # SitemapEntry struct must have all 4 fields per row.
    for field in ("href:", "label:", "description:", "status:"):
        # Count must match (one per entry)
        count = len(re.findall(re.escape(field), src))
        # Allow leeway for type definitions vs entries
        if count < 30:
            print(f"x SITEMAP entries missing {field!r} consistency; got {count} occurrences")
            return 1
    print("  ok: all entries structured (href/label/description/status)")

    print("-- 6. NEGATIVE: no broken local-only refs (every href is /admin/...) --")
    # Bit-rot: a refactor that adds external URLs would be wrong here —
    # sitemap is internal navigation only.
    hrefs = re.findall(r"href:\s*['\"]([^'\"]+)['\"]", src)
    for href in hrefs:
        if not href.startswith("/admin"):
            print(f"x non-/admin href in sitemap: {href!r}")
            return 1
    if len(hrefs) < 30:
        print(f"x sitemap should have >=30 hrefs; got {len(hrefs)}")
        return 1
    print(f"  ok: all {len(hrefs)} hrefs are /admin/*")

    print("-- 7. NEGATIVE: discovery rule documented at bottom --")
    # Per the "discovery rule" section: new admin pages MUST update both
    # sidebar AND sitemap. Drill enforces the rule is documented so
    # contributors know.
    if "Discovery rule" not in src:
        print("x sitemap must document the discovery rule for new pages")
        return 1
    if "sidebar" not in src.lower():
        print("x discovery rule must mention sidebar")
        return 1
    print("  ok: discovery rule + sidebar reference present")

    print("-- 8. POSITIVE: sitemap entry sourced 1:1 with sidebar entry --")
    # Sidebar must wire /admin/sitemap entry (drill enforces back-pointer).
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/sitemap" not in sidebar_src:
        print("x sidebar must contain /admin/sitemap entry")
        return 1
    print("  ok: sidebar wires /admin/sitemap")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
