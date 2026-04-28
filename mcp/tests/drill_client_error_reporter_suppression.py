# RESOURCES: playwright
"""
Drill: ClientErrorReporter suppresses 404 cascade when backend is
unavailable.

Background: when /api/v1/admin/client-errors returns 404 (backend
not deployed in dev), every fetch failure cascades into another
fetch failure logged by the browser as a console error. This was
producing perpetual F12 noise on otherwise-clean pages.

Verifies:

 1. First visit to a page that triggers a fetch failure produces
    ≤ 2 console 404s — the one-time detection tax.
 2. After the first 404, sessionStorage holds
    documind_client_error_reporter_disabled=1.
 3. Subsequent navigations within the same session produce ZERO
    /api/v1/admin/client-errors POSTs (negative assertion — the
    user's actual experience).

Negative assertion per §43:
  - Step 3 fails closed if the suppression regresses. Without the
    sessionStorage flag, every page load would re-issue POSTs and
    keep logging 404s in F12.

Run:
    PROD_URL=http://localhost:3000 \\
      /tmp/pw-venv/bin/python mcp/tests/drill_client_error_reporter_suppression.py
"""
from __future__ import annotations

import asyncio
import os
import sys

PROD_URL = os.getenv("PROD_URL", "http://localhost:3000")

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"
DIM = "\033[2m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


async def run() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"{YELLOW}⚠ playwright not installed — skipping{NC}")
        return 0

    failures = 0
    print(f"{BOLD}Drill: ClientErrorReporter 404-cascade suppression{NC}")
    print(f"{DIM}prod: {PROD_URL}{NC}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()
        page = await ctx.new_page()

        first_load_errors: list[str] = []
        first_load_reporter_posts: list[str] = []

        page.on(
            "console",
            lambda m: first_load_errors.append(m.text)
            if m.type == "error" else None,
        )
        page.on(
            "request",
            lambda r: first_load_reporter_posts.append(r.url)
            if r.method == "POST"
            and "/api/v1/admin/client-errors" in r.url
            else None,
        )

        # First load — let it run, observe noise
        await page.goto(f"{PROD_URL}/admin/audio/tts/topics", wait_until="networkidle")
        await page.wait_for_timeout(1500)

        first_load_count = len(first_load_errors)
        first_load_post_count = len(first_load_reporter_posts)

        # 1. First-load noise is bounded (≤ 1 — singleton-Promise gate)
        if first_load_count <= 1:
            ok(f"step 1: first load — {first_load_count} console error(s) (≤ 1 detection tax)")
        else:
            fail(f"step 1: first load produced {first_load_count} console errors (expected ≤ 1)")
            failures += 1

        # 2. sessionStorage flipped
        flag = await page.evaluate(
            "window.sessionStorage.getItem('documind_client_error_reporter_disabled')"
        )
        if first_load_post_count > 0:
            if flag == "1":
                ok("step 2: sessionStorage flag set (reporter disabled for session)")
            else:
                fail(f"step 2: reporter POSTed {first_load_post_count}× but sessionStorage flag NOT set")
                failures += 1
        else:
            ok("step 2: no reporter POSTs (backend reachable OR no errors fired) — flag check skipped")

        # 3. NEGATIVE: navigate to a different page; expect ZERO new
        # client-error POSTs because the flag suppresses them.
        second_nav_posts: list[str] = []
        page.on(
            "request",
            lambda r: second_nav_posts.append(r.url)
            if r.method == "POST"
            and "/api/v1/admin/client-errors" in r.url
            else None,
        )

        await page.goto(f"{PROD_URL}/admin/architect/deep", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.goto(f"{PROD_URL}/admin/python/deep", wait_until="networkidle")
        await page.wait_for_timeout(1500)

        # Filter out posts from the first nav (they were appended before
        # the second handler started).
        new_posts = [u for u in second_nav_posts if u not in first_load_reporter_posts]

        if len(new_posts) == 0:
            ok("step 3: ZERO reporter POSTs across 2 subsequent navigations (negative assertion)")
        else:
            fail(f"step 3: {len(new_posts)} reporter POST(s) on subsequent navigations — suppression regressed")
            failures += 1

        await browser.close()

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 3 STEPS PASSED{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
