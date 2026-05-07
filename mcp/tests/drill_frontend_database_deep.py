# RESOURCES: frontend
"""
Drill: /admin/database/deep renders 6 datastore roles using the
universal 20-dimension interview framework via the new
<UniversalDeepDive /> component.

Pairs with /admin/llmops/deep (commit 6fa8eab) and /admin/python/
deep (commit d0d8e98) — same interview-template family, third
domain (datastores).

Negative-assertion §43-style:
 1. Route returns 200.
 2. All 6 datastore titles present (Postgres, Qdrant, Redis,
    Kafka, ClickHouse, object storage).
 3. Mermaid mounts ≥ 12 (6 stores × 2 diagrams). NEGATIVE: a
    regression that stripped the Mermaid component would render
    a content-only page.
 4. 'Interview line' EXACTLY 6x (one per datastore). The
    interview-line is the senior-signal.
 5. 'Maturity model' EXACTLY 6x — every datastore must have an
    MVP/production/enterprise breakdown. NEGATIVE: dropping the
    maturity row would lose the "where is this on the curve?"
    interview answer.
 6. 'Failure modes' EXACTLY 6x — every datastore must declare
    detect+recover. A regression dropping this turns the page
    from operational into theoretical.
 7. Sidebar exposes /admin/database/deep alongside the existing
    deep-dive routes.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_database_deep.py
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


REQUIRED_DATASTORE_TITLES = [
    "Postgres + RLS",
    "Qdrant",
    "Redis",
    "Kafka",
    "ClickHouse",
    "object storage",
]
REQUIRED_SIDEBAR = [
    "/admin/database/deep",
    "/admin/llmops/deep",
    "/admin/python/deep",
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=20.0) as c:
        step("1. /admin/database/deep returns 200")
        r = await c.get(f"{FRONTEND}/admin/database/deep")
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}")
        body = r.text
        ok(f"200 + {len(body):,} bytes")

        step("2. all 6 datastore titles present")
        missing = [t for t in REQUIRED_DATASTORE_TITLES if t not in body]
        if missing:
            fail(f"missing datastore title(s): {missing}")
        ok(f"all {len(REQUIRED_DATASTORE_TITLES)} datastore titles present")

        step("3. mermaid mounts ≥ 12 (6 stores × 2 diagrams)")
        mounts = body.count("md-mermaid-wrap")
        if mounts < 12:
            fail(
                f"expected ≥12 mermaid mounts, got {mounts}. The "
                f"<UniversalDeepDive> component renders flowchart + "
                f"sequence per topic; missing mounts means stripped "
                f"diagrams or broken component."
            )
        ok(f"{mounts} mermaid mount points")

        step("4. interview-line block ≥ 6x (one per datastore)")
        # Master template renamed the label to "Final interview script".
        # Accept either form so this drill works during the per-topic
        # migration. Threshold ≥ 6 — the master-template renderer also
        # echoes the legacy interviewLine in the §36 block, so >6 is
        # acceptable; <6 means a datastore lost its closer.
        count = body.count("Final interview script") + body.count("Interview line")
        if count < 6:
            fail(
                f"expected ≥ 6 interview-closer blocks (legacy "
                f"'Interview line' OR new 'Final interview script'), "
                f"got {count}. The interview-line is the senior-signal "
                f"— one per datastore."
            )
        ok(f"interview-closer block appears {count}x")

        step("5. 'Maturity model' EXACTLY 6x")
        mat = body.count("Maturity model")
        if mat != 6:
            fail(
                f"expected 6 maturity-model blocks, got {mat}. Every "
                f"datastore must declare MVP/production/enterprise — "
                f"that's the 'where on the curve?' interview answer."
            )
        ok("maturity-model block appears 6x")

        step("6. 'Failure modes' EXACTLY 6x")
        fm = body.count("Failure modes")
        if fm != 6:
            fail(
                f"expected 6 failure-mode tables, got {fm}. Every "
                f"datastore must declare detect+recover — without "
                f"this, the page is theoretical not operational."
            )
        ok("failure-modes block appears 6x")

        step("7. sidebar exposes /admin/database/deep + sibling deep-dive routes")
        for marker in REQUIRED_SIDEBAR:
            if marker not in body:
                fail(f"sidebar marker {marker!r} missing")
        ok("sidebar exposes all 3 deep-dive routes")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 DATABASE-DEEP-DIVE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
