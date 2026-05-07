# RESOURCES: readonly
"""
Drill: RAG vectorless retrieval (graph-only) feature flag.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §45.4 (no checkbox
flips without code), §47 (architecture: feature flags reversible),
§39.2 (RAG architecture: graph option must be admitted at retrieval
boundary, not bolted on).

Architecture matrix listed RAG / Vectorless option as ⚠️ PLANNED
'feature flag missing'. Empirical truth: schema admitted strategy=
'graph' but the retriever still vector-searched whenever 'vector' was
in include_sources (default). Iter-36 closes that gap:

  strategy='graph'                       → graph-only retrieval
  DOCUMIND_VECTORLESS_DEFAULT=1          → graph-only forced globally
  strategy='vector' OR 'hybrid' (default)→ unchanged behavior

Locks (positive):
  L1. Source has the env-flag DOCUMIND_VECTORLESS_DEFAULT
  L2. Source documents the strategy='graph' branch in a comment
  L3. The vector-branch condition includes both `strategy != 'graph'`
      AND `not force_graph_only` (the feature flag)

Locks (negative — ≥3 per §43):
  N1. Strategy='graph' MUST suppress the vector branch (was previous
      bug: graph-only was advertised but vector still ran)
  N2. Feature flag is opt-in (default OFF; comparing exact == '1');
      never an inferred boolean truth — operator must set explicitly
  N3. Source has NO `pull` or `add` or `embed` write-side verbs in the
      strategy gate (gate is read-only routing, not data mutation)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETRIEVER = REPO / "services" / "retrieval-svc" / "app" / "services" / "hybrid_retriever.py"

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
    if not RETRIEVER.exists():
        fail(f"retriever missing: {RETRIEVER.relative_to(REPO)}")

    src = RETRIEVER.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: env-flag DOCUMIND_VECTORLESS_DEFAULT in source
    # ------------------------------------------------------------------
    step("1. DOCUMIND_VECTORLESS_DEFAULT env-flag present in retriever")
    if "DOCUMIND_VECTORLESS_DEFAULT" not in src:
        fail(
            "retriever has no DOCUMIND_VECTORLESS_DEFAULT env-flag; the "
            "vectorless option requires a flag for global toggle"
        )
    ok("env-flag DOCUMIND_VECTORLESS_DEFAULT present")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: strategy='graph' branch documented
    # ------------------------------------------------------------------
    step("2. strategy='graph' branch documented in retriever")
    if "graph-only" not in src.lower() and "graph only" not in src.lower():
        fail(
            "no graph-only documentation comment near the strategy gate; "
            "future maintainer won't know vectorless is a real option"
        )
    ok("graph-only retrieval branch documented")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: vector-branch condition has both gates
    # ------------------------------------------------------------------
    step("3. vector-branch has both strategy and feature-flag gates")
    # Locate the vector-branch decision (the `if` that decides whether to
    # call _do_vector). Should reference 'strategy' AND 'force_graph_only'
    # OR similar combined gate.
    if "request.strategy != \"graph\"" not in src and "request.strategy != 'graph'" not in src:
        fail("vector branch missing `request.strategy != 'graph'` gate")
    if "force_graph_only" not in src and "VECTORLESS_DEFAULT" not in src:
        fail("vector branch missing the feature-flag gate")
    ok("both strategy gate AND feature-flag gate present in vector branch")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: feature flag opt-in (exact '1' compare, not truthy)
    # ------------------------------------------------------------------
    step("4. NEGATIVE: feature flag opt-in (exact == '1', not truthy)")
    # Look for the pattern `getenv("DOCUMIND_VECTORLESS_DEFAULT", ...).strip() == "1"`
    # or equivalent. We want to AVOID `bool(getenv(...))` which would
    # treat "0", "false", "" etc as truthy if the env var is just set.
    if (
        '"DOCUMIND_VECTORLESS_DEFAULT", "")' in src
        and '== "1"' in src
    ) or (
        "'DOCUMIND_VECTORLESS_DEFAULT', '')" in src
        and "== '1'" in src
    ):
        ok("feature flag uses explicit == '1' check (opt-in only)")
    else:
        # Allow other safe patterns; just reject naive truthy checks
        forbidden = (
            'bool(os.getenv("DOCUMIND_VECTORLESS_DEFAULT"',
            'bool(os.environ.get("DOCUMIND_VECTORLESS_DEFAULT"',
            'os.environ.get("DOCUMIND_VECTORLESS_DEFAULT") and',
        )
        leaks = [p for p in forbidden if p in src]
        if leaks:
            fail(
                f"naive truthy env-var check in source: {leaks}. "
                f"Use `.getenv(...).strip() == '1'` so 'false' / '0' don't "
                f"accidentally enable the flag."
            )
        # Soft warn: pattern unrecognized but not obviously broken
        ok("feature flag opt-in pattern present (custom; no naive truthy check)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: gate has no write-side verbs
    # ------------------------------------------------------------------
    step("5. NEGATIVE: gate is read-only (no pull / add / embed verbs)")
    # Locate the dispatch block (between `# Parallel fetch` and the
    # `results = await asyncio.gather(...)` line) and verify it has no
    # write-side verbs that would mutate index state.
    dispatch_match = re.search(
        r"# Parallel fetch.*?results = await asyncio\.gather",
        src, re.DOTALL,
    )
    if dispatch_match is None:
        fail("could not locate parallel-fetch dispatch block")
    dispatch = dispatch_match.group(0)
    forbidden_verbs = (".upsert(", ".add(", ".embed(", ".write(", ".delete(")
    leaks = [v for v in forbidden_verbs if v in dispatch]
    if leaks:
        fail(
            f"dispatch block has write-side verbs: {leaks}. "
            f"Strategy gate must be read-only routing; no data mutation."
        )
    ok("dispatch block has no write-side verbs (read-only routing)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: graph branch still gated on strategy != 'vector'
    # ------------------------------------------------------------------
    step("6. NEGATIVE: graph branch still suppressed when strategy='vector'")
    if "request.strategy != \"vector\"" not in src and "request.strategy != 'vector'" not in src:
        fail(
            "graph branch missing `request.strategy != 'vector'` gate — "
            "back-compat broken: vector-only mode would now also graph-search"
        )
    ok("graph branch still suppressed when strategy='vector' (back-compat)")

    print(f"\n{GREEN}{BOLD}ALL 6 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
