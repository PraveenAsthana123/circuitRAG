# RESOURCES: none
"""
Drill: AUDIT every deep-dive page for the MASTER 36-section
template + HLD + LLD coverage. Reports per-topic completeness so
the operator knows which topics are MIGRATED, PARTIAL, or LEGACY.

This is an AUDIT drill, not a gate. The drill ALWAYS passes (exit
0) but emits a green/yellow/red coverage map. Use it to drive the
next loop iteration's targets.

The audit walks each deep-dive route, locates every topic anchor
(<article id="...">), and counts how many of the 29 §N. master-
template markers appear *within* each topic block. A topic is:

  MIGRATED  if it has ≥ 27 of 29 markers (full template)
  PARTIAL   if it has 8-26 markers (partial migration)
  LEGACY    if it has < 8 markers (pre-master-template shape)

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_template_coverage_audit.py
"""
from __future__ import annotations

import asyncio
import os
import re

import httpx

FRONTEND = os.getenv("FRONTEND_URL", "http://127.0.0.1:3001")

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"
BOLD = "\033[1m"; NC = "\033[0m"; DIM = "\033[2m"


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# Every deep-dive route + the topic slugs it should expose.
# The slug list is the discoverable surface — each slug is the
# id="..." anchor on the rendered <article>.
DEEP_DIVE_ROUTES: list[tuple[str, list[str]]] = [
    ("/admin/database/deep", [
        "postgres-rls", "qdrant", "redis", "kafka", "clickhouse", "object-storage",
    ]),
    ("/admin/mcp/deep", [
        # Slugs discovered at runtime — see step 1.
    ]),
    ("/admin/breakers/deep", [
        "generic-cb", "transport-cb",
    ]),
    ("/admin/rag/deep", [
        "chunking", "hybrid-retrieval",
    ]),
    ("/admin/microservices/deep", [
        "service-boundaries", "rest-vs-grpc-vs-mcp",
    ]),
    ("/admin/data/deep", [
        # Discovered at runtime.
    ]),
    # Hand-rolled renderers — predate UniversalDeepDive. The audit
    # walks them too. They will all show as LEGACY (0/29 §N. markers)
    # until the page migrates to UniversalDeepDive. That's the
    # honest signal: not "passing" because of the legacy shape.
    ("/admin/python/deep", [
        "async-await", "decorators", "context-managers", "exceptions",
        "typing-pydantic", "iterators-generators", "gil-concurrency-models",
        "classes-inheritance-mro", "fastapi-middleware",
    ]),
    ("/admin/llmops/deep", [
        # Discovered at runtime.
    ]),
]

# The master-template markers we look for inside each topic block.
SECTION_MARKERS = [
    "§1.", "§2.", "§3.", "§4.", "§5.", "§6.", "§7.",
    "§8.", "§9.", "§10.", "§11.", "§12.", "§13.", "§14.",
    "§17.", "§18.", "§19.", "§20.", "§21.", "§22.", "§23.",
    "§24.", "§30.", "§31.", "§32.", "§33.", "§34.", "§35.", "§36.",
]
TOTAL_MARKERS = len(SECTION_MARKERS)
THRESHOLD_MIGRATED = 27  # ≥ 27 / 29 ⇒ MIGRATED (full template)
THRESHOLD_PARTIAL = 8    # ≥ 8 / 29 ⇒ PARTIAL


def grade(count: int) -> tuple[str, str]:
    if count >= THRESHOLD_MIGRATED:
        return ("MIGRATED", GREEN)
    if count >= THRESHOLD_PARTIAL:
        return ("PARTIAL ", YELLOW)
    return ("LEGACY  ", RED)


def discover_topic_slugs(html: str) -> list[str]:
    # Match every <article id="..."> in the rendered page.
    return re.findall(r'<article[^>]*\sid="([^"]+)"', html)


def slice_topic_block(html: str, slug: str) -> str:
    # Best-effort: take from <article id="slug" ... > to the next
    # <article id="..." or end of body. Counts will be approximate
    # but consistent.
    open_re = re.compile(rf'<article[^>]*\sid="{re.escape(slug)}"[^>]*>')
    m = open_re.search(html)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r'<article[^>]*\sid="', html[m.end():])
    end = m.end() + nxt.start() if nxt else len(html)
    return html[start:end]


async def main() -> None:
    overall_topics = 0
    overall_migrated = 0
    overall_partial = 0
    overall_legacy = 0

    async with httpx.AsyncClient(timeout=15.0) as c:
        for route, hinted_slugs in DEEP_DIVE_ROUTES:
            step(f"audit {route}")
            r = await c.get(f"{FRONTEND}{route}")
            if r.status_code != 200:
                print(f"  {RED}✗ {route} returned {r.status_code} — skipping{NC}")
                continue
            html = r.text
            slugs = discover_topic_slugs(html)
            # Merge hinted + discovered to catch known slugs even if
            # the regex misses them (e.g., id rendered out of order).
            seen = set(slugs)
            for s in hinted_slugs:
                if s not in seen:
                    slugs.append(s)
                    seen.add(s)

            if not slugs:
                print(f"  {YELLOW}⚠ no <article id> found on {route}{NC}")
                continue

            # Per-route table.
            print(f"  {BOLD}{'topic':<28}{'count':>8}  status{NC}")
            for slug in slugs:
                block = slice_topic_block(html, slug)
                if not block:
                    # Topic anchor missing entirely — count as LEGACY 0.
                    count = 0
                else:
                    count = sum(1 for m in SECTION_MARKERS if m in block)
                label, color = grade(count)
                print(
                    f"  {color}{slug:<28}{count:>3}/{TOTAL_MARKERS}  "
                    f"{label}{NC}"
                )
                overall_topics += 1
                if label.strip() == "MIGRATED":
                    overall_migrated += 1
                elif label.strip() == "PARTIAL":
                    overall_partial += 1
                else:
                    overall_legacy += 1

        # Roll-up
        step("roll-up")
        if overall_topics == 0:
            print(f"  {RED}✗ no topics discovered across any deep-dive route{NC}")
        else:
            mp = (overall_migrated * 100) // overall_topics
            pp = (overall_partial * 100) // overall_topics
            lp = (overall_legacy * 100) // overall_topics
            print(
                f"  total={overall_topics}  "
                f"{GREEN}MIGRATED={overall_migrated} ({mp}%){NC}  "
                f"{YELLOW}PARTIAL={overall_partial} ({pp}%){NC}  "
                f"{RED}LEGACY={overall_legacy} ({lp}%){NC}"
            )
            if overall_legacy + overall_partial > 0:
                print(
                    f"\n  {DIM}Next loop iteration: pick a LEGACY or PARTIAL "
                    f"topic and migrate it to the master template.{NC}"
                )

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  TEMPLATE COVERAGE AUDIT COMPLETE{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
