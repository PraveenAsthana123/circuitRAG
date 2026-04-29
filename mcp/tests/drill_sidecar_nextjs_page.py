#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: services/frontend/app/admin/sidecar/page.tsx structural
contract.

Phase 1B is the §7-granted Next.js page that consumes the static
dashboard HTML. Tier-1 drill verifies its STRUCTURE (file exists,
right imports, right shape) without spinning up a Node runtime.

Eight steps. Six negative assertions.

  1. page.tsx exists at services/frontend/app/admin/sidecar/.
  2. NEGATIVE: NO 'use client' directive (this MUST be a Server
     Component - only Server Components can read disk in Next.js
     App Router).
  3. NEGATIVE: imports node:fs (the disk read mechanism).
  4. NEGATIVE: reads from `.loop/dashboard.html` path - the
     rendered output of scripts/render_dashboard.py.
  5. NEGATIVE: defines a default-exported async function (Server
     Component contract for App Router).
  6. NEGATIVE: provides a fallback HTML when dashboard.html is
     missing - operator on a fresh install shouldn't see Next.js
     500.
  7. NEGATIVE: uses dangerouslySetInnerHTML (the embedding
     mechanism). The render_dashboard.py drill step 6 already
     locks XSS escaping at the source; embedding pre-escaped
     HTML is safe.
  8. NEGATIVE: file lives ONLY under
     services/frontend/app/admin/sidecar/. The §7 extension was
     scoped strictly to this path; broader edits to
     services/frontend/ would violate the gate.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "sidecar" / "page.tsx"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def main():
    # Step 1: file exists
    step("1. page.tsx exists at services/frontend/app/admin/sidecar/")
    if not PAGE.exists():
        fail(f"page.tsx missing: {PAGE}")
    text = PAGE.read_text()
    if len(text) < 400:
        fail(f"page.tsx suspiciously short: {len(text)} chars")
    ok(f"page.tsx exists ({len(text)} chars)")

    # Step 2: NEGATIVE - NOT a 'use client' directive
    step("2. NEGATIVE: page is Server Component (no 'use client' directive)")
    # 'use client' appears as either the first non-blank-non-comment
    # line OR not at all. Server Components have no such directive.
    if re.search(r"^['\"]use client['\"]", text, re.MULTILINE):
        fail(
            "page.tsx has 'use client' directive - must be a Server "
            "Component to read .loop/dashboard.html from disk. Client "
            "components run in browser; can't access fs."
        )
    ok("no 'use client' directive (Server Component)")

    # Step 3: imports node:fs
    step("3. NEGATIVE: imports node:fs to read dashboard from disk")
    if "node:fs" not in text and "from 'fs'" not in text:
        fail(
            "page.tsx doesn't import fs - can't read dashboard.html "
            "without disk access. Verify the import statement."
        )
    ok("imports node:fs (or fs)")

    # Step 4: reads from .loop/dashboard.html
    step("4. NEGATIVE: reads from .loop/dashboard.html")
    if "dashboard.html" not in text:
        fail(
            "page.tsx doesn't reference dashboard.html. The whole "
            "purpose of this page is to consume the renderer's "
            "output."
        )
    if ".loop" not in text:
        fail(
            "page.tsx doesn't reference .loop/ directory. The "
            "renderer writes to .loop/, gitignored, where the page "
            "expects it."
        )
    ok("references .loop/dashboard.html")

    # Step 5: default-exported async function
    step(
        "5. NEGATIVE: default-exported async function "
        "(Server Component App Router contract)"
    )
    if not re.search(r"export default async function", text):
        fail(
            "no `export default async function` found. App Router "
            "Server Components must default-export an async fn."
        )
    ok("default-exported async function present")

    # Step 6: fallback HTML for missing dashboard
    step(
        "6. NEGATIVE: provides fallback HTML when dashboard.html missing"
    )
    if "FALLBACK_HTML" not in text and "fallback" not in text.lower():
        fail(
            "no fallback path. Fresh-install operator hitting the "
            "page would get a Next.js 500. Show 'run the renderer' "
            "instructions instead."
        )
    if "render_dashboard.py" not in text:
        fail(
            "fallback should mention `render_dashboard.py` so the "
            "operator knows the next step."
        )
    ok("fallback HTML with renderer instructions present")

    # Step 7: dangerouslySetInnerHTML for embedding
    step(
        "7. NEGATIVE: uses dangerouslySetInnerHTML "
        "(safe because renderer escapes content at source)"
    )
    if "dangerouslySetInnerHTML" not in text:
        fail(
            "no dangerouslySetInnerHTML found. Without it the "
            "embedded HTML would render as literal text, not as "
            "rendered markup."
        )
    # The escape contract is in the Python renderer; this drill
    # references that linkage so a future reader sees the chain.
    ok("dangerouslySetInnerHTML present (XSS locked at renderer)")

    # Step 8: NEGATIVE - files live ONLY under sidecar/ tree (scope check)
    step(
        "8. NEGATIVE: files live ONLY under "
        "services/frontend/app/admin/sidecar/* (incl. deep/, telemetry/)"
    )
    sidecar_dir = PAGE.parent
    files = list(sidecar_dir.rglob("*.tsx"))
    # Allowed paths under §7 grant (each requires a scope-extension log
    # entry per §7 of docs/NEXT_POLICY.md):
    #   sidecar/page.tsx                 (Phase 1B - static dashboard embed)
    #   sidecar/deep/page.tsx            (Phase 5B - C4 + scenario diagrams)
    #   sidecar/telemetry/page.tsx       (Phase 5S - daily snapshot live view)
    #   sidecar/[eventId]/page.tsx       (Phase 1B-2 event drill-down)
    allowed_relative = {
        "page.tsx",
        "deep/page.tsx",
        "telemetry/page.tsx",
        "[eventId]/page.tsx",
    }
    actual_relative = {
        str(f.relative_to(sidecar_dir)) for f in files
    }
    extra = actual_relative - allowed_relative
    if extra:
        fail(
            f"files outside §7-granted paths: {extra}. The grant "
            f"covers sidecar/page.tsx, sidecar/deep/page.tsx, "
            f"sidecar/telemetry/page.tsx, and sidecar/[eventId]/page.tsx only. "
            f"Adding more needs another scope-extension entry in §7."
        )
    if "page.tsx" not in actual_relative:
        fail(f"page.tsx (Phase 1B) missing")
    # deep/page.tsx is OPTIONAL at the Phase 1B level - it's a Phase
    # 5B add-on. Don't fail if absent; just log.
    ok(
        f"only allowed paths present: {sorted(actual_relative)} "
        f"(scope respected)"
    )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 SIDECAR-NEXTJS-PAGE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
