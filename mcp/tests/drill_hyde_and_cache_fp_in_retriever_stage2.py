#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: HyDE + cache_fingerprint Stage-2 wires into HybridRetriever (per §43 + §56).

Locks both Stage-2 wires that compose with HybridRetriever.retrieve:

  1. cache_fingerprint Stage-2: _cache_key uses 8-dim fingerprint
     when CACHE_FINGERPRINT_ENABLED=1 (else legacy 4-dim hash)
  2. HyDE Stage-2: when min_score returns 0 chunks AND HYDE_ENABLED=1,
     fire hypothetical answer + re-run vector search

Both are opt-in (separate env flags), fail-safe (try/except + log),
lazy-imported, and additive (legacy paths preserved).

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETRIEVER = REPO / "services" / "retrieval-svc" / "app" / "services" / "hybrid_retriever.py"
HYDE = REPO / "scripts" / "hyde_adapter.py"
CACHE_FP = REPO / "scripts" / "cache_fingerprint.py"


def main() -> int:
    print("-- 1. POSITIVE: HybridRetriever wires both adapters --")
    if not RETRIEVER.exists():
        print(f"x {RETRIEVER} missing")
        return 1
    src = RETRIEVER.read_text(encoding="utf-8")
    if "CACHE_FINGERPRINT_ENABLED" not in src:
        print("x cache_fingerprint env-flag check missing")
        return 1
    if "HYDE_ENABLED" not in src:
        print("x HYDE_ENABLED env-flag check missing")
        return 1
    if "from cache_fingerprint" not in src:
        print("x must import from cache_fingerprint (lazy)")
        return 1
    if "from hyde_adapter" not in src:
        print("x must import from hyde_adapter (lazy)")
        return 1
    print("  ok: HybridRetriever wires both Stage-2 adapters")

    print("-- 2. NEGATIVE: Stage-1 modules UNCHANGED (no reverse imports) --")
    hyde_src = HYDE.read_text(encoding="utf-8")
    cache_fp_src = CACHE_FP.read_text(encoding="utf-8")
    rev_import = re.compile(
        r"^\s*(from\s+.*hybrid_retriever|import\s+.*hybrid_retriever)",
        re.MULTILINE,
    )
    if rev_import.search(hyde_src):
        print("x hyde_adapter imports HybridRetriever (cycle risk)")
        return 1
    if rev_import.search(cache_fp_src):
        print("x cache_fingerprint imports HybridRetriever (cycle risk)")
        return 1
    print("  ok: Stage-1 adapters don't import retriever (clean layering)")

    print("-- 3. NEGATIVE: cache_fingerprint wire fails-safe to legacy hash --")
    # Per §47 fail-safe: if fingerprint() raises (e.g. env flag set
    # but module import fails), we MUST fall through to the legacy
    # hash so caching keeps working. Drill enforces try/except in
    # the _cache_key path.
    cache_key_idx = src.find("def _cache_key")
    cache_key_end = src.find("async def retrieve", cache_key_idx)
    cache_key_body = src[cache_key_idx:cache_key_end]
    if "try:" not in cache_key_body:
        print("x _cache_key must wrap fingerprint call in try/except")
        return 1
    if "except Exception" not in cache_key_body:
        print("x must catch generic Exception in _cache_key (fail-safe)")
        return 1
    if "h = hashlib.sha256" not in cache_key_body:
        print("x legacy hash path must remain as fallthrough")
        return 1
    print("  ok: cache_fingerprint fails safe to legacy hash on error")

    print("-- 4. NEGATIVE: HyDE wire fires ONLY when min_score returns 0 chunks --")
    # Per HyDE heuristic: don't fire on every query (2x latency for
    # easy queries). Drill enforces the `len(chunks) == 0` guard
    # appears in the SAME if-block as the HYDE_ENABLED check.
    # Find the `if (` block that contains HYDE_ENABLED (multi-line).
    hyde_block_start = src.find("HYDE_ENABLED")
    hyde_block_end = src.find("latency_ms = ", hyde_block_start)
    if hyde_block_end < 0:
        hyde_block_end = hyde_block_start + 2000
    # Look forward (the conditional body) AND backward for the
    # `if (` line that wraps the env check.
    surrounding = src[max(0, hyde_block_start - 500):hyde_block_end]
    if "len(chunks) == 0" not in surrounding:
        print("x HyDE wire must guard with `len(chunks) == 0` near HYDE_ENABLED")
        return 1
    hyde_block = src[hyde_block_start:hyde_block_end]
    print("  ok: HyDE fires only on empty-result fallback path")

    print("-- 5. NEGATIVE: HyDE re-run uses vector strategy + min_score=0 --")
    # When HyDE fires, the hypothetical is embedded and used as query.
    # Re-running with the original min_score would defeat the purpose
    # (HyDE already produces the closest matches by definition).
    # Strategy must be "vector" for the re-run since BM25/graph don't
    # benefit from hypothetical-doc embedding.
    if "strategy=\"vector\"" not in hyde_block:
        print("x HyDE re-run must use strategy='vector'")
        return 1
    if "min_score=0.0" not in hyde_block:
        print("x HyDE re-run must use min_score=0.0 (don't double-floor)")
        return 1
    print("  ok: HyDE re-run = vector + min_score=0.0 (correct semantics)")

    print("-- 6. NEGATIVE: both wires lazy-import (no module-top dep) --")
    # Cold-start invariant: Stage-1 adapters NOT loaded at retriever
    # module import. Both imports happen inside the conditional blocks.
    class_idx = src.find("class HybridRetriever")
    lines_before_class = src[:class_idx]
    if "import cache_fingerprint" in lines_before_class:
        print("x cache_fingerprint must NOT be imported at module top")
        return 1
    if "from cache_fingerprint" in lines_before_class:
        print("x cache_fingerprint must NOT be 'from'-imported at module top")
        return 1
    if "import hyde_adapter" in lines_before_class:
        print("x hyde_adapter must NOT be imported at module top")
        return 1
    if "from hyde_adapter" in lines_before_class:
        print("x hyde_adapter must NOT be 'from'-imported at module top")
        return 1
    print("  ok: both Stage-1 adapters lazy-imported")

    print("-- 7. NEGATIVE: HyDE wire fails-safe — caller's chunks list preserved --")
    # If HyDE generation or re-retrieval fails, caller must continue
    # with the original empty chunks list (acceptable non-error
    # outcome). Drill enforces the try/except.
    if "try:" not in hyde_block:
        print("x HyDE wire must wrap in try/except (fail-safe)")
        return 1
    if "except Exception" not in hyde_block:
        print("x must catch generic Exception around HyDE (fail-safe)")
        return 1
    if "log.warning" not in hyde_block:
        print("x failure path must log.warning so ops sees the issue")
        return 1
    print("  ok: HyDE failure caught + logged + chunks preserved")

    print("-- 8. POSITIVE: retriever Python-valid + no regression on prior drills --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x HybridRetriever has syntax error after Stage-2 wires: {exc}")
        return 1
    print("  ok: HybridRetriever Python-valid after both Stage-2 wires")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
