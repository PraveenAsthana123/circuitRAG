#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: /admin/mcp/deep page covers six topics — server, client,
feature surface, architecture, every component, end-to-end flow.

The page is the operator's interview-grade reference for the entire
MCP layer. Two original topics (mcp-server, mcp-client) covered the
two main pieces of code; four new topics (mcp-feature, mcp-architect,
mcp-components, mcp-flow) added the framing operators actually ask
for: "what does it give me", "where does it sit", "what are the
files", "what happens on a single call". Without those four, the
page is half a reference.

Negative assertions lock the contract:
  1. POSITIVE: page exists at the canonical path.
  2. NEGATIVE: TOPICS array contains all six required slugs (the
     two originals and the four new). Future additions are fine;
     subtraction breaks the page.
  3. NEGATIVE: each required topic has a non-empty title containing
     a leading section number (matches the page's enumeration
     pattern). A bare title without a number means the page lost
     its operator-scannable structure.
  4. NEGATIVE: each required topic has a non-empty coreConcept AND
     a non-empty interviewLine. Without those two fields the
     UniversalDeepDive renderer drops the §1 hook + final pitch —
     the topic becomes prose with no entry/exit point.
  5. NEGATIVE: page imports UniversalDeepDive AND DeepDiveCrossRefs.
     The cross-refs footer is the §49 compose-with contract; the
     UniversalDeepDive component is the rendering contract. Either
     missing means the page silently regresses.
  6. NEGATIVE: no TODO / FIXME / PLACEHOLDER / TBD markers anywhere
     in the new topics' bodies. Half-finished prose is worse than
     no prose for an interview reference.
  7. POSITIVE: subtitle text mentions the four new framing words
     (feature, architecture, component, flow). Page header lying
     about coverage is the regression we lock against.

Run: python3 mcp/tests/drill_mcp_deep_page_topics.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "mcp" / "deep" / "page.tsx"

REQUIRED_SLUGS = (
    "mcp-server",       # original — server-internal detail
    "mcp-client",       # original — client-internal detail
    "mcp-feature",      # new — what MCP gives operators (six guarantees)
    "mcp-architect",    # new — architectural placement
    "mcp-components",   # new — every file in mcp/
    "mcp-flow",         # new — 11-step end-to-end request flow
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _topic_block(body: str, slug: str) -> str:
    """Return the source slice of one Topic object, by slug.

    The TOPICS array uses object literals separated by `},`. We find
    the slug declaration, then walk forward to the matching closing
    brace. Brace-counting handles nested braces from inline mermaid
    blocks (which do not contain TS object braces, only fenced
    strings).
    """
    needle = f"slug: '{slug}'"
    idx = body.find(needle)
    if idx < 0:
        return ""
    # Walk back to the opening "{" of this object.
    open_idx = body.rfind("{", 0, idx)
    if open_idx < 0:
        return ""
    # Walk forward counting braces, but skip braces inside backtick
    # template literals (mermaid bodies use ${}-style template
    # interpolation occasionally; safer to treat backtick-delimited
    # spans as opaque).
    depth = 1
    i = open_idx + 1
    in_backtick = False
    while i < len(body) and depth > 0:
        ch = body[i]
        if ch == "`":
            in_backtick = not in_backtick
        elif not in_backtick:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        i += 1
    return body[open_idx:i]


def main() -> int:
    # ---- Step 1: POSITIVE — page exists ----
    step("1. POSITIVE: /admin/mcp/deep/page.tsx exists")
    if not PAGE.exists():
        fail(f"page missing at {PAGE}")
    body = PAGE.read_text()
    if len(body) < 1000:
        fail(f"page suspiciously short ({len(body)} bytes); expected interview-grade content")
    ok(f"page exists ({len(body):,} bytes)")

    # ---- Step 2: NEGATIVE — every required slug declared ----
    step("2. NEGATIVE: every required topic slug present in TOPICS array")
    missing = [s for s in REQUIRED_SLUGS if f"slug: '{s}'" not in body]
    if missing:
        fail(f"missing required slugs: {missing}")
    ok(f"all {len(REQUIRED_SLUGS)} required slugs declared")

    # ---- Step 3: NEGATIVE — every topic has a numbered title ----
    step("3. NEGATIVE: every required topic has a leading section number")
    title_pattern = re.compile(r"title:\s*'(\d+)\.\s+([^']+)'")
    for slug in REQUIRED_SLUGS:
        block = _topic_block(body, slug)
        if not block:
            fail(f"could not extract block for slug={slug}")
        m = title_pattern.search(block)
        if not m:
            # Fallback: maybe double-quoted
            alt = re.search(r'title:\s*"(\d+)\.\s+([^"]+)"', block)
            if not alt:
                fail(f"slug={slug} has no numbered title (expected 'N. ...')")
    ok(f"all {len(REQUIRED_SLUGS)} topics have numbered titles")

    # ---- Step 4: NEGATIVE — coreConcept + interviewLine non-empty ----
    step("4. NEGATIVE: every required topic has non-empty coreConcept AND interviewLine")
    for slug in REQUIRED_SLUGS:
        block = _topic_block(body, slug)
        for field in ("coreConcept", "interviewLine"):
            # Match `field: '...content...'` or `field: "...content..."`
            # allowing backslash-escapes inside (so `project\'s` doesn't
            # prematurely close the quote). Capture group is the body.
            pat = re.compile(
                rf"{field}:\s*"
                r"(?:'((?:\\.|[^'\\])*)'"
                r"|\"((?:\\.|[^\"\\])*)\")",
                re.DOTALL,
            )
            m = pat.search(block)
            if not m:
                fail(f"slug={slug} field={field} not found at all")
            content = m.group(1) or m.group(2) or ""
            if len(content.strip()) < 20:
                fail(
                    f"slug={slug} field={field} too short "
                    f"({len(content)} chars; need >= 20). "
                    "Both fields are mandatory for §1 hook + final pitch."
                )
    ok(f"all {len(REQUIRED_SLUGS)} topics have substantive coreConcept + interviewLine")

    # ---- Step 5: NEGATIVE — required imports present ----
    step("5. NEGATIVE: page imports UniversalDeepDive AND DeepDiveCrossRefs")
    if "import UniversalDeepDive" not in body:
        fail("missing import: UniversalDeepDive (rendering contract broken)")
    if "import DeepDiveCrossRefs" not in body:
        fail("missing import: DeepDiveCrossRefs (§49 compose-footer contract broken)")
    if "<DeepDiveCrossRefs" not in body:
        fail("DeepDiveCrossRefs imported but not rendered — footer ships dead code")
    ok("rendering + compose-footer contracts both wired")

    # ---- Step 6: NEGATIVE — no half-finished markers in new topics ----
    step("6. NEGATIVE: no TODO/FIXME/PLACEHOLDER/TBD in new topic bodies")
    new_slugs = ("mcp-feature", "mcp-architect", "mcp-components", "mcp-flow")
    bad_markers = ("TODO", "FIXME", "PLACEHOLDER", "TBD", "XXX")
    offenders: list[tuple[str, str]] = []
    for slug in new_slugs:
        block = _topic_block(body, slug)
        for marker in bad_markers:
            if marker in block:
                offenders.append((slug, marker))
    if offenders:
        fail(f"half-finished markers found: {offenders}")
    ok(f"all {len(new_slugs)} new topics ship clean prose (no half-finished markers)")

    # ---- Step 7: POSITIVE — subtitle reflects new framing ----
    step("7. POSITIVE: page subtitle mentions feature + architecture + component + flow")
    # Match the page-subtitle block; case-insensitive on framing words
    subtitle_match = re.search(
        r'<p className="page-subtitle">(.+?)</p>',
        body, re.DOTALL,
    )
    if not subtitle_match:
        fail("could not find page-subtitle block")
    subtitle = subtitle_match.group(1).lower()
    required_words = ("feature", "architect", "component", "flow")
    missing_words = [w for w in required_words if w not in subtitle]
    if missing_words:
        fail(
            f"subtitle missing framing words: {missing_words}. "
            "Subtitle must declare what the page covers; lying about "
            "coverage is the regression we lock against."
        )
    ok(f"subtitle mentions all 4 framing words: {list(required_words)}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 MCP-DEEP-PAGE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 3, 4, 5, 6){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
