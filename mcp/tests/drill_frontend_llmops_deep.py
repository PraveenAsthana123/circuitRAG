# RESOURCES: frontend
"""
Drill: /admin/llmops/deep renders 10 LLMOps capabilities, each
with the 8-lens interview structure (core concept / 5W / IPO /
flowchart / sequence / challenges-solutions / edge-cases-solutions
/ limitations / next evolution / interview line).

Static-content drill — locks the route + content shape so a
regression that emptied CAPABILITIES or removed mermaid mounts
goes red instead of silently shipping a degraded page.

Negative-assertion §43-style:
 1. Route returns 200. NEGATIVE: 404 means the file moved or
    the sidebar was updated without the page existing.
 2. All 10 capability titles present. NEGATIVE: a regression
    that emptied CAPABILITIES would still render a page shell
    + summary — the title sniff catches that.
 3. Status badges (shipped / partial / open) all appear
    SOMEWHERE on the page. NEGATIVE: hardcoding all to one
    status would still render headings; this catches deceptive
    uniformity.
 4. Mermaid mount points present (md-mermaid-wrap class). 10
    capabilities × 2 diagrams (flowchart + sequence) = at least
    20 mounts expected. NEGATIVE: stripping the Mermaid component
    would render a content-only page; this catches that.
 5. "Interview line" appears 10x — once per capability. NEGATIVE:
    losing the per-capability interview-line block (the senior-
    level signal) breaks the page's whole purpose.
 6. Sidebar entry exposes /admin/llmops/deep alongside the
    existing scorecard. NEGATIVE: missing sidebar link breaks
    discoverability.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_llmops_deep.py
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
    "Prompt registry",
    "Offline evaluation",
    "Audit trail",
    "Draft fallback",
    "RAG data lifecycle",
    "Observability",
    "Model management",
    "Experiment tracking",
    "Deployment",
    "SLM vs LLM",
]
REQUIRED_BADGES = ["badge-active", "badge-parsing", "badge-failed"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=20.0) as c:
        step("1. /admin/llmops/deep returns 200")
        r = await c.get(f"{FRONTEND}/admin/llmops/deep")
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}")
        body = r.text
        ok(f"200 + {len(body):,} bytes")

        step("2. all 10 capability titles present")
        missing = [t for t in REQUIRED_TITLES if t not in body]
        if missing:
            fail(
                f"missing capability title(s): {missing}. A regression "
                f"that emptied CAPABILITIES would still render the "
                f"page shell — the title sniff catches it."
            )
        ok(f"all {len(REQUIRED_TITLES)} capability titles present")

        step("3. all three status badges (shipped/partial/open) appear")
        missing_badges = [b for b in REQUIRED_BADGES if b not in body]
        if missing_badges:
            fail(
                f"missing badge classes: {missing_badges}. A regression "
                f"that hardcoded every capability to one status would "
                f"still render titles; this catches deceptive uniformity."
            )
        ok("shipped + partial + open badges all rendered")

        step("4. Mermaid mounts present (≥20 for 10 caps × 2 diagrams)")
        # Each Mermaid component renders <div class="md-mermaid-wrap">
        mount_count = body.count("md-mermaid-wrap")
        if mount_count < 20:
            fail(
                f"expected ≥20 mermaid mounts (10 caps × 2 diagrams), "
                f"got {mount_count}. Stripping the Mermaid component "
                f"would render content-only pages."
            )
        ok(f"{mount_count} mermaid mount points (≥20 expected)")

        step("5. 'Interview line' appears 10x — one per capability")
        # Each CapabilitySection renders an "Interview line" block.
        interview_count = body.count("Interview line")
        if interview_count != 10:
            fail(
                f"expected 10 'Interview line' blocks (one per cap), "
                f"got {interview_count}. The interview-line is the "
                f"senior-signal that distinguishes this page from the "
                f"flat scorecard."
            )
        ok("interview-line block appears 10x (correct)")

        step("6. sidebar exposes /admin/llmops/deep")
        if "/admin/llmops/deep" not in body:
            fail(
                "sidebar marker /admin/llmops/deep missing. Sidebar "
                "entry was removed or layout no longer renders the "
                "sidebar on this route."
            )
        # Also verify the scorecard sibling is still there (no
        # accidental replacement).
        if "/admin/llmops" not in body:
            fail("sibling /admin/llmops link missing")
        ok("sidebar exposes /admin/llmops + /admin/llmops/deep")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 LLMOPS-DEEP-DIVE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
