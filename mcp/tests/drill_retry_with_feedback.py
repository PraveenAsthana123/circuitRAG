#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: retry-with-feedback (Tier 2 #2.1) — both directions locked.

Per CLAUDE.md §43 + §55. When AUTHOR's first output fails schema
validation, retry once with the validation error embedded as
explicit feedback. Empirically: schema-rejected outputs are often
ALMOST right (missing one field; wrong rule_code; etc.) — a second
attempt with concrete feedback can recover them at low cost.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LC_PATH = REPO / "scripts" / "local_council.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("local_council", LC_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {LC_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["local_council"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: _summarize_validation_failure exported + callable --")
    lc = _load()
    if not hasattr(lc, "_summarize_validation_failure"):
        print("x step 1: _summarize_validation_failure missing")
        return 1
    print("  ok: helper exported")

    print("-- 2. POSITIVE: empty input → human-readable instruction --")
    out = lc._summarize_validation_failure("")
    if "empty" not in out.lower() or "councilproposal" not in out.lower():
        print(f"x step 2: empty input feedback unhelpful: {out!r}")
        return 1
    print(f"  ok: empty → {out[:80]}")

    print("-- 3. NEGATIVE: prose-only input → 'no balanced JSON' message --")
    out = lc._summarize_validation_failure("Sure, I'll add a semicolon to fix the error.")
    if "no balanced JSON" not in out and "no balanced json" not in out.lower():
        print(f"x step 3: prose-only feedback didn't cite the missing JSON: {out!r}")
        return 1
    print(f"  ok: prose-only → {out[:80]}")

    print("-- 4. NEGATIVE: missing required field → top-3 ValidationError detail --")
    bad = json.dumps({
        "file_path": "scripts/test.py",
        # rule_code MISSING
        "summary": "fix",
        "unified_diff": "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n",
        "confidence": 0.9,
        "risks": [],
    })
    out = lc._summarize_validation_failure(bad)
    if "rule_code" not in out:
        print(f"x step 4: missing-field feedback didn't name the missing field: {out!r}")
        return 1
    if "ValidationError" not in out and "validation" not in out.lower():
        print(f"x step 4: feedback should cite Pydantic error type: {out!r}")
        return 1
    print("  ok: missing rule_code surfaced in feedback")

    print("-- 5. NEGATIVE: extra field → top-3 ValidationError detail --")
    bad = json.dumps({
        "file_path": "scripts/test.py",
        "rule_code": "UP035",
        "summary": "fix",
        "unified_diff": "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n",
        "confidence": 0.9,
        "risks": [],
        "reasoning": "I think this fix is correct because...",  # extra
    })
    out = lc._summarize_validation_failure(bad)
    if "reasoning" not in out and "extra" not in out.lower():
        print(f"x step 5: extra-field feedback should mention 'reasoning' or 'extra': {out!r}")
        return 1
    print("  ok: extra 'reasoning' field surfaced in feedback")

    print("-- 6. NEGATIVE: tokenizer artifact → top-3 ValidationError detail --")
    bad = json.dumps({
        "file_path": "scripts/<｜begin▁of▁sentence｜>test.py",
        "rule_code": "UP035",
        "summary": "fix",
        "unified_diff": "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n",
        "confidence": 0.9,
        "risks": [],
    })
    out = lc._summarize_validation_failure(bad)
    if "tokenizer" not in out.lower() and "file_path" not in out:
        print(f"x step 6: tokenizer artifact should be cited: {out!r}")
        return 1
    print("  ok: tokenizer artifact rejection surfaced in feedback")

    print("-- 7. NEGATIVE: run_local_council source has the retry loop --")
    src = LC_PATH.read_text(encoding="utf-8")
    if "for attempt in range(2):" not in src:
        print("x step 7: run_local_council missing the retry loop (range(2))")
        return 1
    if "<validation_feedback>" not in src:
        print("x step 7: retry prompt missing the <validation_feedback> XML tag")
        return 1
    if "author_schema_rejected_after_retry" not in src:
        print("x step 7: missing the post-retry rejection outcome")
        return 1
    print("  ok: retry loop bounded at 2 attempts; feedback section embedded")

    print("-- 8. POSITIVE: audit row schema preserves per-attempt entries --")
    # The implementation uses f"author_attempt_{attempt + 1}" — grep for the
    # f-string template, not the rendered keys.
    if 'f"author_attempt_{attempt + 1}"' not in src:
        print("x step 8: audit chain missing per-attempt f-string key template")
        return 1
    if 'audit_chain["author"] = audit_chain[f"author_attempt_' not in src:
        print("x step 8: legacy 'author' key not aliased to winning attempt")
        return 1
    if '"attempt"' not in src:
        print("x step 8: winning author entry missing 'attempt' counter")
        return 1
    print("  ok: per-attempt entries + legacy 'author' alias + attempt counter all present")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
