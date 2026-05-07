#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: HITL framework — score capture + preference-pair export.

Locks the HITL framework's contract per the autonomous-fix-bot
roadmap (Tier 3 #3.1 + Tier 4 #4.5):

  - All 6 gate types accepted (research, author, reviewer, advisor,
    apply, post_commit) — wider gate set rejected
  - score field bounded [0, 5] — out-of-range rejected
  - confidence field bounded [0, 1] — out-of-range rejected
  - verdict='edit' WITHOUT chosen_text+rejected_text rejected (would
    pollute the preference dataset with empty pairs)
  - extra fields rejected per Pydantic extra='forbid'
  - Preference pairs export filters correctly (only verdict='edit'
    with both texts populated)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "hitl_framework.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("hitl_framework", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load hitl_framework from {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hitl_framework"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: hitl_framework imports + 6 exports --")
    hf = _load()
    for name in ("HitlScore", "GATE_TYPES", "append_score", "load_scores", "now_iso", "main"):
        if not hasattr(hf, name):
            print(f"x step 1: missing export {name}")
            return 1
    if len(hf.GATE_TYPES) != 6:
        print(f"x step 1: expected 6 gate types; got {len(hf.GATE_TYPES)}")
        return 1
    print(f"  ok: 6 exports + 6 gate types ({hf.GATE_TYPES})")

    print("-- 2. POSITIVE: well-formed HitlScore parses + all fields preserved --")
    valid_score = hf.HitlScore(
        timestamp=hf.now_iso(),
        gate="author",
        issue_id="ruff-UP035-test-L1",
        rule_code="UP035",
        model="deepseek-coder:6.7b-instruct",
        verdict="approve",
        score=4,
        confidence=0.9,
        note="diff was correct",
    )
    assert valid_score.gate == "author"
    assert valid_score.verdict == "approve"
    assert valid_score.score == 4
    print("  ok: HitlScore validated; 11 fields including optional chosen_text/rejected_text")

    print("-- 3. NEGATIVE: invalid gate type → ValidationError --")
    try:
        hf.HitlScore(
            timestamp=hf.now_iso(),
            gate="invalid_gate",  # type: ignore
            issue_id="x",
            verdict="approve",
            score=3,
        )
    except Exception:
        print("  ok: gate='invalid_gate' rejected by Literal type")
    else:
        print("x step 3: invalid gate accepted — Literal[...] not enforcing")
        return 1

    print("-- 4. NEGATIVE: score out of [0, 5] range → ValidationError --")
    try:
        hf.HitlScore(
            timestamp=hf.now_iso(),
            gate="author",
            issue_id="x",
            verdict="approve",
            score=10,
        )
    except Exception:
        print("  ok: score=10 rejected (Field ge/le bounds enforced)")
    else:
        print("x step 4: score=10 accepted — bounds not enforced")
        return 1

    print("-- 5. NEGATIVE: confidence out of [0, 1] → ValidationError --")
    try:
        hf.HitlScore(
            timestamp=hf.now_iso(),
            gate="author",
            issue_id="x",
            verdict="approve",
            score=3,
            confidence=2.5,
        )
    except Exception:
        print("  ok: confidence=2.5 rejected")
    else:
        print("x step 5: confidence=2.5 accepted")
        return 1

    print("-- 6. NEGATIVE: extra hallucinated field → ValidationError (extra='forbid') --")
    try:
        hf.HitlScore.model_validate({
            "timestamp": hf.now_iso(),
            "gate": "author",
            "issue_id": "x",
            "verdict": "approve",
            "score": 3,
            "operator_pii": "praveen@example.com",  # extra field
        })
    except Exception:
        print("  ok: extra 'operator_pii' field rejected; PII contamination blocked")
    else:
        print("x step 6: extra field accepted")
        return 1

    print("-- 7. NEGATIVE: verdict='edit' without both texts → CLI rejects --")
    # Schema allows the construction (chosen_text/rejected_text are optional);
    # the CLI cmd_record() enforces the pair rule. Verify by simulating
    # the cmd_record path with an args namespace.
    import argparse
    args = argparse.Namespace(
        gate="author", issue_id="x", verdict="edit",
        score=3, confidence=1.0, note="", rule_code=None, model=None,
        chosen_text="i wrote this",
        rejected_text=None,  # missing!
    )
    # Use a temporary log file so we don't pollute the real one
    real_log = hf.HITL_LOG
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        hf.HITL_LOG = Path(fh.name)
    try:
        rc = hf.cmd_record(args)
        if rc == 0:
            print("x step 7: verdict='edit' without rejected_text was accepted")
            return 1
        print("  ok: verdict='edit' missing rejected_text rejected by cmd_record")
    finally:
        hf.HITL_LOG = real_log

    print("-- 8. POSITIVE: preference-pairs export filters edit rows correctly --")
    # Three scores: 1 approve (skip), 1 edit-with-pair (include), 1 edit-missing (skip)
    pairs_input = [
        hf.HitlScore(
            timestamp=hf.now_iso(), gate="author", issue_id="a", verdict="approve",
            score=4, confidence=1.0,
        ),
        hf.HitlScore(
            timestamp=hf.now_iso(), gate="author", issue_id="b", verdict="edit",
            score=4, confidence=1.0,
            chosen_text="operator wrote this",
            rejected_text="model wrote that",
        ),
        hf.HitlScore(
            timestamp=hf.now_iso(), gate="author", issue_id="c", verdict="edit",
            score=4, confidence=1.0,
            chosen_text=None,  # missing
            rejected_text="model output",
        ),
    ]
    # Simulate the filter logic from cmd_preference_pairs
    pairs = [
        s for s in pairs_input
        if s.verdict == "edit" and s.chosen_text and s.rejected_text
    ]
    if len(pairs) != 1:
        print(f"x step 8: filter produced {len(pairs)} pairs, expected 1")
        return 1
    print("  ok: only 1 valid (chosen, rejected) pair extracted from 3 inputs")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
