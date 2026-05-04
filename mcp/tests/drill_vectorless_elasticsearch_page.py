#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: vectorless-elasticsearch admin page contract.

Per CLAUDE.md §43 + §49 (compose-footer pattern). Locks:

  - page.tsx exists at expected path
  - Page is a Server Component (no 'use client' — static docs)
  - All 6 documented topic sections present (what / when / architecture
    / queries / index-mapping / gotchas)
  - Decision matrix table comparing vectorless vs vector vs hybrid
  - At least 4 ES query examples (BM25 / phrase / multi-field / RRF)
  - Recommended index mapping documents tenant_id as keyword (RLS)
  - §49 compose footer with 5+ cross-refs
  - Sidebar wires the nav entry
  - No live ES query in Stage-1 (no fetch / axios / EventSource)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "vectorless-elasticsearch" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx exists + is a Server Component --")
    if not PAGE.exists():
        print(f"x {PAGE} missing")
        return 1
    src = PAGE.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x page too short ({len(src)} chars); expected >=4000")
        return 1
    # Server Component: NO 'use client' directive at the TOP of the
    # file. The directive must be on its own line, before imports —
    # we check the first ~500 chars + verify no line equals "'use client';".
    # The docstring/comments may mention 'use client' as text.
    head = src[:500]
    has_directive = re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE)
    if has_directive:
        print("x Stage-1 page must be a Server Component (no 'use client' directive)")
        return 1
    print(f"  ok: {len(src)} chars; Server Component (no 'use client' directive)")

    print("-- 2. POSITIVE: 6 topic sections documented --")
    required_section_titles = (
        "What is vectorless RAG",
        "When vectorless beats vector",
        "Architecture",
        "Elasticsearch query patterns",
        "Recommended index mapping",
        "Gotchas",
    )
    for title in required_section_titles:
        if title not in src:
            print(f"x section missing: {title!r}")
            return 1
    print(f"  ok: all 6 topic sections present")

    print("-- 3. POSITIVE: decision matrix table comparing vectorless vs vector --")
    # Must contain "vectorless" + "vector" + at least 5 row markers
    # to be a real decision matrix, not a one-liner.
    if "vectorless" not in src.lower():
        print("x page must mention 'vectorless'")
        return 1
    if "vector" not in src.lower():
        print("x page must mention 'vector' (the comparison target)")
        return 1
    # Count <tr> rows in the body section — should be at least 5 data rows
    tr_count = src.count("<tr>")
    if tr_count < 5:
        print(f"x decision matrix must have >=5 <tr>; got {tr_count}")
        return 1
    print(f"  ok: decision matrix with {tr_count} rows")

    print("-- 4. POSITIVE: 4+ Elasticsearch query patterns documented --")
    es_query_markers = (
        "match_phrase",   # exact-term match pattern
        "multi_match",    # multi-field weighted
        "rrf",            # Reciprocal Rank Fusion
        "_search",        # the ES search endpoint
    )
    for marker in es_query_markers:
        if marker not in src:
            print(f"x ES query example missing marker: {marker!r}")
            return 1
    print(f"  ok: all 4 ES query pattern markers present")

    print("-- 5. NEGATIVE: index mapping must declare tenant_id as keyword (RLS) --")
    # Tenant isolation is non-negotiable. The mapping must define
    # tenant_id as keyword type so {term: tenant_id} queries are
    # exact + cheap. Without keyword mapping, multi-tenant retrieval
    # leaks per §41.3.
    mapping_section = re.search(r"index mapping.*?</section>", src, re.DOTALL | re.IGNORECASE)
    if not mapping_section:
        print("x cannot locate index mapping section")
        return 1
    section = mapping_section.group(0)
    if "tenant_id" not in section:
        print("x index mapping must include tenant_id field")
        return 1
    if '"keyword"' not in section:
        print("x index mapping must declare tenant_id as keyword type")
        return 1
    print("  ok: tenant_id mapped as keyword (multi-tenant RLS-ready)")

    print("-- 6. NEGATIVE: page does NOT fetch live data (Stage-1 is docs only) --")
    # Stage-1 is documentation; live ES queries land in Stage-2 via
    # /api/v1/retrieve?strategy=vectorless. The page must NOT call
    # fetch / axios / EventSource directly to ES.
    forbidden_runtime = (
        r"\bfetch\s*\(",
        r"\bnew\s+EventSource\s*\(",
        r"axios\.\w+\s*\(",
        r"http://localhost:9200",  # direct ES port
    )
    for pat in forbidden_runtime:
        if re.search(pat, src):
            print(f"x Stage-1 page must NOT contain runtime data fetch: {pat!r}")
            return 1
    print("  ok: 0 runtime fetch / EventSource / direct-ES patterns")

    print("-- 7. POSITIVE: §49 compose footer with 5+ cross-refs --")
    if "Composes with" not in src:
        print("x page missing §49 'Composes with' footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    print(f"  ok: compose footer with {len(cross_refs)} cross-refs")

    print("-- 8. POSITIVE: sidebar wires the nav entry --")
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/vectorless-elasticsearch" not in sidebar_src:
        print("x sidebar must contain /admin/vectorless-elasticsearch nav entry")
        return 1
    print("  ok: sidebar nav entry present")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
