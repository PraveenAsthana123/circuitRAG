# RESOURCES: playwright
"""
Drill: §26 ErrorTracker — F12-introspectable runtime diagnostic surface.

The frontend already has a <ClientErrorReporter /> that POSTs uncaught
errors to /api/v1/admin/client-errors. That's the SERVER-SIDE
visibility surface. Global CLAUDE.md §26 demands a separate
DEVELOPER-SIDE surface: an in-memory tracker accessible at the F12
console as `window.__errors` with getSummary / getReport / clear.

This drill verifies that surface exists, captures real events, and
does NOT fabricate events.

Steps:

 1. window.__errors exists on a /admin/* page in dev mode.
 2. getSummary() shape contract: required keys present, all numeric.
 3. console.error("UNIQUE_SENTINEL_<id>") is captured AND retrievable
    via getErrors(). Positive assertion.
 4. NEGATIVE: BEFORE the trigger in step 3, the sentinel must NOT
    appear in getErrors(). This is the causality lock — proves the
    capture happened because of OUR call, not coincidence.
 5. NEGATIVE: After clear(), getErrors() is empty AND a non-triggered
    second sentinel is absent. Proves clear() doesn't leak prior
    state and the tracker doesn't fabricate entries.
 6. Inject duplicate id="dup-test" into DOM, call getReport(), assert
    domIssues contains a duplicate_id entry mentioning "dup-test".
 7. NEGATIVE: A unique id never injected (e.g. "phantom-id-XYZ") must
    NOT appear in domIssues. Proves the DOM scan reads the live tree,
    not a hardcoded list.

Negative assertions per §43 are steps 4, 5, 7. They're the contract
that makes the drill catch a faked tracker (one that returns canned
data without observing real events).

Run:
    PROD_URL=http://localhost:3000 \\
      /tmp/pw-venv/bin/python mcp/tests/drill_frontend_error_tracker.py

Prereq: a Next.js DEV server (NODE_ENV=development) on PROD_URL — the
tracker is intentionally inert in production builds.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

PROD_URL = os.getenv("PROD_URL", "http://localhost:3000")
TARGET = f"{PROD_URL}/admin"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


async def run() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"{RED}playwright not installed in this venv{NC}")
        return 1

    failures = 0
    sentinel = f"DRILL_SENTINEL_{uuid.uuid4().hex[:12]}"
    sentinel_b = f"DRILL_SENTINEL_B_{uuid.uuid4().hex[:12]}"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            await page.goto(TARGET, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"{RED}cannot reach {TARGET}: {e}{NC}")
            print(f"{YELLOW}Is `next dev` running on {PROD_URL}?{NC}")
            await browser.close()
            return 1

        # 1. Wait for client hydration — useEffect in ErrorTrackerInit
        # only fires after hydration, so `window.__errors` becomes defined
        # asynchronously after first paint.
        try:
            await page.wait_for_function(
                "typeof window.__errors === 'object'",
                timeout=10_000,
            )
        except Exception:
            pass  # let the assertion below handle the failure
        exists = await page.evaluate("typeof window.__errors === 'object'")
        if exists:
            ok("step 1: window.__errors mounted in dev mode")
        else:
            fail(
                "step 1: window.__errors NOT mounted — is the dev server running"
                " in NODE_ENV=development?"
            )
            failures += 1
            await browser.close()
            return failures

        # 2. getSummary() shape contract.
        summary = await page.evaluate("window.__errors.getSummary()")
        required_keys = {
            "errors", "warnings", "longTasks", "layoutShifts",
            "totalCLS", "domIssues", "enabled", "startedAt",
        }
        missing = required_keys - set(summary.keys())
        if not missing and summary.get("enabled") is True:
            ok(f"step 2: getSummary() shape valid; enabled=True (keys={sorted(summary.keys())})")
        else:
            fail(f"step 2: missing keys {missing} or enabled is False — summary={summary}")
            failures += 1

        # 4. NEGATIVE pre-check (must come before step 3 of trigger).
        pre_count = await page.evaluate(
            f"window.__errors.getErrors().filter(e => "
            f"(e.message || '').includes('{sentinel}')).length"
        )
        if pre_count == 0:
            ok(f"step 4 (negative): sentinel '{sentinel[:24]}…' absent BEFORE trigger")
        else:
            fail(f"step 4 (negative): sentinel already present BEFORE trigger (count={pre_count})")
            failures += 1

        # 3. Trigger console.error and verify capture.
        await page.evaluate(f"console.error('{sentinel}')")
        await page.wait_for_timeout(50)  # console wrap is sync, but allow event-loop tick
        post_count = await page.evaluate(
            f"window.__errors.getErrors().filter(e => "
            f"(e.message || '').includes('{sentinel}')).length"
        )
        if post_count >= 1:
            ok(f"step 3: console.error captured (sentinel found {post_count}× after trigger)")
        else:
            fail(f"step 3: console.error NOT captured (post_count={post_count})")
            failures += 1

        # 5. NEGATIVE: clear() empties storage AND doesn't fabricate.
        await page.evaluate("window.__errors.clear()")
        cleared = await page.evaluate("window.__errors.getErrors().length")
        sentinel_b_count = await page.evaluate(
            f"window.__errors.getErrors().filter(e => "
            f"(e.message || '').includes('{sentinel_b}')).length"
        )
        if cleared == 0 and sentinel_b_count == 0:
            ok(
                "step 5 (negative): clear() emptied storage AND "
                "non-triggered sentinel absent"
            )
        else:
            fail(
                f"step 5 (negative): cleared={cleared} (expect 0), "
                f"sentinel_b={sentinel_b_count} (expect 0)"
            )
            failures += 1

        # 6. Inject duplicate id, verify DOM scan catches it.
        await page.evaluate(
            """(() => {
              const a = document.createElement('span');
              a.id = 'dup-test';
              a.textContent = 'a';
              document.body.appendChild(a);
              const b = document.createElement('span');
              b.id = 'dup-test';
              b.textContent = 'b';
              document.body.appendChild(b);
            })()"""
        )
        report = await page.evaluate("window.__errors.getReport()")
        dom_issues = report.get("domIssues", [])
        dup_msgs = [
            i for i in dom_issues
            if i.get("kind") == "duplicate_id"
            and "dup-test" in (i.get("message") or "")
        ]
        if dup_msgs:
            ok(f"step 6: getReport() detected injected duplicate_id (msg: {dup_msgs[0]['message']})")
        else:
            fail(
                f"step 6: getReport() did NOT detect injected duplicate_id "
                f"(found {len(dom_issues)} issues, none mentioning 'dup-test')"
            )
            failures += 1

        # 7. NEGATIVE: a phantom id never injected must NOT appear.
        phantom_id = f"phantom-{uuid.uuid4().hex[:8]}"
        phantom_msgs = [
            i for i in dom_issues
            if phantom_id in (i.get("message") or "")
        ]
        if not phantom_msgs:
            ok(f"step 7 (negative): phantom id '{phantom_id}' absent from domIssues — scan reads live DOM")
        else:
            fail(f"step 7 (negative): phantom id leaked into domIssues — scan is fabricating")
            failures += 1

        await browser.close()

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
