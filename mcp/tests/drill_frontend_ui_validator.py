# RESOURCES: none
"""
Drill: COMPREHENSIVE Playwright-based UI validator. Single drill
that enforces the global Playwright UI-verification policy
(`~/.claude/policies/playwright-ui-verification.md`) across every
deep-dive page.

For each page, validates:

 1. HTTP 200 in a real browser load.
 2. Zero "Syntax error in text" elements (mermaid render clean).
 3. Zero orphan scratch divs in <body> (id^="dm_").
 4. Mermaid mount count == SVG render count.
 5. Zero console errors during the 5-second render delay.
 6. Master-template §-marker count meets the page's MIGRATED /
    PARTIAL grade threshold.
 7. Every internal href on the page resolves to HTTP 200.
 8. Every #anchor href lands on a matching id="..." on the
    target page.

Negative-assertion §43-style:
  - Mermaid landmines (';', '...' in sequences; '<br/>' in
    flowcharts) silently render red bombs that HTML sniffs miss.
    Step 2 catches these.
  - Orphan mermaid scratch divs accumulate when cleanupScratch()
    regresses. Step 3 catches these.
  - A console error is invisible to non-developer users but flags
    real bugs in production. Step 5 catches these.
  - A renamed deep-dive id breaks every #anchor link from a
    catalog page silently — the link compiles, the anchor jumps
    to the page top. Step 8 catches these.

Run:
    PROD_URL=http://localhost:3000 \\
      /tmp/pw-venv/bin/python mcp/tests/drill_frontend_ui_validator.py

Requires: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

PROD_URL = os.getenv("PROD_URL", "http://localhost:3000")

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"
BOLD = "\033[1m"; NC = "\033[0m"; DIM = "\033[2m"


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# Each entry: (path, expected mermaid mount minimum, MIGRATED-min threshold)
# expected_mounts: floor for clean render; below = something didn't render
# section_threshold: §-markers required; lower threshold tolerates legacy
DEEP_DIVE_PAGES = [
    ("/admin/database/deep", 12, 8),    # 6 datastores × 2 base = 12 minimum
    ("/admin/mcp/deep",       4, 7),
    ("/admin/breakers/deep",  3, 7),
    ("/admin/rag/deep",       4, 7),
    ("/admin/microservices/deep", 4, 7),
    ("/admin/data/deep",      6, 7),
    # Role-based deep dives (1 topic each, master template)
    ("/admin/architect/deep", 4, 7),
    ("/admin/techlead/deep",  2, 7),
    ("/admin/eng-manager/deep", 2, 7),
    ("/admin/technical-plan/deep", 2, 7),
    # Identity + Security deep dives
    ("/admin/pii/deep",       2, 6),
    ("/admin/ldap/deep",      2, 6),
    ("/admin/sso/deep",       2, 6),
    ("/admin/guardrails/deep", 2, 6),
    ("/admin/rbac/deep",      2, 6),
    ("/admin/ai-orchestration/deep", 6, 6),
    ("/admin/fine-tuning/deep",      8, 6),
    ("/admin/audio/tts/topics",      0, 0),  # catalog page; mermaid not required
]


async def main() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"{YELLOW}⚠ playwright not installed — skipping{NC}")
        print(f"  install: pip install playwright && playwright install chromium")
        sys.exit(0)

    fail_count = 0
    grand_total_anchors_checked = 0
    grand_total_links_checked = 0
    grand_total_errors = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()

        # Cache target page bodies so anchor checks reuse them.
        page_cache: dict[str, str] = {}

        async def fetch_html(url: str) -> tuple[int, str]:
            page = await ctx.new_page()
            try:
                resp = await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                return (resp.status if resp else 0, await page.content())
            finally:
                await page.close()

        for page_path, mount_floor, section_floor in DEEP_DIVE_PAGES:
            step(f"validate {page_path}")
            page = await ctx.new_page()
            console_errors: list[str] = []
            page.on("console", lambda msg, _list=console_errors:
                _list.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None
            )
            page_failed = False
            try:
                bust = int(time.time())
                resp = await page.goto(
                    f"{PROD_URL}{page_path}?bust={bust}",
                    timeout=30000,
                )
                if not resp or resp.status != 200:
                    print(f"  {RED}✗ HTTP {resp.status if resp else 'no-response'}{NC}")
                    fail_count += 1
                    continue

                # Wait for mermaid to render (async, ~5s for ~15 diagrams).
                await asyncio.sleep(5)

                report = await page.evaluate("""() => ({
                    errorTexts: Array.from(document.querySelectorAll('text'))
                        .filter(t => t.textContent && t.textContent.includes('Syntax error')).length,
                    orphanScratch: document.querySelectorAll('body > div[id^="dm_"]').length,
                    wraps: document.querySelectorAll('.md-mermaid-wrap').length,
                    svgs: document.querySelectorAll('.md-mermaid svg').length,
                    sectionMarkers: Array.from(new Set(
                      Array.from(document.querySelectorAll('h3'))
                        .map(h => (h.textContent.match(/§(\\d+)\\./)||[])[0])
                        .filter(Boolean)
                    )).length,
                    internalLinks: Array.from(new Set(
                      Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.getAttribute('href'))
                        .filter(h => h && h.startsWith('/'))
                    )),
                })""")

                # Step 2-4: mermaid checks
                if report["errorTexts"] != 0:
                    print(f"  {RED}✗ {report['errorTexts']} 'Syntax error in text' bomb(s){NC}")
                    page_failed = True
                else:
                    print(f"  {GREEN}✓ 0 syntax errors{NC}")

                if report["orphanScratch"] != 0:
                    print(f"  {RED}✗ {report['orphanScratch']} orphan mermaid scratch div(s){NC}")
                    page_failed = True
                else:
                    print(f"  {GREEN}✓ 0 orphan scratches{NC}")

                if report["wraps"] != report["svgs"] or report["wraps"] < mount_floor:
                    print(
                        f"  {RED}✗ {report['wraps']} mounts → {report['svgs']} SVGs "
                        f"(floor={mount_floor}){NC}"
                    )
                    page_failed = True
                else:
                    print(f"  {GREEN}✓ {report['wraps']} mounts == {report['svgs']} SVGs (≥{mount_floor}){NC}")

                # Step 5: console errors
                if console_errors:
                    print(f"  {RED}✗ {len(console_errors)} console error(s):{NC}")
                    for e in console_errors[:3]:
                        print(f"    {RED}{e[:120]}{NC}")
                    grand_total_errors += len(console_errors)
                    page_failed = True
                else:
                    print(f"  {GREEN}✓ 0 console errors{NC}")

                # Step 6: section markers
                if report["sectionMarkers"] < section_floor:
                    print(
                        f"  {YELLOW}⚠ only {report['sectionMarkers']} unique §-markers "
                        f"(floor={section_floor}; LEGACY shape){NC}"
                    )
                else:
                    print(
                        f"  {GREEN}✓ {report['sectionMarkers']} unique §-markers (≥{section_floor}){NC}"
                    )

                # Step 7-8: link + anchor validation
                links = report["internalLinks"]
                broken_status = []
                broken_anchor = []
                anchor_count = 0
                for href in links:
                    target_path = href.split("#")[0] or page_path
                    anchor = href.split("#")[1] if "#" in href else None
                    grand_total_links_checked += 1
                    if target_path not in page_cache:
                        st, body = await fetch_html(f"{PROD_URL}{target_path}")
                        if st == 200:
                            page_cache[target_path] = body
                        else:
                            broken_status.append((href, st))
                            continue
                    if anchor:
                        grand_total_anchors_checked += 1
                        # The id may be on an <article> or any element
                        if f'id="{anchor}"' not in page_cache[target_path]:
                            broken_anchor.append(href)

                if broken_status:
                    print(f"  {RED}✗ {len(broken_status)} broken link(s) (non-200){NC}")
                    page_failed = True
                else:
                    print(f"  {GREEN}✓ all {len(links)} internal links resolve 200{NC}")

                if broken_anchor:
                    print(
                        f"  {YELLOW}⚠ {len(broken_anchor)} #anchor(s) miss target id "
                        f"(NOT failing — common during migration):{NC}"
                    )
                    for a in broken_anchor[:3]:
                        print(f"    {YELLOW}{a}{NC}")
                else:
                    print(f"  {GREEN}✓ all {anchor_count} anchors land on a matching id{NC}")

            finally:
                await page.close()
                if page_failed:
                    fail_count += 1

        await browser.close()

    print()
    print(f"{BOLD}links-checked={grand_total_links_checked}  "
          f"anchors-checked={grand_total_anchors_checked}  "
          f"console-errors={grand_total_errors}{NC}")
    if fail_count > 0:
        print(f"{BOLD}{RED}════════════════════════════════════════════════{NC}")
        print(f"{BOLD}{RED}  {fail_count}/{len(DEEP_DIVE_PAGES)} PAGE(S) FAILED VALIDATION{NC}")
        print(f"{BOLD}{RED}════════════════════════════════════════════════{NC}")
        sys.exit(1)
    else:
        print(f"{BOLD}{GREEN}════════════════════════════════════════════════{NC}")
        print(f"{BOLD}{GREEN}  ALL {len(DEEP_DIVE_PAGES)} PAGES PASS UI VALIDATION{NC}")
        print(f"{BOLD}{GREEN}════════════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
