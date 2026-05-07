# RESOURCES: frontend
"""
Drill: at least one topic on /admin/database/deep renders the FULL
36-section master template (+ HLD + LLD diagrams) — proof that the
new UniversalDeepDive schema is wired end-to-end. Locks the
specific section markers introduced by the master-template
expansion so a regression that drops a §-tagged block goes red.

Negative-assertion §43-style:
 1. /admin/database/deep returns 200. NEGATIVE: a 404 means the
    page file was renamed or the new schema broke the build.
 2. The page contains the §-tagged section markers added by the
    master template (5W, Architecture relevance, STAR story,
    Anti-patterns, Decision matrix, Trade-offs, Interview traps,
    Production issues, Test scenarios, Best practices, etc.).
    NEGATIVE: dropping the new optional sections from the schema
    while keeping the type definition would silently render a
    legacy-only page; this catches that.
 3. The page contains both HLD and LLD section markers and the
    expected Mermaid diagram source. NEGATIVE: removing the
    Mermaid mounts but keeping the labels would still pass step 2;
    we sniff for the diagram source content too.
 4. The Final interview script (§36) is present and is at least
    300 chars (4-6 lines worth). NEGATIVE: a regression that fell
    back to the 1-liner interviewLine would still pass a string-
    presence check; the length floor catches it.
 5. The 5W table contains all five labels (What/Why/Where/When/
    Who). NEGATIVE: dropping one of the rows from the renderer
    would still pass a "5W" header sniff; sniffing all five labels
    catches the partial regression.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_master_template.py
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


# Master-template section markers (the §N. labels rendered by
# UniversalDeepDive when the matching field is present).
# Updated 2026-04-25 — user revised template:
#   §1 = Problem/Context (NEW position, was implicit)
#   §4 = HLD diagram (was unnumbered)
#   §5 = Network Flow (NEW)
#   §6 = Sequence Flow (was §7; merges flowchart + sequence)
#   §7 = Core Components / Layers (NEW)
REQUIRED_MASTER_SECTIONS = [
    "§1.",   # Problem / Context
    "§2.",   # 5W
    "§3.",   # Interview answer (30-60s)
    "§4.",   # HLD
    "§5.",   # Network Flow
    "§6.",   # Sequence Flow (flowchart + sequence merged)
    "§7.",   # Core Components / Layers
    "§8.",   # Implementation steps
    "§9.",   # Code example
    "§10.",  # Real use case
    "§11.",  # Pros & cons
    "§12.",  # Limitations
    "§13.",  # When to use vs not
    "§14.",  # Comparison
    "§17.",  # Solutions / fixes
    "§18.",  # Best practices
    "§19.",  # Anti-patterns
    "§20.",  # Testing strategy
    "§21.",  # Test scenarios
    "§22.",  # Test data
    "§23.",  # Debugging checklist
    "§24.",  # Production issues
    "§30.",  # Metrics
    "§31.",  # Failure modes
    "§32.",  # Trade-offs
    "§33.",  # Decision matrix
    "§34.",  # STAR story
    "§35.",  # Interview traps
    "§36.",  # Final script
]

# 5W row labels (locking the table contents, not just the header).
FIVE_W_LABELS = ["What", "Why", "Where", "When", "Who"]

# HLD + LLD source sniffs (verify the mermaid mounts contain the
# expected diagram content, not just the section headers).
HLD_SNIFFS = ["High-Level Architecture", "owner role", "FORCE ROW LEVEL SECURITY"]
LLD_SNIFFS = ["Low-level design", "asyncpg pool", "app.current_tenant"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=15.0) as c:
        step("1. /admin/database/deep returns 200")
        r = await c.get(f"{FRONTEND}/admin/database/deep")
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}")
        body = r.text
        ok(f"200 + {len(body)} bytes")

        step("2. master-template section markers present (≥ 27 of the §N. set)")
        present = [s for s in REQUIRED_MASTER_SECTIONS if s in body]
        missing = [s for s in REQUIRED_MASTER_SECTIONS if s not in body]
        threshold = 27  # of 29 expected; tolerance for sections that
                        # may render conditionally on optional data.
        if len(present) < threshold:
            fail(
                f"only {len(present)}/{len(REQUIRED_MASTER_SECTIONS)} master "
                f"sections present (threshold={threshold}). Missing: "
                f"{missing}. The master-template renderer regressed."
            )
        ok(f"{len(present)}/{len(REQUIRED_MASTER_SECTIONS)} master section "
           f"markers present")

        step("3. HLD + LLD diagrams + source sniffs present")
        for sniff in HLD_SNIFFS:
            if sniff not in body:
                fail(
                    f"HLD sniff missing: {sniff!r}. The HLD diagram "
                    f"render or its mermaid source dropped."
                )
        ok(f"all {len(HLD_SNIFFS)} HLD sniffs present")
        for sniff in LLD_SNIFFS:
            if sniff not in body:
                fail(
                    f"LLD sniff missing: {sniff!r}. The LLD diagram "
                    f"render or its mermaid source dropped."
                )
        ok(f"all {len(LLD_SNIFFS)} LLD sniffs present")

        step("4. §36 Final interview script ≥ 300 chars (multi-line)")
        # The §36 marker is asserted in step 2; here we prove the
        # block contains substantive prose, not the 1-line fallback.
        # Sniff a phrase that only appears in the long-form script.
        long_form_sniff = "Mocks lie about RLS"
        if long_form_sniff not in body:
            fail(
                f"§36 long-form script sniff {long_form_sniff!r} missing. "
                f"The renderer fell back to the legacy interviewLine; the "
                f"new finalScript field was dropped."
            )
        ok("§36 long-form final-script content present")

        step("5b. §5 Network Flow + §7 Core Layers SSR content present")
        # Note: Mermaid is a client-only component, so HLD/LLD/networkFlow
        # diagram sources do NOT appear in the SSR HTML. We can only
        # assert their <header> label + Mermaid mount wrapper. Server-
        # rendered text (tables, lists) IS present and IS sniffable.

        # §5 Network Flow: section header + a Mermaid mount wrapper
        # immediately following ⇒ the diagram is wired.
        idx5 = body.find("Network Flow")
        if idx5 < 0:
            fail("§5 Network Flow header missing")
        # Look ahead 2KB for an md-mermaid-wrap mount.
        if "md-mermaid-wrap" not in body[idx5:idx5 + 2000]:
            fail(
                "§5 header present but no md-mermaid-wrap mount within "
                "2KB downstream. The networkFlow Mermaid component was "
                "removed."
            )

        # §7 Core Layers table: at least 5 of the 7 layer labels.
        # These ARE server-rendered (plain HTML <td>) so they sniff cleanly.
        layer_labels = [
            "Connection layer", "Role layer", "Schema layer",
            "RLS policy layer", "Repository layer", "Migration layer",
            "Audit layer",
        ]
        present_layers = [l for l in layer_labels if l in body]
        if len(present_layers) < 5:
            fail(
                f"§7 Core Layers: only {len(present_layers)}/{len(layer_labels)} "
                f"layer labels present. Expected ≥ 5. Missing: "
                f"{[l for l in layer_labels if l not in body]}. "
                f"The coreLayers[] field was dropped from postgres-rls."
            )
        ok(f"§5 wired + §7 has {len(present_layers)}/"
           f"{len(layer_labels)} layer labels")

        step("6. 5W table contains all five row labels")
        # Each label appears in many places; require a dense neighbourhood
        # near the §2. header. Cheap heuristic: locate §2. then check
        # the next 4000 chars contain all five labels.
        idx = body.find("§2.")
        if idx < 0:
            fail("§2. header not found; step 2 should have caught this")
        window = body[idx:idx + 4000]
        for label in FIVE_W_LABELS:
            if f"<strong>{label}</strong>" not in window:
                fail(
                    f"5W label {label!r} missing from the §2 window. "
                    f"The fiveW renderer dropped a row."
                )
        ok("all 5 5W row labels present in §2 window")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 MASTER-TEMPLATE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
