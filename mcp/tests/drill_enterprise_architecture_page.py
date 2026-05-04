#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/enterprise-architecture page contract.

Per CLAUDE.md §43 + §49. Locks the canonical 20+17+12 enterprise
architecture map.

Eight steps. Five negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "enterprise-architecture" / "page.tsx"
SIDEBAR = REPO / "services" / "frontend" / "components" / "Sidebar.tsx"


def main() -> int:
    print("-- 1. POSITIVE: page.tsx exists --")
    if not PAGE.exists():
        print(f"x {PAGE} missing")
        return 1
    src = PAGE.read_text(encoding="utf-8")
    if len(src) < 8000:
        print(f"x page too short ({len(src)} chars); expected >=8000")
        return 1
    print(f"  ok: {len(src)} chars")

    print("-- 2. POSITIVE: 20-tool sequence has all 20 entries --")
    # SEQUENCE array must have 20 entries (seq: 1..20)
    seq_count = len(re.findall(r"seq:\s*\d+", src))
    if seq_count < 20:
        print(f"x SEQUENCE must have 20 entries; got {seq_count}")
        return 1
    # Verify entries 1, 10, 20 exist (sentinel checks)
    for n in (1, 10, 20):
        if f"seq: {n}" not in src:
            print(f"x SEQUENCE entry seq={n} missing")
            return 1
    print(f"  ok: {seq_count} sequence entries (tools 1-20)")

    print("-- 3. POSITIVE: 17 missing components documented --")
    # MISSING array must include the 17 areas the user named
    expected_missing = (
        "MCP registry", "MCP security gateway", "Agent registry",
        "Prompt registry", "Model gateway", "Memory governance",
        "Dataset/versioning", "Feature flags", "Queue/DLQ",
        "Rate limit", "Kill switch", "Audit vault",
        "Threat modeling", "Supply-chain security", "Policy testing",
        "Chaos testing", "Load testing",
    )
    for area in expected_missing:
        if area not in src:
            print(f"x missing component not documented: {area!r}")
            return 1
    print(f"  ok: all {len(expected_missing)} missing components documented")

    print("-- 4. POSITIVE: 12 MCP servers documented with risk levels --")
    expected_mcp = (
        "Filesystem MCP", "GitHub/Git MCP", "Postgres MCP",
        "Slack/Teams MCP", "Google Drive/SharePoint MCP", "Browser MCP",
        "Kubernetes MCP", "Databricks MCP", "Jira/Linear MCP",
        "CI/CD MCP", "Vault MCP", "Observability MCP",
    )
    for mcp in expected_mcp:
        if mcp not in src:
            print(f"x MCP server not documented: {mcp!r}")
            return 1
    # 3 risk levels must be used (medium / high / critical)
    for risk in ("medium", "high", "critical"):
        if f"'{risk}'" not in src and f'"{risk}"' not in src:
            print(f"x risk level not used: {risk!r}")
            return 1
    print(f"  ok: all {len(expected_mcp)} MCP servers + 3 risk levels")

    print("-- 5. NEGATIVE: page does NOT use any 'enable adapter' or live-call UI --")
    # Server Component (static documentation)
    head = src[:300]
    if re.search(r"^\s*['\"]use client['\"]\s*;?\s*$", head, re.MULTILINE):
        print("x enterprise-architecture page should be Server Component (static)")
        return 1
    # No fetch / runtime queries (this is documentation)
    forbidden = (
        r"\bfetch\s*\(",
        r"useState",
        r"useEffect",
        r"\bspawn\s*\(",
    )
    for pat in forbidden:
        if re.search(pat, src):
            print(f"x page must NOT have runtime/interactive code: {pat!r}")
            return 1
    print("  ok: Server Component, no runtime queries (pure docs)")

    print("-- 6. NEGATIVE: page documents the 'do not allow direct MCP access' rule --")
    # The brutal rule from the spec: every MCP must be behind gateway.
    # Drill enforces the rule is surfaced explicitly.
    if "do not allow direct MCP access" not in src:
        print("x page must document 'do not allow direct MCP access' rule")
        return 1
    if "MCP Gateway" not in src:
        print("x page must mention MCP Gateway")
        return 1
    if "OPA + sandbox + audit" not in src and "OPA + sandbox" not in src:
        print("x page must mention the gateway + OPA + sandbox + audit composition")
        return 1
    print("  ok: brutal MCP rule surfaced explicitly")

    print("-- 7. NEGATIVE: brutal-recommendation section names a single highest-leverage move --")
    # Section must be concrete: name what to ship next, not vague.
    if "biggest gap" not in src.lower() and "highest-leverage" not in src.lower():
        print("x page must have a brutal-recommendation section with single highest-leverage move")
        return 1
    if "MCP security gateway" not in src:
        print("x recommendation must name MCP security gateway as the next iteration target")
        return 1
    if "scripts/mcp_gateway.py" not in src:
        print("x recommendation must name the concrete file path to ship")
        return 1
    print("  ok: brutal recommendation surfaces 1 concrete next move")

    print("-- 8. POSITIVE: §49 compose footer + sidebar wired --")
    if "Composes with" not in src:
        print("x missing §49 footer")
        return 1
    cross_refs = re.findall(r'href="/admin/[^"]+', src)
    if len(cross_refs) < 5:
        print(f"x §49 footer must have >=5 cross-refs; got {len(cross_refs)}")
        return 1
    sidebar_src = SIDEBAR.read_text(encoding="utf-8")
    if "/admin/enterprise-architecture" not in sidebar_src:
        print("x sidebar missing /admin/enterprise-architecture")
        return 1
    print(f"  ok: footer with {len(cross_refs)} cross-refs + sidebar wired")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
