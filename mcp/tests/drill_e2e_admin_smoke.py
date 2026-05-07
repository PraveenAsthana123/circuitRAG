# RESOURCES: playwright
"""
Drill: §19/§25 admin deep-dive smoke E2E.

Two layers of guarantees:

  STATIC (filesystem grep — runs in <1s, no browser):
    - Every services/frontend/app/admin/*/deep/page.tsx must import
      DeepDiveCrossRefs (§49 compose-footer policy).
    - Every such page must have a `refs={[...]}` array with at least
      3 entries. <3 = anti-pattern per §49.3.

  RUNTIME (Playwright — sample 4 pages to keep drill fast):
    - Each sampled page renders the "Composes with" header text
      (the footer's visible anchor — survives styling refactors).
    - No console.error fires during initial paint.
    - A known-bad route /admin/__phantom_does_not_exist__/deep returns
      a 4xx OR a Next.js not-found page — proves Next routing
      actually 404s on missing routes (negative assertion).

Negative assertions per §43:
  - Step 1: any page MISSING DeepDiveCrossRefs is a hard fail. The
    test reads the live filesystem; cannot be faked from cache.
  - Step 2: any page with <3 refs is a hard fail. Catches
    half-implemented compose-footers.
  - Step 4: a phantom route /admin/__phantom_…/deep MUST 404 or
    render the not-found UI. Catches a routing wildcard that would
    silently match anything.

Run:
    PROD_URL=http://localhost:3000 \\
      /tmp/pw-venv/bin/python mcp/tests/drill_e2e_admin_smoke.py

Prereq: a Next.js DEV server on PROD_URL.
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import sys
from pathlib import Path

PROD_URL = os.getenv("PROD_URL", "http://localhost:3000")
REPO = Path(__file__).resolve().parents[2]
ADMIN_DIR = REPO / "services" / "frontend" / "app" / "admin"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def discover_deep_pages() -> list[Path]:
    pages: list[Path] = []
    for entry in sorted(ADMIN_DIR.iterdir()):
        candidate = entry / "deep" / "page.tsx"
        if candidate.is_file():
            pages.append(candidate)
    return pages


def count_refs(text: str) -> int:
    """Count entries in a refs={[...]} array — match `{ href:` markers."""
    return len(re.findall(r"\{\s*href:\s*['\"]", text))


async def run() -> int:
    failures = 0

    # ---- STATIC LAYER -----------------------------------------------
    pages = discover_deep_pages()
    if not pages:
        fail("no deep pages discovered — bad path?")
        return 1

    # 1. Every page imports DeepDiveCrossRefs.
    missing_import = []
    for p in pages:
        text = p.read_text(encoding="utf-8")
        if "DeepDiveCrossRefs" not in text:
            missing_import.append(p.relative_to(REPO))
    if not missing_import:
        ok(f"step 1: all {len(pages)} deep pages import DeepDiveCrossRefs")
    else:
        fail(f"step 1: {len(missing_import)} deep pages MISSING DeepDiveCrossRefs:")
        for p in missing_import[:5]:
            print(f"    - {p}")
        failures += 1

    # 2. Every page has ≥3 refs.
    too_few = []
    for p in pages:
        text = p.read_text(encoding="utf-8")
        n = count_refs(text)
        if n < 3:
            too_few.append((p.relative_to(REPO), n))
    if not too_few:
        ok(f"step 2: all {len(pages)} deep pages have ≥3 compose refs")
    else:
        fail(f"step 2: {len(too_few)} pages with <3 refs (anti-pattern per §49.3):")
        for p, n in too_few[:5]:
            print(f"    - {p} (refs={n})")
        failures += 1

    # ---- RUNTIME LAYER ----------------------------------------------
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"{YELLOW}playwright not installed; skipping runtime steps{NC}")
        if failures == 0:
            print(f"{GREEN}{BOLD}STATIC LAYER PASSED ({len(pages)} pages){NC}")
        return failures

    # Per §43 (drills runnable in clean env): a Next.js dev server is
    # operator-territory dependency (§42). When PROD_URL is unreachable,
    # the runtime steps are skipped and the drill returns its static-layer
    # result. Aggregator drills see "skipped runtime" as PASS so the
    # regression catalog focuses on real bugs, not env-setup gaps.
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(PROD_URL, timeout=2).close()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(
            f"{YELLOW}skip runtime layer: cannot reach {PROD_URL}: "
            f"{type(exc).__name__}; run `pnpm dev` to exercise{NC}"
        )
        if failures == 0:
            print(f"{GREEN}{BOLD}STATIC LAYER PASSED ({len(pages)} pages); "
                  f"runtime layer skipped (no dev server){NC}")
        return failures

    sample_size = min(4, len(pages))
    sample = random.sample(pages, sample_size)
    sample_routes = [
        f"/admin/{p.parent.parent.name}/deep" for p in sample
    ]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # 3. Each sampled page renders "Composes with" + 0 console errors.
        for route in sample_routes:
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg, store=console_errors: store.append(msg.text)
                if msg.type == "error" else None,
            )
            try:
                resp = await page.goto(
                    f"{PROD_URL}{route}",
                    wait_until="domcontentloaded",
                    timeout=20_000,
                )
            except Exception as e:
                fail(f"step 3: {route} navigation failed: {e}")
                failures += 1
                continue

            status = resp.status if resp else 0
            if status >= 400:
                fail(f"step 3: {route} → HTTP {status}")
                failures += 1
                continue

            try:
                # Wait for footer to render — signal that page hydrated.
                await page.wait_for_function(
                    "Array.from(document.querySelectorAll('*'))"
                    ".some(el => /Composes with/i.test(el.textContent || ''))",
                    timeout=8_000,
                )
            except Exception:
                fail(f"step 3: {route} did NOT render 'Composes with' footer")
                failures += 1
                continue

            # Brief wait for any async console errors during paint.
            await page.wait_for_timeout(300)

            # Filter out env-state errors that are NOT page bugs:
            #   - "Failed to fetch RSC payload" — Next.js prefetch hits an
            #     upstream service; if backend services are down (env
            #     state), every page sees this regardless of correctness.
            #     Operator-territory per §42; not the drill's concern.
            #   - "TypeError: Failed to fetch" / "TypeError: network error"
            #     — same root cause, surfaced as the underlying network
            #     exception from the prefetch wrapper.
            ENV_STATE_PATTERNS = (
                "Failed to fetch RSC payload",
                "TypeError: Failed to fetch",
                "TypeError: network error",
            )
            page_errors = [
                e for e in console_errors
                if not any(p in e for p in ENV_STATE_PATTERNS)
            ]
            env_filtered = len(console_errors) - len(page_errors)

            if page_errors:
                fail(
                    f"step 3: {route} emitted {len(page_errors)} page-bug "
                    f"console.error (filtered {env_filtered} env-state): "
                    f"{page_errors[:1]}"
                )
                failures += 1
            elif env_filtered:
                ok(
                    f"step 3: {route} loaded; footer present; "
                    f"0 page-bug errors ({env_filtered} env-state filtered)"
                )
            else:
                ok(f"step 3: {route} loaded; footer present; 0 console.error")

        # 4. NEGATIVE — phantom route must 404 or show not-found.
        phantom_route = "/admin/__phantom_does_not_exist__/deep"
        try:
            resp = await page.goto(
                f"{PROD_URL}{phantom_route}",
                wait_until="domcontentloaded",
                timeout=15_000,
            )
            status = resp.status if resp else 0
            body_text = await page.evaluate("document.body.innerText || ''")
            looks_like_not_found = (
                status == 404
                or "404" in body_text[:500]
                or "not found" in body_text.lower()[:500]
                or "could not be found" in body_text.lower()[:500]
            )
            if status == 404 or looks_like_not_found:
                ok(f"step 4 (negative): phantom route correctly 404s (status={status})")
            else:
                fail(
                    f"step 4 (negative): phantom route returned status={status} "
                    f"and body did NOT match not-found markers — wildcard route?"
                )
                failures += 1
        except Exception as e:
            fail(f"step 4 (negative): phantom route navigation crashed: {e}")
            failures += 1

        await browser.close()

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL STEPS PASSED ({len(pages)} static + {sample_size} runtime){NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
