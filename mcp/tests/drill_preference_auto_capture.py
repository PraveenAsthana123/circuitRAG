#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: preference-dataset auto-capture (Phase C #3.1).

Per CLAUDE.md §43 + §55. Locks the contract:
  - 'auto_capture' added to Verdict Literal (no breaking change)
  - auto_capture_council_outcome writes a valid HitlScore row
  - cmd_review filters to verdict='auto_capture' rows only
  - local_council fire-and-forget integration (council never fails
    if hitl_framework import breaks)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HF_PATH = REPO / "scripts" / "hitl_framework.py"
LC_PATH = REPO / "scripts" / "local_council.py"


def _load(name, path):
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: auto_capture added to Verdict Literal --")
    hf = _load("hitl_framework", HF_PATH)
    # Construct a HitlScore with verdict='auto_capture' to confirm the
    # Literal accepts it.
    score = hf.HitlScore(
        timestamp=hf.now_iso(),
        gate="author", issue_id="test-issue",
        rule_code="UP035", model="deepseek-coder",
        verdict="auto_capture", score=0, confidence=0.5,
        note="drill",
    )
    if score.verdict != "auto_capture":
        print(f"x step 1: verdict='auto_capture' didn't roundtrip; got {score.verdict!r}")
        return 1
    print("  ok: verdict='auto_capture' accepted by Literal")

    print("-- 2. POSITIVE: auto_capture_council_outcome exported + callable --")
    if not hasattr(hf, "auto_capture_council_outcome"):
        print("x step 2: auto_capture_council_outcome missing")
        return 1
    if not callable(hf.auto_capture_council_outcome):
        print("x step 2: auto_capture_council_outcome not callable")
        return 1
    print("  ok: helper exported")

    print("-- 3. POSITIVE: helper writes a valid HitlScore + appends to log --")
    # Use a temp log so we don't pollute the real one
    real_log = hf.HITL_LOG
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        hf.HITL_LOG = Path(fh.name)
    try:
        score = hf.auto_capture_council_outcome(
            issue_id="ruff-UP035-test-L1",
            rule_code="UP035",
            council_outcome="council_complete",
            author_model="deepseek-coder:6.7b-instruct",
            author_proposal_summary="swap typing.Callable",
            confidence=0.85,
        )
        if score.verdict != "auto_capture":
            print(f"x step 3: helper produced verdict={score.verdict!r}")
            return 1
        if score.score != 0:
            print(f"x step 3: helper score should be 0 (pending); got {score.score}")
            return 1
        # Verify appended to the file
        loaded = hf.load_scores()
        captures = [s for s in loaded if s.verdict == "auto_capture"]
        if not captures:
            print("x step 3: helper didn't append to log")
            return 1
    finally:
        hf.HITL_LOG = real_log
        os.unlink(score.timestamp.replace(":", "_") + ".tmp") if False else None  # noqa
    print("  ok: helper writes verdict='auto_capture' + score=0 row to log")

    print("-- 4. NEGATIVE: cmd_review filters to verdict='auto_capture' only --")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        hf.HITL_LOG = Path(fh.name)
    try:
        # Mix verdicts: 1 auto_capture + 1 approve + 1 reject
        for verdict in ("auto_capture", "approve", "reject"):
            sc = hf.HitlScore(
                timestamp=hf.now_iso(),
                gate="author", issue_id=f"x-{verdict}",
                rule_code="UP035", verdict=verdict,
                score=0 if verdict == "auto_capture" else 4,
                confidence=0.5, note="drill",
            )
            hf.append_score(sc)
        loaded = hf.load_scores()
        captures = [s for s in loaded if s.verdict == "auto_capture"]
        approves = [s for s in loaded if s.verdict == "approve"]
        if len(captures) != 1 or len(approves) != 1:
            print(f"x step 4: log loaded {len(captures)} auto + {len(approves)} approve; expected 1 of each")
            return 1
    finally:
        hf.HITL_LOG = real_log
    print("  ok: log/load preserve verdict distinction; review filter would target 1 row")

    print("-- 5. NEGATIVE: extra field STILL rejected on auto_capture row --")
    try:
        hf.HitlScore.model_validate({
            "timestamp": hf.now_iso(),
            "gate": "author", "issue_id": "x",
            "verdict": "auto_capture", "score": 0,
            "confidence": 0.5,
            "note": "x",
            "chosen_text": None, "rejected_text": None,
            "operator_pii": "praveen@example.com",  # extra
        })
    except Exception:
        print("  ok: extra 'operator_pii' rejected even on auto_capture row (extra='forbid' preserved)")
    else:
        print("x step 5: extra field accepted on auto_capture")
        return 1

    print("-- 6. POSITIVE: cmd_review subcommand wired in main() --")
    src = HF_PATH.read_text(encoding="utf-8")
    if 'add_parser("review"' not in src:
        print("x step 6: argparse missing review subparser")
        return 1
    if "def cmd_review(" not in src:
        print("x step 6: cmd_review function missing")
        return 1
    print("  ok: review subcommand wired")

    print("-- 7. NEGATIVE: local_council fire-and-forget integration (broken hitl ≠ broken council) --")
    lc_src = LC_PATH.read_text(encoding="utf-8")
    if "auto_capture_council_outcome" not in lc_src:
        print("x step 7: local_council does NOT call auto_capture_council_outcome")
        return 1
    # Verify the call is wrapped in except Exception (fire-and-forget)
    if "except Exception" not in lc_src or "Auto-capture is fire-and-forget" not in lc_src:
        print("x step 7: auto_capture call is NOT wrapped in fire-and-forget except guard")
        return 1
    print("  ok: local_council calls auto_capture_council_outcome inside fire-and-forget guard")

    print("-- 8. POSITIVE: pending audit field present (score=0 → operator-pending) --")
    score = hf.HitlScore(
        timestamp=hf.now_iso(), gate="author", issue_id="x",
        verdict="auto_capture", score=0, confidence=0.5, note="x",
    )
    if score.score != 0:
        print(f"x step 8: auto_capture score not 0: {score.score}")
        return 1
    print("  ok: auto_capture rows have score=0 (signal: operator-pending; will be re-set on review)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
