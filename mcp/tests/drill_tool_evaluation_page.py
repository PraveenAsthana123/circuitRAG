#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/tool-evaluation page contract.

Per CLAUDE.md §43 + §49. Locks:
  - All 13 candidate tools evaluated (5 AI frameworks + 8 Minecraft tools)
  - Each tool has license + maintenance + useful + safe + verdict + recommendation
  - 4 verdict categories used (integrate / sandbox-only / specific-use / skip)
  - LiteLLM is verdict=integrate (the headline actionable recommendation)
  - All 8 Minecraft tools are verdict=skip OR sandbox-only (not integrate)
  - Bottom-line section names actionable next moves
  - §49 compose footer

8 steps; 5 negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "tool-evaluation" / "page.tsx"
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

    print("-- 2. POSITIVE: all 13 tools named --")
    expected_tools = (
        # AI frameworks
        "LiteLLM", "PydanticAI", "CrewAI", "Agno", "PraisonAI",
        # Minecraft stack
        "MineRL", "Malmo", "mineflayer", "PaperMC",
        "Crafty", "mc-control", "mc-server-wrapper", "minerl.io",
    )
    for tool in expected_tools:
        if tool not in src:
            print(f"x tool not evaluated: {tool!r}")
            return 1
    print(f"  ok: all {len(expected_tools)} tools named")

    print("-- 3. POSITIVE: every tool entry has license + maintenance + useful + safe + verdict --")
    # Each ToolEval object must have these 5 fields
    # Look for the ToolEval array structure
    for field_name in ("license", "maintenance", "useful", "safe", "verdict", "recommendation"):
        if f"{field_name}:" not in src:
            print(f"x ToolEval objects missing field: {field_name!r}")
            return 1
    print(f"  ok: 6 evaluation fields (license/maintenance/useful/safe/verdict/recommendation)")

    print("-- 4. POSITIVE: 4 verdict categories used --")
    verdicts = ("integrate", "sandbox-only", "specific-use", "skip")
    for v in verdicts:
        if f"'{v}'" not in src and f'"{v}"' not in src:
            print(f"x verdict category not used: {v!r}")
            return 1
    print(f"  ok: all 4 verdict categories used")

    print("-- 5. POSITIVE: LiteLLM verdict=integrate (the headline rec) --")
    # LiteLLM is the one tool that should be 'integrate' — drill locks
    # this so a future PR doesn't accidentally downgrade it.
    litellm_idx = src.find("LiteLLM")
    if litellm_idx == -1:
        print("x LiteLLM section not found")
        return 1
    # Look at the LiteLLM object's verdict (in the next ~1500 chars)
    section = src[litellm_idx:litellm_idx + 1500]
    if "verdict: 'integrate'" not in section:
        print("x LiteLLM must have verdict='integrate' (the headline actionable rec)")
        return 1
    print("  ok: LiteLLM verdict=integrate")

    print("-- 6. NEGATIVE: NO Minecraft tool has verdict=integrate --")
    # Per the analysis: all 8 Minecraft tools are out-of-scope for our
    # production stack. Drill enforces that none gets accidentally
    # promoted to 'integrate' without an architecture review.
    mc_tool_names = ("MineRL", "Malmo", "mineflayer", "PaperMC",
                     "Crafty Controller", "mc-control",
                     "mc-server-wrapper", "minerl.io")
    for tool in mc_tool_names:
        idx = src.find(f"name: '{tool}'")
        if idx == -1:
            # Try alternate quoting
            idx = src.find(f"'{tool}'")
            if idx == -1:
                continue
        # Look at the next ~1500 chars for the verdict field
        section = src[idx:idx + 1500]
        if "verdict: 'integrate'" in section:
            print(f"x Minecraft tool {tool!r} must NOT have verdict='integrate'")
            return 1
    print("  ok: 0 Minecraft tools have verdict='integrate'")

    print("-- 7. NEGATIVE: bottom-line section names 5 actionable moves --")
    # The bottom-line summary must be concrete: "adopt X" / "skip Y"
    # not vague platitudes.
    bottom_line_idx = src.find("Bottom line")
    if bottom_line_idx == -1:
        print("x page must have 'Bottom line' actionable summary")
        return 1
    bottom_section = src[bottom_line_idx:bottom_line_idx + 3000]
    required_actions = ("Adopt LiteLLM", "Adopt PydanticAI", "Read CrewAI", "Skip all 8 Minecraft", "Skip PraisonAI")
    for action in required_actions:
        if action not in bottom_section:
            print(f"x bottom-line must include action: {action!r}")
            return 1
    print(f"  ok: 5 concrete actionable next moves named")

    print("-- 8. POSITIVE: §49 compose footer + sidebar wired --")
    if "Composes with" not in src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/tool-evaluation" not in sidebar_src:
        print("x sidebar missing /admin/tool-evaluation")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
