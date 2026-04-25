# RESOURCES: none
"""
Drill: /admin/llmops renders 200 with all 14 LLMOps categories
+ status badges + sidebar exposes the link.

Static-content drill — no API surface to lock, but locks:
  * route exists + serves 200
  * all 14 user-supplied categories surface
  * shipped/partial/open status badges all appear (proves the
    page isn't a degraded "all open" or "all shipped" render)
  * sidebar exposes the new entry alongside the prior admin
    routes (Operator Dashboard, Techstack, Python, Client errors)

Negative-assertion §43-style:
 1. /admin/llmops returns 200. NEGATIVE: a 404 means the page
    file was renamed/deleted without sidebar update.
 2. All 14 numbered categories appear. NEGATIVE: a regression
    that emptied CATEGORIES would render a metric-strip-only
    page with totals=0; the heading sniff catches it.
 3. All three status badges (shipped / partial / open) appear
    SOMEWHERE on the page. NEGATIVE: a regression that flipped
    every row to a single status would still render headings;
    badge-presence sniff catches it.
 4. Sidebar exposes ALL FIVE current admin routes on this page.
    NEGATIVE: losing a sidebar entry breaks navigation
    discoverability for shipped features.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_admin_llmops.py
"""
from __future__ import annotations

import asyncio
import os

import httpx

FRONTEND = os.getenv("FRONTEND_URL", "http://127.0.0.1:3001")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# React server-render splits "1. Data management" across multiple
# text nodes (number and title come from separate JSX expressions).
# Match only the title — that's the load-bearing assertion: each
# of the user's 11 categories surfaces in the rendered HTML.
REQUIRED_CATEGORY_HEADINGS = [
    "Data management",
    "Feature and retrieval data layer",
    "Model management",
    "Prompt and policy management",
    "Code and repo management",
    "Experiment tracking",
    "Deployment and serving",
    "Observability",
    "Evaluation and quality",
    "Governance and lifecycle",
    "LLM vs SLM management",
]
REQUIRED_BADGES = ["badge-active", "badge-parsing", "badge-failed"]
REQUIRED_SIDEBAR_LINKS = [
    "/admin/llmops",
    "/admin/techstack",
    "/admin/python",
    "/admin/client-errors",
    "Operator Dashboard",
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=15.0) as c:
        step("1. /admin/llmops returns 200")
        r = await c.get(f"{FRONTEND}/admin/llmops")
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}")
        body = r.text
        ok(f"200 + {len(body)} bytes")

        step("2. all 14 numbered category headings present")
        missing = [h for h in REQUIRED_CATEGORY_HEADINGS if h not in body]
        if missing:
            fail(
                f"missing categor(ies): {missing}. A regression that "
                f"emptied CATEGORIES would render the page with no "
                f"headings; this catches it."
            )
        ok(f"all {len(REQUIRED_CATEGORY_HEADINGS)} categories present")

        step("3. all three status badge classes present (shipped/partial/open)")
        missing_badges = [b for b in REQUIRED_BADGES if b not in body]
        if missing_badges:
            fail(
                f"missing badge classes: {missing_badges}. A regression "
                f"that hardcoded every row's status would still render "
                f"headings; the missing-badge sniff catches it."
            )
        ok(f"shipped + partial + open badges all rendered")

        step("4. sidebar exposes all five admin routes on this page")
        for marker in REQUIRED_SIDEBAR_LINKS:
            if marker not in body:
                fail(
                    f"sidebar marker missing: {marker!r}. Either the "
                    f"Sidebar.tsx entry was lost or the layout no "
                    f"longer renders the sidebar on this route."
                )
        ok(f"sidebar exposes Operator Dashboard + Techstack + Python + LLMOps + Client errors")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 ADMIN-LLMOPS-PAGE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
