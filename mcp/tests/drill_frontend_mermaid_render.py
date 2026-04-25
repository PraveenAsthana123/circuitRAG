# RESOURCES: none
"""
Drill: Playwright-based UI verification — every deep-dive page
renders mermaid diagrams CLEANLY (no "Syntax error in text" bombs,
no orphan scratch divs in <body>).

This is the gate that HTML-presence sniffs cannot replace. A page
can ship with all the right §-markers in HTML and still render
red bombs because mermaid v11's strict parser rejects:
- ';' inside sequence message text
- '...' (ellipsis) inside sequence message text
- '<br/>' inside flowchart node labels with securityLevel=strict

Negative-assertion §43-style:
 1. Every deep-dive page returns 200 from a real browser load.
 2. Zero <text> elements containing "Syntax error". NEGATIVE: a
    new mermaid source with '...' or ';' would silently render
    red bombs visible to users; this catches it.
 3. Zero orphan mermaid scratch divs in <body> (id^="dm_").
    NEGATIVE: even when the Mermaid component's cleanupScratch
    runs, a regression that drops the cleanup logic would leave
    permanent error-svg artifacts on the page.
 4. Mermaid mount count == SVG render count. NEGATIVE: a render
    that throws AND fallback <pre> didn't activate would leave
    a "rendering diagram…" loading state forever.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_mermaid_render.py

Requires: playwright + chromium (`pip install playwright; playwright install chromium`).
"""
from __future__ import annotations

import asyncio
import os
import sys

PROD_URL = os.getenv("PROD_URL", "http://localhost:3000")

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"
BOLD = "\033[1m"; NC = "\033[0m"

DEEP_DIVE_PAGES = [
    "/admin/database/deep",
    "/admin/mcp/deep",
    "/admin/breakers/deep",
    "/admin/rag/deep",
    "/admin/microservices/deep",
    "/admin/data/deep",
]


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def main() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"{YELLOW}⚠ playwright not installed — skipping{NC}")
        print(f"  install: pip install playwright && playwright install chromium")
        sys.exit(0)

    fail_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        for page_path in DEEP_DIVE_PAGES:
            step(f"verify {page_path}")
            page = await ctx.new_page()
            try:
                # Cache-bust to force fresh bundle fetch
                bust = int(asyncio.get_event_loop().time())
                resp = await page.goto(f"{PROD_URL}{page_path}?bust={bust}", timeout=30000)
                if not resp or resp.status != 200:
                    print(f"  {RED}✗ HTTP {resp.status if resp else 'no-response'}{NC}")
                    fail_count += 1
                    await page.close()
                    continue

                # Wait for mermaid render to complete (renders are
                # client-side via /mermaid.min.js script load + async
                # render call — 5s is enough for ~15 diagrams).
                await asyncio.sleep(5)

                report = await page.evaluate("""() => ({
                    errorTexts: Array.from(document.querySelectorAll('text'))
                        .filter(t => t.textContent && t.textContent.includes('Syntax error')).length,
                    orphanScratch: document.querySelectorAll('body > div[id^="dm_"]').length,
                    wraps: document.querySelectorAll('.md-mermaid-wrap').length,
                    svgs: document.querySelectorAll('.md-mermaid svg').length,
                })""")

                checks = []
                if report["errorTexts"] != 0:
                    checks.append(
                        f"{RED}✗ {report['errorTexts']} 'Syntax error in text' "
                        f"bomb(s){NC}"
                    )
                else:
                    checks.append(f"{GREEN}✓ 0 syntax errors{NC}")
                if report["orphanScratch"] != 0:
                    checks.append(
                        f"{RED}✗ {report['orphanScratch']} orphan mermaid scratch "
                        f"div(s) in <body> — cleanupScratch regressed{NC}"
                    )
                else:
                    checks.append(f"{GREEN}✓ 0 orphan scratches{NC}")
                if report["wraps"] != report["svgs"]:
                    checks.append(
                        f"{RED}✗ {report['wraps']} mounts but {report['svgs']} "
                        f"SVGs rendered — failed render didn't fall back{NC}"
                    )
                else:
                    checks.append(
                        f"{GREEN}✓ {report['wraps']} mounts == "
                        f"{report['svgs']} SVGs rendered{NC}"
                    )

                for c in checks:
                    print(f"  {c}")
                if (
                    report["errorTexts"] != 0
                    or report["orphanScratch"] != 0
                    or report["wraps"] != report["svgs"]
                ):
                    fail_count += 1

            finally:
                await page.close()
        await browser.close()

    print()
    if fail_count > 0:
        print(f"{BOLD}{RED}════════════════════════════════════════════════{NC}")
        print(f"{BOLD}{RED}  {fail_count}/{len(DEEP_DIVE_PAGES)} PAGE(S) HAVE MERMAID ERRORS{NC}")
        print(f"{BOLD}{RED}════════════════════════════════════════════════{NC}")
        sys.exit(1)
    else:
        print(f"{BOLD}{GREEN}════════════════════════════════════════════════{NC}")
        print(f"{BOLD}{GREEN}  ALL {len(DEEP_DIVE_PAGES)} PAGES RENDER MERMAID CLEANLY{NC}")
        print(f"{BOLD}{GREEN}════════════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
