#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: vectorless strategy dispatch in HybridRetriever (per §43 + §57.7).

Locks the smallest-meaningful-change Stage-1 wire:
  - RetrieveRequest.strategy field accepts 'vectorless' as a value
  - Schema docstring lists vectorless alongside vector/graph/hybrid
  - HybridRetriever recognizes strategy='vectorless' and SUPPRESSES
    both vector + graph backends (so Stage-2 ES search can plug in
    without competing with vector/graph)
  - Stage-2 path is documented (don't promise what's not shipped per
    §57.7 — vectorless returns degraded empty chunks today; ES wire
    lands separately)
  - Compose footer references the existing /admin/vectorless-
    elasticsearch admin page (per §49)
  - No regression on vector / graph / hybrid strategies

Eight steps. Five negative.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "services" / "retrieval-svc" / "app" / "schemas" / "__init__.py"
RETRIEVER = (
    REPO
    / "services"
    / "retrieval-svc"
    / "app"
    / "services"
    / "hybrid_retriever.py"
)
ADMIN_PAGE = (
    REPO
    / "services"
    / "frontend"
    / "app"
    / "admin"
    / "vectorless-elasticsearch"
    / "page.tsx"
)


GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    if not SCHEMAS.exists() or not RETRIEVER.exists():
        fail(f"missing source files; SCHEMAS={SCHEMAS.exists()} RETRIEVER={RETRIEVER.exists()}")
    schemas_src = SCHEMAS.read_text(encoding="utf-8")
    retriever_src = RETRIEVER.read_text(encoding="utf-8")

    # ── 1. schema docstring lists vectorless ──────────────────────────
    step("1. POSITIVE: RetrieveRequest.strategy docstring includes 'vectorless'")
    # Find the strategy Field and ensure 'vectorless' appears in its
    # description string.
    field_match = re.search(
        r"strategy:\s*str\s*=\s*Field\([^)]*?description=\s*\(([^)]*)\)",
        schemas_src,
        re.DOTALL,
    )
    if not field_match:
        # Fallback: simpler form
        field_match = re.search(
            r"strategy:\s*str\s*=\s*Field\([^)]*description=\"([^\"]*)\"",
            schemas_src,
            re.DOTALL,
        )
    if not field_match:
        fail("cannot locate RetrieveRequest.strategy Field with description")
    description = field_match.group(1)
    if "vectorless" not in description:
        fail(
            "strategy field description does NOT include 'vectorless' — "
            "schema must advertise the new strategy publicly"
        )
    ok("schema description includes vectorless")

    # ── 2. legacy strategies still listed (no regression) ─────────────
    step("2. NEGATIVE: legacy strategies still in description (no regression)")
    for legacy in ("vector", "graph", "hybrid"):
        if legacy not in description:
            fail(
                f"strategy description dropped legacy value '{legacy}' — "
                "regression"
            )
    ok("vector + graph + hybrid all still present")

    # ── 3. retriever recognizes is_vectorless ─────────────────────────
    step("3. POSITIVE: HybridRetriever recognizes is_vectorless")
    if "is_vectorless" not in retriever_src:
        fail(
            "HybridRetriever doesn't have an is_vectorless variable — "
            "dispatch can't gate on it"
        )
    if 'request.strategy == "vectorless"' not in retriever_src:
        fail(
            "HybridRetriever doesn't compute is_vectorless from "
            "request.strategy == 'vectorless'"
        )
    ok("is_vectorless = (request.strategy == 'vectorless') present")

    # ── 4. NEGATIVE: vectorless suppresses vector branch ──────────────
    step("4. NEGATIVE: vectorless suppresses the vector branch")
    # The vector eligibility check must include `not is_vectorless`
    vector_block_match = re.search(
        r'"vector"\s+in\s+request\.include_sources.*?coros\.append\(self\._do_vector',
        retriever_src,
        re.DOTALL,
    )
    if not vector_block_match:
        fail("cannot locate vector dispatch block")
    vector_block = vector_block_match.group(0)
    if "not is_vectorless" not in vector_block:
        fail(
            "vector dispatch block does NOT exclude is_vectorless — "
            "vectorless would silently fall back to vector retrieval"
        )
    ok("vector branch excluded when strategy='vectorless'")

    # ── 5. NEGATIVE: vectorless suppresses graph branch ───────────────
    step("5. NEGATIVE: vectorless suppresses the graph branch")
    graph_block_match = re.search(
        r'"graph"\s+in\s+request\.include_sources.*?coros\.append\(self\._do_graph',
        retriever_src,
        re.DOTALL,
    )
    if not graph_block_match:
        fail("cannot locate graph dispatch block")
    graph_block = graph_block_match.group(0)
    if "not is_vectorless" not in graph_block:
        fail(
            "graph dispatch block does NOT exclude is_vectorless — "
            "vectorless would silently fall back to graph retrieval"
        )
    ok("graph branch excluded when strategy='vectorless'")

    # ── 6. NEGATIVE: §57.7 honesty — Stage-2 marker present ───────────
    step(
        "6. NEGATIVE: dispatch comment marks Stage-2 wire as PENDING "
        "(don't claim ES search is shipped)"
    )
    # The dispatch comment block must mention 'Stage-2' OR 'pending' OR
    # 'wire' — anything that signals the ES call isn't actually wired.
    dispatch_comment_match = re.search(
        r"strategy='vectorless'.*?Stage-1.*?Stage-2",
        retriever_src,
        re.DOTALL,
    )
    if not dispatch_comment_match:
        fail(
            "vectorless dispatch comment must reference both Stage-1 "
            "(returns empty) and Stage-2 (ES wire pending) per §57.7"
        )
    ok("Stage-1 + Stage-2 markers both present in dispatch comment")

    # ── 7. NEGATIVE: docstring cites the admin page (compose footer) ──
    step(
        "7. NEGATIVE: schema description references the admin page "
        "(compose-footer per §49)"
    )
    # Find the strategy field block — between "strategy:" and the next
    # field declaration. Substring check is robust against multi-line
    # parenthesized descriptions where regex paren-balancing is tricky.
    strategy_block_match = re.search(
        r"strategy:\s*str.*?\n\s*(?=\w+\s*:\s*\w|class\s)",
        schemas_src,
        re.DOTALL,
    )
    if not strategy_block_match:
        # Fallback: look at first 1500 chars after "strategy:"
        idx = schemas_src.find("strategy:")
        strategy_block = schemas_src[idx : idx + 1500] if idx >= 0 else ""
    else:
        strategy_block = strategy_block_match.group(0)
    if "/admin/vectorless-elasticsearch" not in strategy_block:
        fail(
            "schema description does NOT reference /admin/vectorless-"
            "elasticsearch — compose-footer broken for this strategy"
        )
    ok("schema description cites /admin/vectorless-elasticsearch")

    # ── 8. POSITIVE: admin page exists (the page this schema points at) ──
    step("8. POSITIVE: /admin/vectorless-elasticsearch page exists")
    if not ADMIN_PAGE.exists():
        fail(
            f"admin page missing: {ADMIN_PAGE.relative_to(REPO)} — "
            "schema description claims it as compose-footer target"
        )
    ok(f"admin page present ({ADMIN_PAGE.stat().st_size}b)")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
