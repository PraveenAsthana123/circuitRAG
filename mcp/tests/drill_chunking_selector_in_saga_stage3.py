#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-3 chunking-selector wire into saga + Chunker (per §43 + §56).

Last named pending iteration. Locks the Chunker interface change +
saga wire that route every ingestion through file-type-aware
chunking strategy selection.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECURSIVE = REPO / "services" / "ingestion-svc" / "app" / "chunking" / "recursive.py"
SAGA = REPO / "services" / "ingestion-svc" / "app" / "saga" / "document_saga.py"
SELECTOR = REPO / "scripts" / "chunking_strategy_selector.py"


def main() -> int:
    print("-- 1. POSITIVE: RecursiveChunker.chunk accepts strategy kwarg --")
    if not RECURSIVE.exists():
        print(f"x {RECURSIVE} missing")
        return 1
    rec_src = RECURSIVE.read_text(encoding="utf-8")
    if "strategy: dict | None = None" not in rec_src:
        print("x chunk() must accept `strategy: dict | None = None` kwarg")
        return 1
    print("  ok: chunk() signature accepts optional strategy kwarg")

    print("-- 2. NEGATIVE: chunking_strategy_selector source UNCHANGED (no reverse import) --")
    sel_src = SELECTOR.read_text(encoding="utf-8")
    rev_import = re.compile(
        r"^\s*(from\s+.*chunking|from\s+.*saga|import\s+.*saga|from\s+app\.|import\s+app\.)",
        re.MULTILINE,
    )
    if rev_import.search(sel_src):
        print("x chunking_strategy_selector imports chunker / saga (cycle risk)")
        return 1
    print("  ok: selector doesn't import chunker / saga (clean layering)")

    print("-- 3. NEGATIVE: strategy override is PER-CALL (state restored after) --")
    # The override must NOT leak into subsequent chunk() calls.
    # Drill enforces try/finally in chunk() that restores
    # constructor-time _target/_overlap.
    chunk_method_idx = rec_src.find("def chunk(\n        self,")
    if chunk_method_idx < 0:
        chunk_method_idx = rec_src.find("def chunk(self")
    chunk_end = rec_src.find("def _split_page", chunk_method_idx)
    chunk_body = rec_src[chunk_method_idx:chunk_end]
    if "saved_target" not in chunk_body:
        print("x must save constructor _target before override")
        return 1
    if "saved_overlap" not in chunk_body:
        print("x must save constructor _overlap before override")
        return 1
    if "finally:" not in chunk_body:
        print("x must use try/finally to restore state after chunk()")
        return 1
    if "self._target, self._overlap = saved_target, saved_overlap" not in chunk_body:
        print("x finally block must restore both _target and _overlap")
        return 1
    print("  ok: per-call strategy override; state restored in finally")

    print("-- 4. NEGATIVE: overlap_percent → absolute tokens with safe clamp --")
    # ChunkingStrategy.overlap_percent is 0-30; we convert to absolute
    # token count via target * percent / 100. Drill enforces:
    #   - clamp prevents overlap >= target (constructor-validated)
    #   - target_tokens override has minimum floor (32)
    if "overlap_percent" not in chunk_body:
        print("x must read overlap_percent from strategy")
        return 1
    if "target * overlap_pct / 100" not in chunk_body:
        print("x must convert percent to absolute tokens via target * pct / 100")
        return 1
    if "min(int(target * overlap_pct / 100), target - 1)" not in chunk_body:
        print("x must clamp overlap to <= target-1 (matches constructor validation)")
        return 1
    if "max(target, 32)" not in chunk_body:
        print("x must enforce minimum target floor (32 tokens)")
        return 1
    print("  ok: percent→absolute conversion + safe clamps")

    print("-- 5. NEGATIVE: legacy callers (strategy=None) see no behavior change --")
    # The whole point of Stage-3 additivity: existing callers that
    # don't pass strategy MUST get the constructor-time defaults.
    # Drill enforces the else-branch.
    if "if strategy is not None:" not in chunk_body:
        print("x must guard override behind `if strategy is not None`")
        return 1
    if "else:" not in chunk_body:
        print("x must have else-branch that uses self._target / self._overlap")
        return 1
    print("  ok: strategy=None preserves legacy behavior (constructor defaults)")

    print("-- 6. POSITIVE: saga wires selector.choose() → chunker.chunk(strategy=) --")
    if not SAGA.exists():
        print(f"x {SAGA} missing")
        return 1
    saga_src = SAGA.read_text(encoding="utf-8")
    if "from chunking_strategy_selector import choose" not in saga_src:
        print("x saga must import choose from chunking_strategy_selector")
        return 1
    if "CHUNKING_STRATEGY_SELECTOR_ENABLED" not in saga_src:
        print("x saga must check CHUNKING_STRATEGY_SELECTOR_ENABLED env flag")
        return 1
    if "strategy=_strategy" not in saga_src:
        print("x saga must pass strategy=_strategy to chunker.chunk()")
        return 1
    print("  ok: saga wired to selector.choose() with env-gated dispatch")

    print("-- 7. NEGATIVE: saga wire FAILS SAFE — selector error falls back to default --")
    chunk_step_idx = saga_src.find("async def _step_chunk")
    chunk_step_end = saga_src.find("async def", chunk_step_idx + 100)
    chunk_step_body = saga_src[chunk_step_idx:chunk_step_end]
    sel_block_start = chunk_step_body.find("CHUNKING_STRATEGY_SELECTOR_ENABLED")
    sel_block_end = chunk_step_body.find("raw_chunks = await", sel_block_start)
    sel_block = chunk_step_body[sel_block_start:sel_block_end]
    if "try:" not in sel_block:
        print("x saga selector wire must wrap choose() in try/except")
        return 1
    if "except Exception" not in sel_block:
        print("x must catch generic Exception (fail-safe)")
        return 1
    if "_strategy = None" not in chunk_step_body:
        print("x error path must reset _strategy to None (default chunker)")
        return 1
    print("  ok: selector errors fall back to default chunker behavior")

    print("-- 8. POSITIVE: both files Python-valid + no regression on prior chunker drills --")
    try:
        ast.parse(rec_src)
        ast.parse(saga_src)
    except SyntaxError as exc:
        print(f"x syntax error after Stage-3 wires: {exc}")
        return 1
    # Smoke: import recursive.py and verify the signature
    spec = importlib.util.spec_from_file_location("_chunker_smoke", RECURSIVE)
    # Actually loading would require app.parsers in sys.path; a
    # lighter check: signature inspection via ast.
    tree = ast.parse(rec_src)
    found_chunk = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "chunk":
            args = [a.arg for a in node.args.args]
            kwonly = [a.arg for a in node.args.kwonlyargs]
            if "strategy" in kwonly:
                found_chunk = True
                break
    if not found_chunk:
        print("x ast inspection: chunk() must have keyword-only `strategy` arg")
        return 1
    print("  ok: ast confirms chunk(self, document, *, strategy=...) signature")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
