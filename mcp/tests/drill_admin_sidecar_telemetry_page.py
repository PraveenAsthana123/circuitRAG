#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: /admin/sidecar/telemetry/page.tsx — structural contract (Phase 5S).

Phase 5S surfaces the daily-snapshot data from Phase 5N on a live
sub-page of /admin/sidecar/. The page reads .loop/council_stats_daily.jsonl
at request time (server component) and renders a daily-table view.

This drill verifies STRUCTURE only — that the page exists, has the
required pieces, follows the project's frontend conventions, and
won't silently regress on a stylistic refactor. We don't render the
page; that's a job for Playwright / browser-qa-agent in a future
phase.

Eight steps. Six negative assertions.

  1. POSITIVE: file exists at the canonical Next.js app-router path.
  2. NEGATIVE: page is a SERVER component (no `'use client'`
     directive). Reading filesystem at request time only works in
     server components; client-side would attempt fs in the browser.
  3. NEGATIVE: file imports `fs` (or `fs/promises`) for the
     snapshot read. Without this, the page is doc-only — the
     whole 5S point is live data.
  4. NEGATIVE: file references `.loop/council_stats_daily.jsonl`
     literally. Hard-coding the snapshot path is the contract;
     wandering off to a custom path would break the cron pipeline.
  5. NEGATIVE: dedup-by-date logic is present (snapshot_taken_at
     comparison). Without dedup, two cron fires on the same day
     show the same date twice.
  6. NEGATIVE: missing-file handling — page must reference an
     'no snapshots' / 'install' / 'no data' fallback string so the
     page renders cleanly in pre-bootstrap state.
  7. NEGATIVE: cross-references back to /admin/sidecar/deep AND
     /admin/sidecar (per ~/.claude/CLAUDE.md §49 compose-footer
     pattern — pages name 3-7 neighbours). Without these, the
     dependency graph misses an edge.
  8. NEGATIVE: NO Tailwind classes; NO `style={{...}}` for layout
     (per ~/.claude/CLAUDE.md §14 vanilla-CSS rule). Inline style
     allowed only for the muted-zero-row color rule.

Run: python3 mcp/tests/drill_admin_sidecar_telemetry_page.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE_PATH = (
    REPO / "services" / "frontend" / "app" / "admin"
    / "sidecar" / "telemetry" / "page.tsx"
)


def main() -> int:
    # ── Step 1: file exists ──
    if not PAGE_PATH.exists():
        print(f"✗ step 1: {PAGE_PATH} missing")
        return 1
    body = PAGE_PATH.read_text()
    if len(body) < 500:
        print(f"✗ step 1: page is suspiciously short ({len(body)} chars); "
              "expected ≥500 for a substantive sub-page")
        return 1
    print(f"✓ step 1: page exists ({len(body)} chars, "
          f"{len(body.splitlines())} lines)")

    # ── Step 2: NEGATIVE — server component, no 'use client' ──
    if re.search(r"^['\"]use client['\"]", body, re.MULTILINE):
        print("✗ step 2: page declares 'use client'; must be a server "
              "component to read fs at request time")
        return 1
    print("✓ step 2: server component (no 'use client' directive)")

    # ── Step 3: NEGATIVE — fs import for live read ──
    fs_import = re.search(
        r"import\s+(?:[\w*\s{},]+)\s+from\s+['\"](?:node:)?fs(?:/promises)?['\"]",
        body,
    )
    if not fs_import:
        print("✗ step 3: no fs / fs/promises import; page can't read "
              "the snapshot file at request time. Without this, 5S "
              "is doc-only — the whole point is live data.")
        return 1
    print(f"✓ step 3: imports fs for runtime read")

    # ── Step 4: NEGATIVE — references the canonical snapshot path ──
    if "council_stats_daily.jsonl" not in body:
        print("✗ step 4: page doesn't reference council_stats_daily.jsonl. "
              "Hard-coding the snapshot path is the cron-pipeline contract.")
        return 1
    if ".loop" not in body and ".loop/" not in body:
        print("✗ step 4: page references the file but not the .loop/ "
              "directory; the snapshot file lives there per Phase 5N.")
        return 1
    print("✓ step 4: references .loop/council_stats_daily.jsonl")

    # ── Step 5: NEGATIVE — dedup-by-date logic present ──
    # The 5N read_snapshots contract: same date keeps the latest
    # snapshot_taken_at. Page must implement this in TS.
    if "snapshot_taken_at" not in body:
        print("✗ step 5: 'snapshot_taken_at' not referenced; "
              "dedup logic missing")
        return 1
    # Look for either Map-based dedup OR sort+filter pattern
    dedup_signal = (
        "Map<" in body or "new Map" in body
        or re.search(r"snapshot_taken_at\s*[><=]", body)
    )
    if not dedup_signal:
        print("✗ step 5: snapshot_taken_at referenced but no dedup "
              "comparison found. Two cron fires on the same date "
              "would show duplicates.")
        return 1
    print("✓ step 5: dedup-by-date logic present (snapshot_taken_at compared)")

    # ── Step 6: NEGATIVE — missing-file fallback string ──
    fallback_keywords = ["no snapshots", "no data", "install_snapshot_cron",
                         "no snapshot", "not yet"]
    if not any(kw.lower() in body.lower() for kw in fallback_keywords):
        print(f"✗ step 6: no missing-file fallback found. Tried: "
              f"{fallback_keywords}. Pre-bootstrap state must render cleanly.")
        return 1
    print("✓ step 6: missing-file fallback present (graceful pre-bootstrap)")

    # ── Step 7: NEGATIVE — compose footer cross-refs ──
    # Pages should name 3-7 neighbours per ~/.claude/CLAUDE.md §49.
    # For the telemetry sub-page, deep-dive + live dashboard are
    # the obvious composing neighbours.
    if "/admin/sidecar/deep" not in body:
        print("✗ step 7: page doesn't link to /admin/sidecar/deep; "
              "operators on this page should be able to jump to architecture")
        return 1
    if "/admin/sidecar" not in body.replace("/admin/sidecar/deep", ""):
        # Strip the deep ref before checking for plain /admin/sidecar
        print("✗ step 7: page doesn't link to /admin/sidecar (live dashboard)")
        return 1
    print("✓ step 7: compose footer links back to deep-dive + live dashboard")

    # ── Step 8: NEGATIVE — vanilla CSS, no Tailwind/styled-components ──
    # Per ~/.claude/CLAUDE.md §14: no Tailwind classes, no inline
    # style for layout. Inline style allowed only for narrow rules
    # (e.g. muted color on zero-row text).
    tailwind_signal = re.search(
        r'className=["\'][^"\']*\b(?:bg|text|p|m|w|h|flex|grid)-(?:\d+|\[)[^"\']*["\']',
        body,
    )
    if tailwind_signal:
        print(f"✗ step 8: Tailwind class detected: {tailwind_signal.group(0)!r}")
        return 1
    # Count inline style usages — should be ≤2 (the muted color rule;
    # maybe one more for a special case). More than that suggests
    # systemic style-in-JSX bleed.
    inline_styles = re.findall(r"style=\{\{[^}]+\}\}", body)
    if len(inline_styles) > 3:
        print(f"✗ step 8: {len(inline_styles)} inline style props found; "
              "expected ≤3 (vanilla-CSS rule allows narrow exceptions only). "
              f"Found: {inline_styles}")
        return 1
    print(f"✓ step 8: vanilla CSS only ({len(inline_styles)} inline style "
          "props within budget; no Tailwind)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
