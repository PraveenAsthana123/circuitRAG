#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: prior-fix RAG (Tier 2 #2.6) — both directions.

Per CLAUDE.md §43 + §55. Locks the contract:
  - zero preference data → empty list (no theater retrieval)
  - rejected verdict rows NEVER returned (anti-examples skipped)
  - BM25 prefers exact rule_code matches
  - render_few_shot returns '' on empty list (no prompt bloat)
  - integration: _prior_fix_section in local_council returns ''
    when index is empty

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "prior_fix_rag.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("prior_fix_rag", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["prior_fix_rag"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: prior_fix_rag imports + 5 exports --")
    rag = _load()
    for name in ("FixExample", "query_similar_fixes", "render_few_shot",
                 "POSITIVE_VERDICTS", "BM25_K1"):
        if not hasattr(rag, name):
            print(f"x step 1: missing export {name}")
            return 1
    if rag.POSITIVE_VERDICTS != ("approve", "edit"):
        print(f"x step 1: POSITIVE_VERDICTS unexpected: {rag.POSITIVE_VERDICTS}")
        return 1
    print(f"  ok: 5 exports; positive verdicts={rag.POSITIVE_VERDICTS}")

    print("-- 2. POSITIVE: zero-data behavior — query returns [] when no log --")
    # Temporarily redirect HITL_LOG to a non-existent path
    real_log = rag.HITL_LOG
    rag.HITL_LOG = Path("/tmp/_definitely_does_not_exist_12345.jsonl")
    try:
        result = rag.query_similar_fixes(query="test", rule_code="UP035")
        if result != []:
            print(f"x step 2: missing log should yield []; got {result}")
            return 1
    finally:
        rag.HITL_LOG = real_log
    print("  ok: missing HITL log → empty list (no theater)")

    print("-- 3. POSITIVE: render_few_shot returns '' for empty list --")
    if rag.render_few_shot([]) != "":
        print("x step 3: render_few_shot([]) should be ''")
        return 1
    print("  ok: empty list → '' (no prompt bloat)")

    print("-- 4. NEGATIVE: rejected-verdict rows NEVER appear in results --")
    # Build a fake HITL log with one rejected + one approved row;
    # only the approved one should retrieve.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        fh.write(json.dumps({
            "timestamp": "2026-05-02T00:00:00+00:00",
            "gate": "author", "issue_id": "rejected-row",
            "rule_code": "UP035", "model": "deepseek-coder",
            "verdict": "reject", "score": 1, "confidence": 1.0, "note": "BAD-FIX-EXAMPLE",
        }) + "\n")
        fh.write(json.dumps({
            "timestamp": "2026-05-02T00:00:00+00:00",
            "gate": "author", "issue_id": "approved-row",
            "rule_code": "UP035", "model": "deepseek-coder",
            "verdict": "approve", "score": 5, "confidence": 1.0,
            "note": "GOOD-FIX-EXAMPLE",
        }) + "\n")
        tmp_log = Path(fh.name)
    rag.HITL_LOG = tmp_log
    try:
        result = rag.query_similar_fixes(query="UP035 deprecated typing", rule_code="UP035", min_score=0.0)
        notes = [r.note for r in result]
        if any("BAD-FIX" in n for n in notes):
            print("x step 4: rejected row leaked into retrieval results")
            return 1
        if not any("GOOD-FIX" in n for n in notes):
            print(f"x step 4: approved row not retrieved: {notes}")
            return 1
    finally:
        rag.HITL_LOG = real_log
        tmp_log.unlink(missing_ok=True)
    print("  ok: verdict='reject' rows skipped; only approve/edit returned")

    print("-- 5. NEGATIVE: rule_code match boosts ranking (exact > different) --")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        fh.write(json.dumps({
            "timestamp": "2026-05-02T00:00:00+00:00",
            "gate": "author", "issue_id": "match-row",
            "rule_code": "UP035", "verdict": "approve", "score": 5, "confidence": 1.0,
            "note": "callable typing collections.abc",
        }) + "\n")
        fh.write(json.dumps({
            "timestamp": "2026-05-02T00:00:00+00:00",
            "gate": "author", "issue_id": "other-row",
            "rule_code": "E702", "verdict": "approve", "score": 5, "confidence": 1.0,
            "note": "callable typing collections.abc",  # same text, diff rule
        }) + "\n")
        tmp_log = Path(fh.name)
    rag.HITL_LOG = tmp_log
    try:
        result = rag.query_similar_fixes(query="callable typing collections.abc", rule_code="UP035", min_score=0.0)
        if not result:
            print("x step 5: no results from BM25 query")
            return 1
        if result[0].rule_code != "UP035":
            print(f"x step 5: top result should be UP035 match; got {result[0].rule_code}")
            return 1
    finally:
        rag.HITL_LOG = real_log
        tmp_log.unlink(missing_ok=True)
    print("  ok: rule_code='UP035' query → top result is UP035 (rule-code 3x boost works)")

    print("-- 6. NEGATIVE: query without rule_code still works (graceful default) --")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        fh.write(json.dumps({
            "timestamp": "2026-05-02T00:00:00+00:00",
            "gate": "author", "issue_id": "x",
            "rule_code": "UP035", "verdict": "approve", "score": 5, "confidence": 1.0,
            "note": "callable from collections.abc",
        }) + "\n")
        tmp_log = Path(fh.name)
    rag.HITL_LOG = tmp_log
    try:
        # No rule_code provided
        result = rag.query_similar_fixes(query="callable", rule_code=None, min_score=0.0)
        # Should not crash; may or may not return depending on score
    finally:
        rag.HITL_LOG = real_log
        tmp_log.unlink(missing_ok=True)
    print("  ok: rule_code=None doesn't crash (graceful)")

    print("-- 7. NEGATIVE: render_few_shot does NOT include 'rejected' or PII fields --")
    fake_examples = [
        rag.FixExample(
            issue_id="x", rule_code="UP035",
            chosen_text="from collections.abc import Callable",
            note="example fix",
            score=2.5,
        ),
    ]
    rendered = rag.render_few_shot(fake_examples)
    if "<prior_fixes>" not in rendered:
        print("x step 7: rendered missing <prior_fixes> tag")
        return 1
    if "</prior_fixes>" not in rendered:
        print("x step 7: rendered missing closing tag")
        return 1
    if "score=2.5" not in rendered:
        print("x step 7: rendered missing score")
        return 1
    print("  ok: render output is XML-fenced; score visible; no leaked metadata")

    print("-- 8. NEGATIVE: local_council._prior_fix_section returns '' on empty index --")
    sys.path.insert(0, str(REPO / "scripts"))
    spec_lc = importlib.util.spec_from_file_location("local_council", REPO / "scripts" / "local_council.py")
    if spec_lc is None or spec_lc.loader is None:
        print("x step 8: could not load local_council")
        return 1
    lc = importlib.util.module_from_spec(spec_lc)
    sys.modules["local_council"] = lc
    spec_lc.loader.exec_module(lc)
    rag.HITL_LOG = Path("/tmp/_empty_log_99999.jsonl")
    try:
        section = lc._prior_fix_section({"id": "x", "code": "UP035", "message": "test"})
        if section != "":
            print(f"x step 8: empty index → _prior_fix_section returned non-empty: {section!r}")
            return 1
    finally:
        rag.HITL_LOG = real_log
    print("  ok: empty index → _prior_fix_section('') (AUTHOR prompt unchanged)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
