#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Sentry Stage-1 frontend RUM adapter (per §43 + §47.6 + §57.1).

Locks the offline-safe Sentry browser RUM init that pairs with the
existing ClientErrorReporter component. Stage-1 ships:
  - services/frontend/lib/sentry-init.ts (the adapter)
  - services/frontend/components/SentryInit.tsx (mount-once Client
    Component)
  - app/layout.tsx imports + renders <SentryInit />

The Sentry SDK itself (@sentry/nextjs) is operator-installed; until
then init() catches the ImportError and the page runs normally.

Eight steps. Five negative.

Step coverage:
  1. POSITIVE: adapter file exists + non-trivial size
  2. POSITIVE: SentryInit Client Component exists + 'use client'
  3. POSITIVE: app/layout.tsx imports + renders <SentryInit />
  4. NEGATIVE: DSN read from NEXT_PUBLIC_SENTRY_DSN env, NEVER
     hardcoded literal in source — would leak to client bundle
  5. NEGATIVE: @sentry/nextjs is LAZY-imported (dynamic import()
     inside init function, NOT static at module top — keeps the
     SDK out of every page bundle when DSN is unset)
  6. NEGATIVE: ClientErrorReporter is STILL imported + rendered in
     layout — Sentry is defense-in-depth, NOT a replacement (the
     dev-time backend reporter survives the Sentry add)
  7. NEGATIVE: SentryInit returns null (no UI rendered) — purely
     side-effect via useEffect
  8. POSITIVE: status() reports stage=1 + fail_mode='OPEN' +
     offline_safe=true (matches Langfuse / Rebuff Stage-1 contract)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "services" / "frontend" / "lib" / "sentry-init.ts"
COMPONENT = REPO / "services" / "frontend" / "components" / "SentryInit.tsx"
LAYOUT = REPO / "services" / "frontend" / "app" / "layout.tsx"


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


def main() -> int:
    # ── 1. adapter exists + non-trivial size ──────────────────────────
    step("1. POSITIVE: services/frontend/lib/sentry-init.ts exists")
    if not ADAPTER.exists():
        fail(f"missing: {ADAPTER.relative_to(REPO)}")
    adapter_src = ADAPTER.read_text(encoding="utf-8")
    if len(adapter_src) < 2000:
        fail(f"adapter too short ({len(adapter_src)}b) — likely stub")
    ok(f"{len(adapter_src)}b")

    # ── 2. SentryInit Client Component exists + 'use client' ──────────
    step("2. POSITIVE: SentryInit Client Component exists + 'use client'")
    if not COMPONENT.exists():
        fail(f"missing: {COMPONENT.relative_to(REPO)}")
    comp_src = COMPONENT.read_text(encoding="utf-8")
    if "'use client'" not in comp_src and '"use client"' not in comp_src:
        fail("SentryInit.tsx missing 'use client' directive")
    ok(f"{len(comp_src)}b — 'use client'")

    # ── 3. app/layout.tsx imports + renders <SentryInit /> ────────────
    step("3. POSITIVE: app/layout.tsx imports + renders <SentryInit />")
    if not LAYOUT.exists():
        fail(f"missing: {LAYOUT.relative_to(REPO)}")
    layout_src = LAYOUT.read_text(encoding="utf-8")
    if "import SentryInit" not in layout_src:
        fail("layout.tsx does not import SentryInit")
    if "<SentryInit" not in layout_src:
        fail("layout.tsx does not render <SentryInit />")
    ok("layout.tsx imports + renders SentryInit")

    # ── 4. NEGATIVE: DSN from env var, never hardcoded ────────────────
    step(
        "4. NEGATIVE: DSN read from NEXT_PUBLIC_SENTRY_DSN env var "
        "(never hardcoded — would leak to client bundle)"
    )
    if "NEXT_PUBLIC_SENTRY_DSN" not in adapter_src:
        fail("adapter doesn't read NEXT_PUBLIC_SENTRY_DSN")
    # Reject any literal that looks like a Sentry DSN (https://...@sentry.io/...
    # or self-hosted equivalents). DSN format: scheme://public-key@host/project-id
    dsn_literal = re.search(
        r"['\"]https?://[a-f0-9]{16,}@[^'\"]+['\"]", adapter_src
    )
    if dsn_literal:
        fail(
            f"hardcoded DSN literal found: {dsn_literal.group(0)[:60]}... — "
            "DSN must come from env var only"
        )
    ok("DSN sourced from env; no hardcoded literal")

    # ── 5. NEGATIVE: @sentry/nextjs lazy-imported ─────────────────────
    step(
        "5. NEGATIVE: @sentry/nextjs is LAZY-imported (dynamic import "
        "inside init function, NOT static at module top)"
    )
    # Static value imports of @sentry/nextjs at module top would force
    # the SDK to load on every page render. Type-only imports OK.
    top = "\n".join(adapter_src.splitlines()[:40])
    static_value_import = re.search(
        r"^\s*import\s+(?!type\b)[^;]*from\s+['\"]@sentry/nextjs['\"]",
        top,
        re.MULTILINE,
    )
    if static_value_import:
        fail(
            "@sentry/nextjs statically imported at module top — must be "
            "dynamic import() inside init() so SDK loads only when DSN set"
        )
    if "import('@sentry/nextjs')" not in adapter_src and 'import("@sentry/nextjs")' not in adapter_src:
        fail(
            "adapter must use dynamic import('@sentry/nextjs') inside init()"
        )
    ok("@sentry/nextjs lazy-imported inside init()")

    # ── 6. NEGATIVE: ClientErrorReporter still mounted (defense in depth) ─
    step(
        "6. NEGATIVE: ClientErrorReporter STILL imported + rendered "
        "(Sentry is defense-in-depth, NOT replacement)"
    )
    if "import ClientErrorReporter" not in layout_src:
        fail(
            "layout.tsx no longer imports ClientErrorReporter — Sentry is "
            "supposed to be additive, not replacement"
        )
    if "<ClientErrorReporter" not in layout_src:
        fail(
            "layout.tsx no longer renders <ClientErrorReporter /> — defense "
            "in depth requires both dev-backend reporter AND Sentry RUM"
        )
    ok("ClientErrorReporter still imported + rendered alongside SentryInit")

    # ── 7. NEGATIVE: SentryInit renders null (side-effect only) ───────
    step(
        "7. NEGATIVE: SentryInit returns null (purely side-effect via "
        "useEffect; renders no UI)"
    )
    # Look for `return null` anywhere in the function body
    if not re.search(r"return\s+null\s*;", comp_src):
        fail(
            "SentryInit must `return null;` — it's a side-effect-only "
            "component, no UI"
        )
    # Must use useEffect
    if "useEffect" not in comp_src:
        fail("SentryInit must use useEffect to mount-once init()")
    ok("returns null + useEffect mount")

    # ── 8. POSITIVE: status() shape locked ────────────────────────────
    step(
        "8. POSITIVE: status() reports stage=1 + fail_mode='OPEN' "
        "+ offline_safe=true (Stage-1 contract)"
    )
    if "stage: 1" not in adapter_src:
        fail("status() must report stage: 1")
    if "fail_mode: 'OPEN'" not in adapter_src and 'fail_mode: "OPEN"' not in adapter_src:
        fail(
            "status() must report fail_mode: 'OPEN' — fail-OPEN is the "
            "safety guarantee that must NEVER drift"
        )
    if "offline_safe: true" not in adapter_src:
        fail("status() must report offline_safe: true")
    ok("status reports stage=1 + fail_mode=OPEN + offline_safe=true")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
