# RESOURCES: frontend
"""
Drill: /admin/python renders 200 with the expected sections + the
two inline SVG flowcharts. Static-content drill — no API surface
to lock, but locks the route's existence + content shape so a
regression that breaks the route or strips the flowcharts is
caught.

Negative-assertion §43-style:
 1. /admin/python returns 200. NEGATIVE: a 404 here would mean
    the page file was renamed/deleted without updating the
    sidebar.
 2. Page contains the section headers from the catalog. NEGATIVE:
    a regression that emptied TOPICS would still render a 200
    shell page; the content sniff catches it.
 3. Page contains BOTH flowchart aria-labels. NEGATIVE: removing
    the SVG components would still render a content-only page;
    the aria-label sniff catches that.
 4. Sidebar HTML on this same page contains the new Python link
    AND the prior Techstack link. NEGATIVE: a regression in
    Sidebar.tsx that lost an entry would still let /admin/python
    render but break navigation discoverability.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_admin_python.py
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


REQUIRED_HEADINGS = [
    "Python concepts for RAG",   # h1
    "Async fan-out",              # flowchart 1 card header
    "Coroutine state",            # flowchart 2 card header
]
REQUIRED_TOPIC_MARKERS = [
    "asyncio.gather",
    "circuit breaker abstraction",
    "Pydantic models",
    "RAG-specific",
    "Project pattern",
]
REQUIRED_FLOWCHART_LABELS = [
    "Async fan-out flow for a RAG request",
    "asyncio coroutine lifecycle",
]
# Per-topic deep-link anchors that MUST appear (the topics that have
# deep-dive entries on /admin/python/deep). Locked by drill so a
# regression that drops the per-topic enrichment goes red.
REQUIRED_DEEP_ANCHORS = [
    "/admin/python/deep#exceptions",
    "/admin/python/deep#decorators",
    "/admin/python/deep#context-managers",
    "/admin/python/deep#async-await",
    "/admin/python/deep#typing-pydantic",
    "/admin/python/deep#iterators-generators",
    "/admin/python/deep#gil-concurrency-models",
    "/admin/python/deep#classes-inheritance-mro",
    "/admin/python/deep#fastapi-middleware",
    "/admin/python/deep#http-pool-retry-breaker",
    "/admin/python/deep#observability-python",
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=15.0) as c:
        step("1. /admin/python returns 200")
        r = await c.get(f"{FRONTEND}/admin/python")
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}")
        body = r.text
        ok(f"200 + {len(body)} bytes")

        step("2. expected section headings present")
        missing = [h for h in REQUIRED_HEADINGS if h not in body]
        if missing:
            fail(f"missing heading(s): {missing}")
        missing_topics = [m for m in REQUIRED_TOPIC_MARKERS if m not in body]
        if missing_topics:
            fail(f"missing topic marker(s): {missing_topics}")
        ok(f"all {len(REQUIRED_HEADINGS)} headings + "
           f"{len(REQUIRED_TOPIC_MARKERS)} topic markers present")

        step("3. both flowcharts present (aria-label sniff)")
        for label in REQUIRED_FLOWCHART_LABELS:
            if label not in body:
                fail(
                    f"flowchart aria-label missing: {label!r}. "
                    f"Stripping the SVG components would render a "
                    f"content-only page; this catches that."
                )
        ok(f"both flowchart aria-labels found")

        step("4. sidebar shows Techstack + Python links on the same page")
        # Sidebar is rendered into every page's HTML by the layout.
        for marker in ("/admin/techstack", "/admin/python", "Operator Dashboard"):
            if marker not in body:
                fail(
                    f"sidebar marker missing: {marker!r}. Either the "
                    f"Sidebar.tsx entry was lost or the layout no "
                    f"longer renders the sidebar on this route."
                )
        ok(f"sidebar exposes Operator Dashboard + Techstack + Python")

        step("5. per-topic deep-dive anchors present (≥10 of the deep set)")
        # Topics with a deep-dive entry on /admin/python/deep MUST link
        # there from this catalog page. Locks the per-topic enrichment.
        missing_anchors = [a for a in REQUIRED_DEEP_ANCHORS if a not in body]
        if len(REQUIRED_DEEP_ANCHORS) - len(missing_anchors) < 10:
            fail(
                f"only {len(REQUIRED_DEEP_ANCHORS) - len(missing_anchors)} "
                f"of {len(REQUIRED_DEEP_ANCHORS)} per-topic deep-dive "
                f"anchors present. Missing: {missing_anchors}. "
                f"Regression that dropped the deepSlug field from topics "
                f"would land here."
            )
        ok(
            f"{len(REQUIRED_DEEP_ANCHORS) - len(missing_anchors)}/"
            f"{len(REQUIRED_DEEP_ANCHORS)} per-topic deep anchors present"
        )

        step("6. per-topic mermaid flowcharts (≥8 inline mounts)")
        # The page-level flowcharts (Async fan-out + Coroutine lifecycle)
        # are inline SVG, not Mermaid. The per-topic flowcharts use the
        # self-hosted Mermaid component → md-mermaid-wrap class.
        # ≥8 = catches a regression that drops most of the enrichment.
        mermaid_mounts = body.count("md-mermaid-wrap")
        if mermaid_mounts < 8:
            fail(
                f"expected ≥8 per-topic mermaid mounts, got "
                f"{mermaid_mounts}. Per-topic flowchart enrichment "
                f"regressed — verify the Mermaid component imports + "
                f"the conditional render in topics.map."
            )
        ok(f"{mermaid_mounts} per-topic mermaid flowcharts rendered")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 ADMIN-PYTHON-PAGE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
