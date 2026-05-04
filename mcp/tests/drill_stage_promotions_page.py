#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/stage-promotions page contract.

Per CLAUDE.md §43 + §44 + §49. Locks the Stage-1/2/3 tracker page so
adding a new component-with-stages also adds a row.

Eight steps. Five negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "stage-promotions" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx exists --")
    if not PAGE.exists():
        print(f"x {PAGE} missing")
        return 1
    src = PAGE.read_text(encoding="utf-8")
    if len(src) < 6000:
        print(f"x page too short ({len(src)} chars); expected >=6000")
        return 1
    print(f"  ok: {len(src)} chars")

    print("-- 2. POSITIVE: Server Component (static documentation) --")
    head = src[:300]
    if re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x stage-promotions should be Server Component")
        return 1
    if "useState" in src or "useEffect" in src:
        print("x page should not use React hooks (static documentation)")
        return 1
    print("  ok: Server Component, no hooks")

    print("-- 3. POSITIVE: 4 stage-status types defined --")
    expected_statuses = ("'shipped'", "'pending'", "'na'", "'rejected'")
    for status in expected_statuses:
        if status not in src:
            print(f"x stage status not used: {status}")
            return 1
    print("  ok: 4 stage statuses (shipped/pending/na/rejected)")

    print("-- 4. POSITIVE: all 4 adopted adapters tracked --")
    expected_adapters = ("LiteLLM adapter", "PydanticAI adapter",
                         "Kafka event-publisher", "MCP Gateway")
    for adapter in expected_adapters:
        if adapter not in src:
            print(f"x adapter not tracked: {adapter!r}")
            return 1
    print(f"  ok: 4 adapters tracked")

    print("-- 5. POSITIVE: all 3 tool-eval rejected items present --")
    expected_rejected = ("CrewAI", "Agno", "PraisonAI")
    for item in expected_rejected:
        if item not in src:
            print(f"x rejected item missing: {item!r}")
            return 1
    # Each rejected must have stage1.status='rejected' (drill enforces
    # tool-evaluation verdicts stay in sync)
    for item in expected_rejected:
        idx = src.find(f"name: '{item}")
        if idx == -1:
            continue
        section = src[idx:idx + 1000]
        if "'rejected'" not in section:
            print(f"x {item!r} should have stage1.status='rejected'")
            return 1
    print(f"  ok: 3 rejected items present + tagged 'rejected'")

    print("-- 6. NEGATIVE: every component has 3 stages defined --")
    # Each Component object must have stage1 + stage2 + stage3 fields.
    # Drill counts occurrences across the array.
    stage1_count = len(re.findall(r"stage1:\s*\{", src))
    stage2_count = len(re.findall(r"stage2:\s*\{", src))
    stage3_count = len(re.findall(r"stage3:\s*\{", src))
    if stage1_count != stage2_count or stage2_count != stage3_count:
        print(f"x stage counts mismatch: 1={stage1_count}, 2={stage2_count}, 3={stage3_count}")
        return 1
    if stage1_count < 8:
        print(f"x expected >=8 components; got {stage1_count}")
        return 1
    print(f"  ok: {stage1_count} components × 3 stages each")

    print("-- 7. NEGATIVE: fully-promoted components retain 3 ✅ stages --")
    # Drill enforces session-shipped fully-promoted components retain
    # all 3 stages as 'shipped'. A regression that moved one to
    # 'pending' would silently undo the achievement.
    fully_promoted = (
        "LiteLLM adapter",
        "MCP Gateway",
        "Paperclip Sandbox",  # added 2026-05-04: Stage-3 dispatcher
    )
    for component in fully_promoted:
        idx = src.find(f"name: '{component}'")
        if idx == -1:
            print(f"x component {component!r} not found")
            return 1
        section = src[idx:idx + 2000]
        # Count 'shipped' occurrences in this component's section
        shipped_count = section.count("status: 'shipped'")
        if shipped_count < 3:
            print(f"x {component!r} should have 3 'shipped' stages; got {shipped_count}")
            return 1
    print(f"  ok: {len(fully_promoted)} components fully-promoted (3 'shipped' stages each)")

    print("-- 8. POSITIVE: §49 footer + sidebar wired + composes-with refs --")
    if "Composes with" not in src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/stage-promotions" not in sidebar_src:
        print("x sidebar missing /admin/stage-promotions")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
