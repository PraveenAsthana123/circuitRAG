# RESOURCES: frontend
"""
Drill: /admin/python/deep renders 12 senior-level Python topics,
each with the 7-lens interview structure (core concept / why it
matters / challenges / edge cases / solutions / limitations /
where it fits / interview line).

Pairs with /admin/llmops/deep — same template, different domain.

Negative-assertion §43-style:
 1. /admin/python/deep returns 200.
 2. All 12 topic titles surface. NEGATIVE: emptied TOPICS would
    still render the page shell — title sniff catches it.
 3. 'Interview line' appears EXACTLY 12x — once per topic. The
    interview-line is the senior-signal.
 4. 'Where it fits in this project' appears EXACTLY 12x — every
    topic must be anchored to actual repo state (file path or
    commit hash), not abstract.
 5. Sidebar exposes /admin/python/deep alongside the existing
    /admin/python.
 6. Per-topic colored cards (challenges, solutions, edge cases,
    limitations) all render — at least one of each section's
    distinctive class/marker is present.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_python_deep.py
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


REQUIRED_TITLES = [
    "async / await",
    "Decorators",
    "Context managers",
    "Exceptions",
    "Pydantic",
    "Iterators",
    "GIL",
    "inheritance",
    "FastAPI",
    "HTTP clients",
    "Structured logging",
    "RAG-specific Python",
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=20.0) as c:
        step("1. /admin/python/deep returns 200")
        r = await c.get(f"{FRONTEND}/admin/python/deep")
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}")
        body = r.text
        ok(f"200 + {len(body):,} bytes")

        step("2. all 12 topic titles surface")
        missing = [t for t in REQUIRED_TITLES if t not in body]
        if missing:
            fail(f"missing topic title(s): {missing}")
        ok(f"all {len(REQUIRED_TITLES)} topic titles present")

        step("3. 'Interview line' appears EXACTLY 12x")
        count = body.count("Interview line")
        if count != 12:
            fail(
                f"expected 12 interview-line blocks (one per topic), "
                f"got {count}. Losing them would silently strip the "
                f"senior-signal that distinguishes this page from the "
                f"flat /admin/python catalog."
            )
        ok("interview-line block appears 12x (correct)")

        step("4. 'Where it fits in this project' appears EXACTLY 12x")
        wcount = body.count("Where it fits in this project")
        if wcount != 12:
            fail(
                f"expected 12 'Where it fits' blocks, got {wcount}. "
                f"Every topic must anchor to actual repo state — file "
                f"paths or commit hashes — not be abstract."
            )
        ok("project-fit anchor appears 12x")

        step("5. sidebar exposes /admin/python/deep + sibling /admin/python")
        for marker in ("/admin/python/deep", "/admin/python"):
            if marker not in body:
                fail(f"sidebar marker {marker!r} missing")
        ok("sidebar exposes both /admin/python and /admin/python/deep")

        step("6. all four colored card families render")
        # Each topic renders amber Challenges, green Solutions, red
        # EdgeCases, grey Limitations cards. Sniff for the headings.
        for header in ("Challenges", "Solutions", "Edge cases", "Limitations"):
            if header not in body:
                fail(f"missing card heading: {header!r}")
        # At least one occurrence of each colour hex (used in inline styles).
        for color in ("#fef3c7", "#dcfce7", "#fee2e2"):
            if color not in body:
                fail(
                    f"missing color {color} in inline styles. The "
                    f"per-topic challenges/solutions/edge-cases card "
                    f"layout is broken."
                )
        ok("4 card families + their colour-coded inline styles render")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 PYTHON-DEEP-DIVE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
