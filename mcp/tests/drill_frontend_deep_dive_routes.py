# RESOURCES: none
"""
Drill: all 5 new deep-dive routes (/admin/mcp /breakers /rag
/microservices /data) render 200 with the universal interview
template + mermaid mounts + interview lines.

Pairs with the per-page drills (drill_frontend_database_deep,
drill_frontend_python_deep, drill_frontend_llmops_deep). This
drill is the consolidated regression test for the deep-dive
family.

Negative-assertion §43-style:
 1. All 5 routes return 200.
 2. Each page contains 'Interview line' (≥1) — proves the
    UniversalDeepDive component rendered.
 3. Each page contains ≥2 mermaid mounts (1 topic × 2 diagrams
    minimum) — proves diagrams aren't stripped.
 4. Each page contains 'Maturity model' + 'Failure modes' +
    'Where it fits in this project' — proves the universal
    template's load-bearing sections all render.
 5. Sidebar exposes all 5 routes alongside existing deep-dives.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_deep_dive_routes.py
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


ROUTES = [
    "/admin/mcp/deep",
    "/admin/breakers/deep",
    "/admin/rag/deep",
    "/admin/microservices/deep",
    "/admin/data/deep",
]
REQUIRED_TEMPLATE_MARKERS = [
    "Interview line",
    "Maturity model",
    "Failure modes",
    "Where it fits in this project",
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as c:
        bodies: dict[str, str] = {}
        step("1. all 5 deep-dive routes return 200")
        for r in ROUTES:
            resp = await c.get(f"{FRONTEND}{r}")
            if resp.status_code != 200:
                fail(f"{r} returned {resp.status_code}")
            bodies[r] = resp.text
            print(f"    {r} -> 200 ({len(resp.text):,} bytes)")
        ok(f"all {len(ROUTES)} routes return 200")

        step("2. each page contains 'Interview line' (≥1)")
        for r, body in bodies.items():
            count = body.count("Interview line")
            if count < 1:
                fail(
                    f"{r}: 0 Interview-line blocks. The "
                    f"UniversalDeepDive component didn't render."
                )
            print(f"    {r}: {count} interview line(s)")
        ok("interview-line blocks present on every page")

        step("3. each page has ≥2 mermaid mounts (1 topic × 2 diagrams min)")
        for r, body in bodies.items():
            mounts = body.count("md-mermaid-wrap")
            if mounts < 2:
                fail(
                    f"{r}: {mounts} mermaid mounts. Universal template "
                    f"renders flowchart + sequence per topic — minimum "
                    f"is 2 for a 1-topic page."
                )
            print(f"    {r}: {mounts} mermaid mounts")
        ok("≥2 mermaid mounts present on every page")

        step("4. each page contains all 4 universal-template markers")
        for r, body in bodies.items():
            missing = [m for m in REQUIRED_TEMPLATE_MARKERS if m not in body]
            if missing:
                fail(
                    f"{r}: missing universal-template marker(s): "
                    f"{missing}. The component's load-bearing sections "
                    f"didn't render."
                )
        ok(f"all {len(REQUIRED_TEMPLATE_MARKERS)} markers present on every page")

        step("5. sidebar exposes all 5 routes")
        # Pick any page; sidebar is rendered into every page's HTML.
        body = bodies[ROUTES[0]]
        for r in ROUTES:
            if r not in body:
                fail(f"sidebar marker {r!r} missing")
        ok(f"sidebar exposes all {len(ROUTES)} new deep-dive routes")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 DEEP-DIVE-ROUTES STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
