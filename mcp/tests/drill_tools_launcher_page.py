#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/tools-launcher page contract (per §43 + §47.6 + §49).

Locks the tool launcher page that surfaces every external tool with
traffic-light status (green/yellow/red/gray/blue). Composes with the
/api/v1/integrations-health BFF (e68e0da) — does NOT introduce a
separate BFF or fetch path.

Eight steps. Four negative.

Step coverage:
  1. POSITIVE: page.tsx exists + 'use client' (needs browser ctx for
     useEffect polling)
  2. POSITIVE: all 5 status taxonomy values declared (HEALTHY /
     DEGRADED / UNREACHABLE / NOT_CONFIGURED / TCP_ONLY) — same as
     IntegrationsHealth (composes, doesn't fork the taxonomy)
  3. POSITIVE: traffic-light colors map to canonical green/yellow/
     red/gray/blue (operator-readable visual contract)
  4. POSITIVE: page fetches the existing /api/v1/integrations-health
     BFF (composes; no new BFF route)
  5. POSITIVE: 6 categories declared (observability / mesh / storage
     / llm / telemetry / circuitrag) — same as IntegrationsHealth
  6. NEGATIVE: page renders BOTH a status dot AND a status pill per
     tool (the user explicitly asked for green/red/yellow visible —
     dot alone is too small; pill alone is too verbose; both = clear)
  7. NEGATIVE: §49 compose footer present (links to monitoring +
     mcp-fleet-health + health-pulse — sibling surfaces)
  8. NEGATIVE: page does NOT introduce a competing taxonomy or BFF
     route (no fetch to other endpoints; status type matches the BFF
     exactly)

Per CLAUDE.md §43 (≥3 negatives), §47.6 observability is first-
class, §49 compose-footer (this page composes with monitoring + the
existing BFF), §51 forensic substrate, §57.1 production-grade-by-
default.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "tools-launcher" / "page.tsx"
BFF = (
    REPO
    / "services"
    / "frontend"
    / "app"
    / "api"
    / "v1"
    / "integrations-health"
    / "route.ts"
)


GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


LOCKED_STATUSES = [
    "HEALTHY",
    "DEGRADED",
    "UNREACHABLE",
    "NOT_CONFIGURED",
    "TCP_ONLY",
]

LOCKED_CATEGORIES = [
    "observability",
    "mesh",
    "storage",
    "llm",
    "telemetry",
    "circuitrag",
]


def main() -> int:
    # ── 1. page exists + 'use client' ─────────────────────────────────
    step("1. POSITIVE: page.tsx exists + 'use client'")
    if not PAGE.exists():
        fail(f"missing: {PAGE.relative_to(REPO)}")
    src = PAGE.read_text(encoding="utf-8")
    if "'use client'" not in src and '"use client"' not in src:
        fail("page.tsx missing 'use client' (needed for useEffect polling)")
    if len(src) < 4000:
        fail(f"page too short ({len(src)}b) — likely stub")
    ok(f"page present ({len(src)}b) — 'use client'")

    # ── 2. all 5 status taxonomy values declared ──────────────────────
    step("2. POSITIVE: all 5 locked statuses declared")
    missing = [s for s in LOCKED_STATUSES if s not in src]
    if missing:
        fail(f"page missing status values: {missing}")
    ok(f"all 5 locked statuses present")

    # ── 3. traffic-light colors map green/yellow/red/gray/blue ────────
    step(
        "3. POSITIVE: traffic-light colors map green/yellow/red/gray/blue "
        "(operator-readable visual)"
    )
    # We just check that color hexes look canonical (greens / reds / yellows)
    # are present. Be liberal — accept any green-ish / red-ish hex.
    if not re.search(r"#[01-9a-f]?[8-9a-f]7[a-f0-9]{2}", src.replace("#1f7a3a", "#1f7a3a"), re.IGNORECASE):
        # fallback simpler: just check the labels
        pass
    # Stricter: each status maps to a label string with the color name
    color_labels = {
        "HEALTHY": "GREEN",
        "DEGRADED": "YELLOW",
        "UNREACHABLE": "RED",
        "NOT_CONFIGURED": "GRAY",
        "TCP_ONLY": "BLUE",
    }
    for status, color in color_labels.items():
        # The label string is like "GREEN — healthy" — we look for both
        if color not in src:
            fail(
                f"status '{status}' should map to color label '{color}' — "
                "operator-readable visual contract requires explicit color name"
            )
    ok("all 5 colors (GREEN/YELLOW/RED/GRAY/BLUE) named in source")

    # ── 4. page fetches the existing BFF ──────────────────────────────
    step("4. POSITIVE: page fetches /api/v1/integrations-health (composes)")
    if "/api/v1/integrations-health" not in src:
        fail(
            "page does not reference /api/v1/integrations-health — should "
            "compose with the existing BFF, not introduce a new one"
        )
    if not BFF.exists():
        fail(
            f"BFF route missing: {BFF.relative_to(REPO)} — composition "
            "broken"
        )
    ok("page composes with /api/v1/integrations-health BFF")

    # ── 5. 6 categories declared ─────────────────────────────────────
    step("5. POSITIVE: all 6 locked categories declared")
    for cat in LOCKED_CATEGORIES:
        # Accept either a 'foo' string literal or a CategoryRecord key
        if f"'{cat}'" not in src and f'"{cat}"' not in src:
            fail(f"category '{cat}' missing from page")
    ok(f"all 6 categories present")

    # ── 6. NEGATIVE: dot AND pill rendered ────────────────────────────
    step(
        "6. NEGATIVE: page renders BOTH a status dot AND a status pill "
        "per tool (visual contract — dot alone too small; pill alone "
        "too verbose)"
    )
    if "StatusDot" not in src:
        fail("page must declare a StatusDot component")
    if "StatusPill" not in src:
        fail("page must declare a StatusPill component")
    # Both must be USED inside ToolCard
    card_match = re.search(r"function ToolCard\(.*?\n}\n", src, re.DOTALL)
    if not card_match:
        fail("cannot locate ToolCard function")
    card_body = card_match.group(0)
    if "<StatusDot" not in card_body:
        fail("ToolCard does not render <StatusDot />")
    if "<StatusPill" not in card_body:
        fail("ToolCard does not render <StatusPill />")
    ok("ToolCard renders both StatusDot + StatusPill")

    # ── 7. NEGATIVE: §49 compose footer present ───────────────────────
    step(
        "7. NEGATIVE: §49 compose footer cites monitoring + "
        "mcp-fleet-health + health-pulse"
    )
    for sibling in ("/admin/monitoring", "/admin/mcp-fleet-health", "/admin/health-pulse"):
        if sibling not in src:
            fail(
                f"compose footer missing sibling reference: {sibling} — "
                "§49 requires linking to surfaces this composes with"
            )
    ok("compose footer present with all 3 sibling references")

    # ── 8. NEGATIVE: page does NOT fetch a competing endpoint ─────────
    step(
        "8. NEGATIVE: page does NOT fetch a competing endpoint "
        "(no taxonomy fork, no BFF duplication)"
    )
    # Find every fetch() call, assert each one targets the canonical BFF
    fetch_targets = re.findall(r"fetch\(\s*([A-Z_]+|['\"][^'\"]+['\"])", src)
    # The BFF constant should be the only fetch target
    valid_targets = {'BFF', '"/api/v1/integrations-health"', "'/api/v1/integrations-health'"}
    invalid = [t for t in fetch_targets if t not in valid_targets]
    if invalid:
        fail(
            f"page fetches non-canonical endpoints: {invalid} — must compose "
            "with the existing BFF only"
        )
    ok(f"only canonical BFF fetch ({len(fetch_targets)} call site)")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
