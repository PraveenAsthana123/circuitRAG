#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-2 best_config_loader secondary-hint wire into ingestion saga.

Per §43 + §47 + §56. Locks the 4th-consumer wire in the empirical
loop chain. Without this drill, a future refactor could promote the
secondary hint into a PRIMARY override that displaces the chunking-
strategy selector — breaking the §49 'selector wins when enabled'
contract.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SAGA = REPO / "services" / "ingestion-svc" / "app" / "saga" / "document_saga.py"
LOADER = REPO / "scripts" / "best_config_loader.py"


def main() -> int:
    print("-- 1. POSITIVE: saga lazy-imports from best_config_loader --")
    if not SAGA.exists():
        print(f"x {SAGA} missing")
        return 1
    src = SAGA.read_text(encoding="utf-8")
    if "from best_config_loader import" not in src:
        print("x saga must import from best_config_loader")
        return 1
    print("  ok: best_config_loader imported")

    print("-- 2. NEGATIVE: import is INSIDE the chunk-step (lazy, not module-level) --")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            if mod == "best_config_loader" or "best_config_loader" in names:
                print("x best_config_loader must NOT be imported at module level")
                return 1
    print("  ok: lazy import inside the chunk step")

    print("-- 3. NEGATIVE: env-flag gated (BEST_CONFIG_LOADER_ENABLED) --")
    if "BEST_CONFIG_LOADER_ENABLED" not in src:
        print("x saga must check BEST_CONFIG_LOADER_ENABLED")
        return 1
    print("  ok: env-flag gated")

    print("-- 4. NEGATIVE: SECONDARY hint — selector wins when enabled --")
    # The whole point of this Stage-2 wire being SECONDARY: when the
    # primary selector (CHUNKING_STRATEGY_SELECTOR_ENABLED) is on AND
    # it produces a strategy, best_config MUST NOT override.
    # Drill enforces the `_strategy is None` guard.
    bc_block_start = src.find("Stage-2 best_config_loader wire")
    if bc_block_start < 0:
        print("x best_config Stage-2 wire marker missing")
        return 1
    bc_block_end = src.find("raw_chunks = await", bc_block_start)
    bc_block = src[bc_block_start:bc_block_end]
    if "_strategy is None" not in bc_block:
        print("x wire must guard with `_strategy is None` (selector primacy)")
        return 1
    if "and _os_chunk.getenv" not in bc_block:
        print("x both conditions (selector-empty AND env-set) must be in same `if`")
        return 1
    print("  ok: secondary hint preserves selector primacy")

    print("-- 5. NEGATIVE: §47 fail-safe — loader errors NEVER raise --")
    if "try:" not in bc_block:
        print("x best_config block must wrap loader call in try/except")
        return 1
    if "except Exception" not in bc_block:
        print("x must catch generic Exception")
        return 1
    if "_strategy = None" not in bc_block:
        print("x except branch must reset _strategy=None for legacy fallback")
        return 1
    print("  ok: loader errors don't escape; fall back to legacy chunker")

    print("-- 6. NEGATIVE: minimal strategy dict — only name + source marker --")
    # The wire must NOT fabricate chunk_size_tokens / overlap_percent
    # values not in BestConfig — those are the chunker's constructor
    # defaults' job. Synthesizing them here would silently override the
    # operator-tuned chunker.
    if '"strategy_name": _bc_cfg.chunking_strategy' not in bc_block:
        print("x must set strategy_name from BestConfig")
        return 1
    if '"_source": "best_config_loader"' not in bc_block:
        print("x must mark _source='best_config_loader' for traceability")
        return 1
    # Check fabricated-field invariant via dict-key form (the
    # field name appearing in a comment is fine; setting it as a
    # value in _strategy is what the drill prevents).
    if '"chunk_size_tokens":' in bc_block:
        print("x must NOT fabricate chunk_size_tokens (not in BestConfig)")
        return 1
    if '"overlap_percent":' in bc_block:
        print("x must NOT fabricate overlap_percent (not in BestConfig)")
        return 1
    print("  ok: minimal dict; no fabricated fields")

    print("-- 7. POSITIVE: ast-valid + chunker invocation unchanged --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x syntax error after Stage-2 wire: {exc}")
        return 1
    # The chunker call MUST still be `self._chunker.chunk(self._parsed_doc, strategy=_strategy)`
    if "self._chunker.chunk, self._parsed_doc, strategy=_strategy" not in src:
        print("x chunker invocation must consume _strategy unchanged")
        return 1
    print("  ok: ast-valid; chunker invocation preserved")

    print("-- 8. NEGATIVE: best_config_loader.py UNCHANGED (no reverse import) --")
    loader_src = LOADER.read_text(encoding="utf-8")
    rev = re.compile(
        r"^\s*(from\s+.*ingestion|from\s+.*saga|"
        r"import\s+.*ingestion|import\s+.*saga|"
        r"from\s+services\.|import\s+services\.)",
        re.MULTILINE,
    )
    if rev.search(loader_src):
        print("x best_config_loader imports services (cycle risk)")
        return 1
    print("  ok: loader source clean; no cycle introduced")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
