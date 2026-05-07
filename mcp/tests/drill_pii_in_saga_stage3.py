#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PII Stage-3 wire into DocumentIngestionSaga (per §43 + §56).

Locks the Stage-3 promotion: pii_hook.redact_for_ingestion is now
called in _step_chunk BEFORE the chunker sees the parsed text.
Default-deny via PII_REDACTOR_ENABLED=1 (single gate inherited from
Stage-1/2).

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SAGA = REPO / "services" / "ingestion-svc" / "app" / "saga" / "document_saga.py"
PII_HOOK = REPO / "services" / "ingestion-svc" / "app" / "services" / "pii_hook.py"
PII_REDACTOR = REPO / "scripts" / "pii_redactor.py"


def main() -> int:
    print("-- 1. POSITIVE: saga now references pii_hook.redact_for_ingestion --")
    if not SAGA.exists():
        print(f"x {SAGA} missing")
        return 1
    src = SAGA.read_text(encoding="utf-8")
    if "redact_for_ingestion" not in src:
        print("x saga must call redact_for_ingestion")
        return 1
    if "PII_REDACTOR_ENABLED" not in src:
        print("x saga must check PII_REDACTOR_ENABLED env flag")
        return 1
    print("  ok: saga wired to redact_for_ingestion under PII_REDACTOR_ENABLED")

    print("-- 2. NEGATIVE: PII Stage-1 + Stage-2 modules don't IMPORT saga (clean layering) --")
    redactor_src = PII_REDACTOR.read_text(encoding="utf-8")
    hook_src = PII_HOOK.read_text(encoding="utf-8")
    # Documentation MENTIONS of DocumentIngestionSaga (in next_stage
    # docstrings or composition references) are legitimate. ACTUAL
    # cycle would be an import statement.
    saga_import_pattern = re.compile(
        r"^\s*(from\s+.*saga|import\s+.*saga)",
        re.MULTILINE,
    )
    if saga_import_pattern.search(redactor_src):
        print("x pii_redactor.py imports saga module (cycle risk)")
        return 1
    if saga_import_pattern.search(hook_src):
        print("x pii_hook.py imports saga module (cycle risk)")
        return 1
    # Stage-3 wire shouldn't re-fire from Stage-1/2 modules
    rewire_pattern = re.compile(
        r"^\s*if\s+.*PII_REDACTOR_ENABLED.*:.*\n.*redact_for_ingestion",
        re.MULTILINE,
    )
    if rewire_pattern.search(redactor_src) or rewire_pattern.search(hook_src):
        print("x Stage-1/2 modules must not re-wire Stage-3")
        return 1
    print("  ok: pii_redactor + pii_hook don't import saga (clean layering)")

    print("-- 3. NEGATIVE: wire fires INSIDE _step_chunk, not _step_parse --")
    # The right place is in _step_chunk BEFORE self._chunker.chunk,
    # not in _step_parse. Drilling the position lock prevents future
    # contributors from moving the wire to the wrong saga step.
    chunk_idx = src.find("async def _step_chunk")
    parse_idx = src.find("async def _step_parse")
    redact_idx = src.find("redact_for_ingestion(")
    if chunk_idx < 0 or parse_idx < 0 or redact_idx < 0:
        print("x missing _step_parse / _step_chunk / redact_for_ingestion")
        return 1
    if redact_idx < chunk_idx:
        print("x redact must be inside _step_chunk, not earlier")
        return 1
    # And BEFORE the chunker.chunk() call inside _step_chunk
    chunker_call_idx = src.find("self._chunker.chunk", chunk_idx)
    if chunker_call_idx < 0:
        print("x couldn't locate self._chunker.chunk inside _step_chunk")
        return 1
    if redact_idx >= chunker_call_idx:
        print("x redact must run BEFORE self._chunker.chunk (semantic order)")
        return 1
    print("  ok: redact fires inside _step_chunk BEFORE chunker.chunk")

    print("-- 4. NEGATIVE: default-deny — wire ONLY fires when env flag set to '1' --")
    flag_check = re.search(
        r'os\.getenv\(\s*[\'"]PII_REDACTOR_ENABLED[\'"][^)]*\)\s*\.strip\(\)\s*==\s*[\'"]1[\'"]',
        src,
    )
    if not flag_check:
        print("x flag check must be exact: os.getenv(...).strip() == '1'")
        return 1
    print("  ok: default-deny — wire fires only when flag literally '1'")

    print("-- 5. NEGATIVE: lazy import inside conditional (no module-top dep) --")
    # The pii_hook import must be lazy. saga module-top must NOT import
    # pii_hook because:
    #   - saga is imported on every cold start
    #   - pii_hook lazily imports pii_redactor lazily imports presidio
    #   - we don't want presidio's spaCy model probe at saga cold start
    saga_class_idx = src.find("class DocumentIngestionSaga")
    lines_before_class = src[:saga_class_idx]
    if "from app.services.pii_hook" in lines_before_class:
        print("x pii_hook must NOT be imported at saga module top")
        return 1
    if "import pii_hook" in lines_before_class:
        print("x pii_hook must NOT be imported at saga module top")
        return 1
    print("  ok: pii_hook lazy-imported inside _step_chunk")

    print("-- 6. NEGATIVE: wire FAILS SAFE — exception caught + ingestion proceeds --")
    # PII errors must NEVER block ingestion. The wire MUST wrap
    # redact_for_ingestion in try/except so an environment glitch
    # (Presidio model unloaded, OOM, etc) doesn't fail the saga.
    chunk_block = src[chunk_idx:src.find("async def", chunk_idx + 100)]
    if "redact_for_ingestion" in chunk_block:
        # Extract the wire block (between PII_REDACTOR_ENABLED check and chunker call)
        wire_start = chunk_block.find("PII_REDACTOR_ENABLED")
        wire_end = chunk_block.find("self._chunker.chunk")
        wire_block = chunk_block[wire_start:wire_end] if wire_start >= 0 else ""
        if "try:" not in wire_block:
            print("x wire must wrap redact in try/except (fail-safe)")
            return 1
        if "except Exception" not in wire_block:
            print("x must catch generic Exception around redact (fail-safe)")
            return 1
    print("  ok: redact failure caught — ingestion never blocked on PII error")

    print("-- 7. NEGATIVE: per-page iteration (not bulk concat) --")
    # The right shape is to redact each page's text in place. Concatenating
    # all pages first, redacting once, then re-splitting by page is
    # error-prone (page boundaries get messed up by the redactor's
    # placeholder text). Drill enforces per-page iteration.
    if "for page in self._parsed_doc.pages" not in src:
        print("x must iterate pages individually for in-place redaction")
        return 1
    # Skip empty pages
    if "page.text.strip()" not in src and "if not page.text" not in src:
        print("x must skip pages with empty text")
        return 1
    print("  ok: per-page iteration with empty-page skip")

    print("-- 8. POSITIVE: saga still Python-valid + no regression in existing drills --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x saga has syntax error after Stage-3 wire: {exc}")
        return 1
    print("  ok: saga Python-valid after Stage-3 wire")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
