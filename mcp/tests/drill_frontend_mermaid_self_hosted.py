# RESOURCES: none
"""
Drill: Mermaid library is served same-origin from /mermaid.min.js,
NOT loaded from a third-party CDN.

Closes the user-reported bug: the circuit-breakers-list page rendered
mermaid sources as raw text instead of SVG diagrams. Root cause was
the Mermaid component loading from cdn.jsdelivr.net, which is blocked
by some networks / corporate proxies / browser ad-blockers — when
blocked, the script never loads and every diagram falls through to
the <pre><code> fallback.

Self-hosting the asset removes the dependency on third-party
networks. Drill locks the assertion so a future "let's go back to
the CDN to save bundle size" refactor goes red instead of silently
breaking diagrams in restrictive environments.

Negative-assertion §43-style:
 1. /mermaid.min.js returns 200 + non-trivial size (~3MB).
    NEGATIVE: a 404 here means the public asset was lost — the
    install step that copies node_modules/mermaid/dist/ to public/
    didn't happen.
 2. Mermaid.tsx source does NOT contain 'cdn.jsdelivr.net' or any
    other third-party CDN host. NEGATIVE: a future "let's pull
    from CDN to save bundle size" change would lock-in the same
    failure mode this fix addresses.
 3. The Mermaid loader uses the same-origin path '/mermaid.min.js'.
    NEGATIVE: a path drift (e.g. '/static/mermaid.js') would 404
    silently — the script tag onerror fires, every diagram falls
    back to source text.
 4. /tools/circuit-breakers-list serves 200 (where the diagrams
    are rendered).

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_mermaid_self_hosted.py
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
FRONTEND = os.getenv("FRONTEND_URL", "http://127.0.0.1:3001")
MERMAID_COMPONENT = REPO / "services" / "frontend" / "components" / "Mermaid.tsx"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as c:
        step("1. /mermaid.min.js returns 200 with substantial size")
        r = await c.get(f"{FRONTEND}/mermaid.min.js")
        if r.status_code != 200:
            fail(
                f"expected 200, got {r.status_code}. The public asset "
                f"is missing — it should be copied from "
                f"node_modules/mermaid/dist/mermaid.min.js to "
                f"services/frontend/public/mermaid.min.js."
            )
        size = len(r.content)
        if size < 500_000:  # mermaid is multi-MB; <500KB means it's the wrong file
            fail(
                f"mermaid.min.js too small ({size} bytes). Expected ~3MB; "
                f"a small file usually means a 404 HTML page or wrong "
                f"asset was served."
            )
        ok(f"served {size:,} bytes")

        step("2. Mermaid.tsx source does NOT reference any third-party CDN")
        if not MERMAID_COMPONENT.is_file():
            fail(f"missing component file: {MERMAID_COMPONENT}")
        text = MERMAID_COMPONENT.read_text()
        # Forbidden: any cdn / unpkg / jsdelivr / googleapis / cloudfront /
        # fastly URL inside the loader path.
        forbidden_patterns = [
            r"https?://cdn\.",
            r"https?://unpkg\.com",
            r"https?://[^/]*jsdelivr",
            r"https?://[^/]*googleapis",
            r"https?://[^/]*cloudfront",
            r"https?://[^/]*fastly",
        ]
        # Strip comments first so docstrings/comments referring to CDNs
        # historically don't trip this. We're checking the live URL the
        # loader uses, which lives outside comments.
        no_block_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        no_line_comments = re.sub(r"^\s*\*.*$|^\s*//.*$", "", no_block_comments, flags=re.MULTILINE)
        for pat in forbidden_patterns:
            m = re.search(pat, no_line_comments)
            if m:
                fail(
                    f"third-party CDN reference {m.group(0)!r} found in "
                    f"Mermaid.tsx executable code. Self-host instead — "
                    f"network-restricted browsers can't reach external "
                    f"CDNs."
                )
        ok("no third-party CDN URLs in Mermaid.tsx executable code")

        step("3. Loader uses same-origin path '/mermaid.min.js'")
        if "/mermaid.min.js" not in text:
            fail(
                f"Mermaid.tsx doesn't reference '/mermaid.min.js' — "
                f"the path may have drifted (e.g. '/static/...' or "
                f"'/_next/...'). Self-hosted assets MUST be at the "
                f"public-folder root path or the script tag 404s."
            )
        ok("loader path is /mermaid.min.js (same-origin)")

        step("4. /tools/circuit-breakers-list (a Mermaid consumer) serves 200")
        r = await c.get(f"{FRONTEND}/tools/circuit-breakers-list")
        if r.status_code != 200:
            fail(f"page returned {r.status_code}")
        body = r.text
        # Sanity: page contains the rendered mermaid mount points.
        # md-mermaid is the wrapper class from Mermaid.tsx.
        if "md-mermaid" not in body:
            fail(
                "page rendered without Mermaid mount points — the "
                "Mermaid component may have been removed."
            )
        ok(f"page 200 + Mermaid mount points present")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 MERMAID-SELF-HOSTED STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
