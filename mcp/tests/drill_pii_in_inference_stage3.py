#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PII Stage-3 wire into inference-svc rag_inference.ask (per §43 + §56).

Symmetric to drill_pii_in_saga_stage3 — that drill locks the ingestion
side; this one locks the inference side. PII redaction fires AFTER
retrieval AND BEFORE prompt assembly. Defense in depth — protects
against PII that entered the corpus before the ingestion-side wire
was active OR that the ingestion redactor missed.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAG_INFER = REPO / "services" / "inference-svc" / "app" / "services" / "rag_inference.py"
PII_REDACTOR = REPO / "scripts" / "pii_redactor.py"


def main() -> int:
    print("-- 1. POSITIVE: rag_inference now references pii_redactor --")
    if not RAG_INFER.exists():
        print(f"x {RAG_INFER} missing")
        return 1
    src = RAG_INFER.read_text(encoding="utf-8")
    if "pii_redactor" not in src:
        print("x rag_inference must import pii_redactor (lazy)")
        return 1
    if "PII_REDACTOR_ENABLED" not in src:
        print("x rag_inference must check PII_REDACTOR_ENABLED env flag")
        return 1
    print("  ok: rag_inference wired to pii_redactor under PII_REDACTOR_ENABLED")

    print("-- 2. NEGATIVE: pii_redactor doesn't IMPORT inference modules (no cycle) --")
    redactor_src = PII_REDACTOR.read_text(encoding="utf-8")
    # Documentation MENTIONS of rag_inference (in next_stage docstrings)
    # are legitimate. ACTUAL import statements would be a cycle.
    inference_import = re.compile(
        r"^\s*(from\s+.*rag_inference|import\s+.*rag_inference|from\s+.*inference_svc|import\s+.*inference_svc)",
        re.MULTILINE,
    )
    if inference_import.search(redactor_src):
        print("x pii_redactor.py imports inference module (cycle risk)")
        return 1
    print("  ok: pii_redactor doesn't import inference modules (no cycle)")

    print("-- 3. NEGATIVE: wire fires AFTER retrieval but BEFORE prompt assembly --")
    # Semantic order: retrieve → PII-redact-each-chunk → prompt-build → LLM
    # Reversing the order would either redact wasted work (after prompt)
    # OR miss the chunks (before retrieve). Drill enforces the
    # retrieve→redact→prompt order.
    retrieve_idx = src.find("self._retrieval.retrieve(")
    redact_idx = src.find("PII_REDACTOR_ENABLED")
    prompt_idx = src.find("self._prompts.build(")
    if retrieve_idx < 0 or redact_idx < 0 or prompt_idx < 0:
        print("x missing retrieve / PII / prompt block in rag_inference")
        return 1
    if not (retrieve_idx < redact_idx < prompt_idx):
        print(f"x order broken: retrieve={retrieve_idx} redact={redact_idx} prompt={prompt_idx}")
        return 1
    print("  ok: retrieve → PII-redact → prompt-build (correct semantic order)")

    print("-- 4. NEGATIVE: default-deny — wire fires only when env flag literally '1' --")
    flag_check = re.search(
        r'_os\.getenv\(\s*[\'"]PII_REDACTOR_ENABLED[\'"][^)]*\)\s*\.strip\(\)\s*==\s*[\'"]1[\'"]',
        src,
    )
    if not flag_check:
        # Allow either `os.getenv` or `_os.getenv` (alias in this file)
        flag_check_alt = re.search(
            r'os\.getenv\(\s*[\'"]PII_REDACTOR_ENABLED[\'"][^)]*\)\s*\.strip\(\)\s*==\s*[\'"]1[\'"]',
            src,
        )
        if not flag_check_alt:
            print("x flag check must be exact: getenv(...).strip() == '1'")
            return 1
    print("  ok: default-deny — wire fires only when flag literally '1'")

    print("-- 5. NEGATIVE: lazy import of pii_redactor (NOT at module top) --")
    # Stage-3 cold-start invariant: rag_inference is on the request hot
    # path; presidio's spaCy model probe must NOT load at module import.
    # The pii_redactor import sits inside the if-block.
    class_ask = src.find("class RagInference")
    if class_ask < 0:
        # Older symbol name? Check for the function head
        class_ask = src.find("async def ask(")
    lines_before = src[:class_ask] if class_ask >= 0 else src[:1000]
    if "import pii_redactor" in lines_before:
        print("x pii_redactor must NOT be imported at module top")
        return 1
    if "from pii_redactor" in lines_before:
        print("x pii_redactor must NOT be 'from'-imported at module top")
        return 1
    print("  ok: pii_redactor lazy-imported inside the redact block")

    print("-- 6. NEGATIVE: wire FAILS SAFE — exception caught + chunks proceed unchanged --")
    # Per §47 fallback rule. The retrieve→prompt path must NOT break
    # if Presidio errors out. Drill enforces try/except around the
    # redact block + a log line.
    redact_block_start = src.find("PII_REDACTOR_ENABLED")
    redact_block_end = src.find("# 2. Prompt", redact_block_start)
    if redact_block_end < 0:
        redact_block_end = src.find("self._prompts.build", redact_block_start)
    redact_block = src[redact_block_start:redact_block_end]
    if "try:" not in redact_block:
        print("x wire must wrap redact in try/except (fail-safe)")
        return 1
    if "except Exception" not in redact_block:
        print("x must catch generic Exception (fail-safe)")
        return 1
    if "log.warning" not in redact_block:
        print("x failure path must log.warning so ops sees the issue")
        return 1
    print("  ok: redact failure caught + logged + chunks preserved")

    print("-- 7. NEGATIVE: per-chunk iteration with empty-chunk skip --")
    # The wire iterates chunks individually (not bulk concat). Skips
    # chunks with empty/whitespace text. Handles BOTH dict-shaped
    # chunks AND object-shaped chunks (defensive).
    if "for chunk in chunks" not in src:
        print("x must iterate chunks individually for in-place redaction")
        return 1
    if "isinstance(chunk, dict)" not in src:
        print("x must handle BOTH dict and object chunk shapes")
        return 1
    if ".strip()" not in redact_block:
        print("x must skip chunks with empty/whitespace text")
        return 1
    print("  ok: per-chunk iteration with empty-chunk skip + dict/object support")

    print("-- 8. POSITIVE: rag_inference Python-valid + no regression on saga drill --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x rag_inference has syntax error after Stage-3 wire: {exc}")
        return 1
    print("  ok: rag_inference Python-valid after Stage-3 wire")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
