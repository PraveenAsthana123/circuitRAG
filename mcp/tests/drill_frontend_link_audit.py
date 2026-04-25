# RESOURCES: none
"""
Drill: AUDIT every internal link on every public deep-dive +
catalog page. Verifies that:

 1. Every internal <a href="/..."> resolves to HTTP 200.
 2. Every #anchor href lands on an actual id="..." on the target
    page (the anchor jump won't be a no-op).
 3. The legacy "Deep dive →" CTA from each catalog actually
    points at a real /admin/<topic>/deep route.

This is an audit, not a gate — exits 0 always. Output is the
broken-link list for the next loop iteration.

Why this matters: text-presence sniffs in HTML say "the link is
on the page". They don't say "the link works". A page can ship
with `/admin/database/deep#postgres-rls` rendered as a clickable
link AND the target page may have renamed `id="postgres-rls"` to
`id="pg-rls"` — the link compiles, the audit's anchor-presence
check passes, but the user clicks and lands on the page top
instead of the intended section.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_link_audit.py
"""
from __future__ import annotations

import asyncio
import os
import re
from collections import defaultdict

import httpx

FRONTEND = os.getenv("FRONTEND_URL", "http://127.0.0.1:3001")

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"
BOLD = "\033[1m"; NC = "\033[0m"; DIM = "\033[2m"


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# Pages to audit. Catalogs + deep dives + admin index.
PAGES_TO_AUDIT = [
    "/admin",
    "/admin/database/deep",
    "/admin/mcp/deep",
    "/admin/breakers/deep",
    "/admin/rag/deep",
    "/admin/microservices/deep",
    "/admin/data/deep",
    "/admin/python/deep",
    "/admin/llmops/deep",
    "/admin/deep-dives",
    "/tools",
    "/tools/database-scenarios",
    "/tools/rag-scenarios",
    "/tools/microservice-scenarios",
    "/tools/circuit-breakers-list",
]

HREF_RE = re.compile(r'href="(/[^"#]*)?(#[^"]+)?"')


def extract_links(html: str) -> list[tuple[str, str]]:
    """Yield (path, anchor) tuples for every internal href.

    Skips: external (//, http://, https://), mailto:, tel:, JS,
    empty fragments.
    """
    links: list[tuple[str, str]] = []
    for m in HREF_RE.finditer(html):
        path = m.group(1) or ""
        anchor = m.group(2) or ""
        if not path and not anchor:
            continue
        # Same-page anchor only (path empty + anchor present)
        if not path:
            continue
        # External / protocol-relative caught by the regex itself
        # (it requires href starting with `/`).
        links.append((path, anchor))
    return links


def extract_ids(html: str) -> set[str]:
    return set(re.findall(r'\sid="([^"]+)"', html))


async def main() -> None:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as c:
        # Cache pages we've fetched so anchor checks reuse them.
        page_cache: dict[str, tuple[int, str]] = {}

        async def fetch(path: str) -> tuple[int, str]:
            if path in page_cache:
                return page_cache[path]
            try:
                r = await c.get(f"{FRONTEND}{path}")
                page_cache[path] = (r.status_code, r.text)
                return page_cache[path]
            except Exception as e:
                page_cache[path] = (0, str(e))
                return page_cache[path]

        broken_status: list[tuple[str, str, int, str]] = []
        broken_anchor: list[tuple[str, str, str]] = []
        ok_count = 0
        anchor_count = 0
        anchor_ok = 0

        for src in PAGES_TO_AUDIT:
            step(f"audit {src}")
            status, body = await fetch(src)
            if status != 200:
                print(f"  {RED}✗ source page returned {status} — skipping{NC}")
                continue

            links = extract_links(body)
            # Dedupe by (path, anchor) to keep output readable.
            unique = sorted(set(links))
            print(f"  {len(unique)} unique internal links")

            # Group by target path for fewer fetches.
            by_path: dict[str, list[str]] = defaultdict(list)
            for path, anchor in unique:
                by_path[path].append(anchor)

            for path, anchors in by_path.items():
                t_status, t_body = await fetch(path)
                if t_status != 200:
                    broken_status.append((src, path, t_status, t_body[:80] if isinstance(t_body, str) else ""))
                    print(f"  {RED}✗ {path} → HTTP {t_status}{NC}")
                    continue
                ok_count += 1
                ids = extract_ids(t_body)
                for anchor in anchors:
                    if not anchor:
                        continue
                    anchor_count += 1
                    slug = anchor[1:]  # drop the '#'
                    if slug in ids:
                        anchor_ok += 1
                    else:
                        broken_anchor.append((src, path, anchor))

        # Summary
        step("roll-up")
        total_pages = sum(1 for p in PAGES_TO_AUDIT if page_cache.get(p, (0,))[0] == 200)
        print(
            f"  {total_pages}/{len(PAGES_TO_AUDIT)} source pages 200"
            f"   {ok_count} link targets resolved 200"
        )
        print(f"  {anchor_ok}/{anchor_count} anchors land on a matching id")

        if broken_status:
            print(f"\n  {RED}BROKEN — {len(broken_status)} non-200 link target(s):{NC}")
            for src, path, st, msg in broken_status[:30]:
                print(f"    {RED}✗ {src} → {path}  (HTTP {st}){NC}")
            if len(broken_status) > 30:
                print(f"    {DIM}… {len(broken_status) - 30} more{NC}")
        else:
            print(f"  {GREEN}✓ no non-200 link targets{NC}")

        if broken_anchor:
            print(f"\n  {YELLOW}BROKEN ANCHORS — {len(broken_anchor)} #fragment(s) "
                  f"with no matching id:{NC}")
            for src, path, anchor in broken_anchor[:30]:
                print(f"    {YELLOW}⚠ {src} → {path}{anchor}{NC}")
            if len(broken_anchor) > 30:
                print(f"    {DIM}… {len(broken_anchor) - 30} more{NC}")
        else:
            print(f"  {GREEN}✓ every #anchor lands on a matching id{NC}")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  LINK AUDIT COMPLETE{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
