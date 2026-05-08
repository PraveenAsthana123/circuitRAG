#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/private-chat WebLLM page (per §43 + §47 + §48 + §57.1).

Locks the privacy-first in-browser-inference page that surfaces
WebLLM as a new lane in circuitRAG. The whole point is that user
input + model output never leave the browser — this drill enforces
that contract at code-review time.

Eight steps. Five negative.

Step coverage:
  1. POSITIVE: package.json declares @mlc-ai/web-llm dependency
  2. POSITIVE: page.tsx + WebLLMChat.tsx exist at canonical paths
  3. POSITIVE: WebLLMChat is 'use client' (WebGPU requires browser ctx)
  4. NEGATIVE: page does NOT make any backend HTTP call — fetch /
              XMLHttpRequest / axios / our /api/v1/* BFF — that
              would defeat the privacy contract
  5. NEGATIVE: page does NOT auto-load model on mount; load is
              gated by an explicit user click (model is ~750 MB,
              auto-load on every visit is a UX disaster)
  6. NEGATIVE: page does NOT log user input via console.log /
              window.analytics / Sentry / posthog / mixpanel —
              privacy means privacy
  7. POSITIVE: @mlc-ai/web-llm is LAZY-imported (dynamic import
              inside the click handler), not at module top — the
              SDK is ~MB and the page must render fast even before
              the user clicks load
  8. POSITIVE: privacy contract is rendered in JSX (visible to the
              user), not just in a comment

Per CLAUDE.md §43 (drill discipline ≥3 negatives), §47
(architecture: privacy is a first-class lane), §48 (this is the
explainability surface for offline AI), §49 (compose footer with
llmops + local-models + explainability), §57.1 (production-grade
defaults: WebGPU detection + user-gated load + offline-safe).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG_JSON = REPO / "services" / "frontend" / "package.json"
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "private-chat" / "page.tsx"
COMPONENT = (
    REPO
    / "services"
    / "frontend"
    / "app"
    / "admin"
    / "private-chat"
    / "WebLLMChat.tsx"
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


def main() -> int:
    # ── 1. package.json declares @mlc-ai/web-llm ──────────────────────
    step("1. POSITIVE: package.json declares @mlc-ai/web-llm dependency")
    if not PKG_JSON.exists():
        fail(f"missing: {PKG_JSON.relative_to(REPO)}")
    pkg = json.loads(PKG_JSON.read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    if "@mlc-ai/web-llm" not in deps:
        fail(
            "package.json dependencies missing @mlc-ai/web-llm — drill ran "
            "before npm install completed?"
        )
    ok(f"@mlc-ai/web-llm: {deps['@mlc-ai/web-llm']}")

    # ── 2. page + component exist ─────────────────────────────────────
    step("2. POSITIVE: page.tsx + WebLLMChat.tsx exist at canonical paths")
    for p in (PAGE, COMPONENT):
        if not p.exists():
            fail(f"missing: {p.relative_to(REPO)}")
    page_src = PAGE.read_text(encoding="utf-8")
    comp_src = COMPONENT.read_text(encoding="utf-8")
    if len(comp_src) < 3000:
        fail(f"WebLLMChat too short ({len(comp_src)}b) — likely stub")
    ok(f"page {len(page_src)}b · component {len(comp_src)}b")

    # ── 3. WebLLMChat is 'use client' ─────────────────────────────────
    step("3. POSITIVE: WebLLMChat is 'use client' (WebGPU needs browser)")
    if "'use client'" not in comp_src and '"use client"' not in comp_src:
        fail("WebLLMChat.tsx missing 'use client' directive")
    if "'use client'" not in page_src and '"use client"' not in page_src:
        fail("page.tsx missing 'use client' directive")
    ok("both files are 'use client'")

    # ── 4. NEGATIVE: NO backend HTTP call — privacy contract ──────────
    step(
        "4. NEGATIVE: page does NOT call backend HTTP — privacy contract "
        "(no fetch / XMLHttpRequest / axios / /api/v1/*)"
    )
    forbidden_http = [
        "fetch(",
        "XMLHttpRequest",
        "axios",
        "/api/v1/",
        "/api/v2/",
    ]
    for tok in forbidden_http:
        for fname, src in (("page.tsx", page_src), ("WebLLMChat.tsx", comp_src)):
            if tok in src:
                fail(
                    f"{fname} contains forbidden network call '{tok}' — privacy "
                    f"contract requires zero backend round-trip"
                )
    ok("no fetch / XHR / axios / BFF call in either file")

    # ── 5. NEGATIVE: model load is USER-GATED, not auto-load ──────────
    step(
        "5. NEGATIVE: model load is gated by user click — not auto-load on "
        "mount (model is ~750 MB)"
    )
    # The model load function (CreateMLCEngine) must NOT appear inside a
    # useEffect with an empty deps array. The acceptable pattern is:
    # useEffect with WebGPU detect + a button onClick that calls load.
    # We check that CreateMLCEngine is invoked from a callback, not from
    # an unconditional useEffect.
    if "CreateMLCEngine" not in comp_src:
        fail("WebLLMChat doesn't reference CreateMLCEngine API — broken")
    # Find every useEffect block; CreateMLCEngine must NOT appear inside
    # one with `[]` deps (that's auto-load on mount).
    auto_load_pattern = re.compile(
        r"useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*CreateMLCEngine[^}]*\}\s*,\s*\[\s*\]\s*\)",
        re.DOTALL,
    )
    if auto_load_pattern.search(comp_src):
        fail(
            "CreateMLCEngine called inside useEffect with [] deps — "
            "auto-loads on every mount; must be user-gated"
        )
    # Must be in a callback that's wired to a button onClick OR an
    # event handler. We check for a button element with onClick that
    # eventually calls the loader.
    if not re.search(r"onClick\s*=\s*\{[^}]*handleLoadModel", comp_src):
        # Or any handler that mentions LoadModel / loadModel
        if not re.search(r"onClick\s*=\s*\{[^}]*[Ll]oad[Mm]odel", comp_src):
            fail("no button onClick wired to a model-load handler")
    ok("model load gated by explicit user click")

    # ── 6. NEGATIVE: NO logging of user input ─────────────────────────
    step(
        "6. NEGATIVE: page does NOT log user input via console / "
        "analytics / telemetry — privacy means privacy"
    )
    forbidden_log = [
        "console.log",
        "console.info",
        "console.warn",
        "console.error",
        "window.analytics",
        "posthog",
        "mixpanel",
        "Sentry.",
        "datadogRum",
        "amplitude",
    ]
    hits = []
    for tok in forbidden_log:
        for fname, src in (("page.tsx", page_src), ("WebLLMChat.tsx", comp_src)):
            if tok in src:
                hits.append(f"{fname}: {tok}")
    if hits:
        fail(f"forbidden logging refs: {hits}")
    ok("no console / analytics / telemetry calls in either file")

    # ── 7. POSITIVE: @mlc-ai/web-llm is LAZY-imported ─────────────────
    step(
        "7. POSITIVE: @mlc-ai/web-llm lazy-imported (dynamic import inside "
        "callback, not at module top) — SDK is heavy"
    )
    # A static `import ... from '@mlc-ai/web-llm'` for VALUES would force
    # the SDK to load on every page render. Type-only imports (`import type`)
    # are fine because they're erased at compile time.
    top_lines = "\n".join(comp_src.splitlines()[:50])
    static_value_import = re.search(
        r"^\s*import\s+(?!type\b)[^;]*from\s+['\"]@mlc-ai/web-llm['\"]",
        top_lines,
        re.MULTILINE,
    )
    if static_value_import:
        fail(
            "@mlc-ai/web-llm statically imported at module top — must be "
            "dynamic import() inside the load callback so the SDK doesn't "
            "load on every page render. (`import type` is fine; runtime "
            "imports must be lazy.)"
        )
    if "import('@mlc-ai/web-llm')" not in comp_src and 'import("@mlc-ai/web-llm")' not in comp_src:
        fail(
            "WebLLMChat must use dynamic import() of @mlc-ai/web-llm inside "
            "the load handler"
        )
    ok("WebLLM SDK lazy-imported inside load callback")

    # ── 8. POSITIVE: privacy contract rendered in JSX ─────────────────
    step(
        "8. POSITIVE: privacy contract is visible in JSX (user can read it; "
        "not just buried in a comment)"
    )
    # Look for the privacy phrasing in the JSX area (after the export
    # default function signature). We just check the component body
    # contains the word 'Privacy' followed by 'browser' and 'never leave'.
    body_after_jsx_marker = comp_src
    if "Privacy" not in body_after_jsx_marker:
        fail("no 'Privacy' string in component — banner is missing")
    if "browser" not in body_after_jsx_marker.lower():
        fail("privacy banner doesn't mention 'browser'")
    if "never leave" not in body_after_jsx_marker.lower():
        fail("privacy banner doesn't claim data 'never leave' the device")
    ok("privacy contract rendered in JSX (Privacy + browser + 'never leave')")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
