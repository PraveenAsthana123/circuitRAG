#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: eval-set auto-generator Stage-1 (per §43 + §56).

Locks the synthetic Q&A generator that unblocks AutoRAG / DSPy /
RAGAS empirical runs. Critical step: enforces the QUALITY GATE —
hedge phrases must drop the pair.

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "scripts" / "eval_set_generator.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: eval_set_generator.py exists + non-trivial size --")
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing")
        return 1
    src = ADAPTER.read_text(encoding="utf-8")
    if len(src) < 5000:
        print(f"x eval_set_generator too short ({len(src)} chars)")
        return 1
    print(f"  ok: eval_set_generator present ({len(src)} chars)")

    print("-- 2. POSITIVE: 7 contract surfaces exported --")
    os.environ["EVAL_SET_GENERATOR_ENABLED"] = "1"
    mod, spec = _load_module(ADAPTER)
    for name in ("is_available", "status", "generate_pair", "generate_set",
                 "write_jsonl", "EvalPair", "EvalSetGeneratorDisabled"):
        if not hasattr(mod, name):
            print(f"x eval_set_generator.{name} missing")
            return 1
    print("  ok: 7 surfaces exported")

    print("-- 3. NEGATIVE: default-deny — generate_pair() raises when env unset --")
    os.environ.pop("EVAL_SET_GENERATOR_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.generate_pair("some chunk text")
    except mod.EvalSetGeneratorDisabled as exc:
        raised = True
        if "EVAL_SET_GENERATOR_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x generate_pair() should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites env flag)")

    print("-- 4. NEGATIVE: hedge-phrase filter drops bad generations --")
    # The QUALITY GATE: synthetic Q&A pairs must be CONCRETE. Hedging
    # phrases ("I don't know", "the passage doesn't say", etc.) are
    # exactly the failure mode synthetic generation produces. Drill
    # enforces the filter is non-trivial.
    if "_HEDGE_PHRASES" not in src:
        print("x _HEDGE_PHRASES filter constant missing")
        return 1
    if "_has_hedge" not in src:
        print("x _has_hedge() filter function missing")
        return 1
    # Verify the filter actually drops representative bad outputs
    if not mod._has_hedge("I don't have enough information"):
        print("x _has_hedge() failed to flag 'I don't have...'")
        return 1
    if not mod._has_hedge("The passage does not specify the date"):
        print("x _has_hedge() failed to flag 'The passage does not...'")
        return 1
    if mod._has_hedge("The CEO of TimeWarner is Richard Parsons."):
        print("x _has_hedge() false-positive on a clean answer")
        return 1
    print("  ok: hedge-phrase filter — drops bad generations, keeps clean ones")

    print("-- 5. NEGATIVE: lazy httpx import (NOT at module top) --")
    # Cold-start invariant: callers who only check status() / is_available()
    # shouldn't pay the httpx import cost.
    lines_before_def = src[:src.find("def is_available")]
    if re.search(r"^import httpx\b", lines_before_def, re.MULTILINE):
        print("x httpx must NOT be imported at module top")
        return 1
    if re.search(r"^from httpx\b", lines_before_def, re.MULTILINE):
        print("x httpx must NOT be 'from'-imported at module top")
        return 1
    print("  ok: httpx lazy-imported inside _call_ollama")

    print("-- 6. NEGATIVE: 2-step prompting (question first, then answer) --")
    # Per the algorithm: ask for question, THEN ask for answer.
    # Single-step "give me Q+A" tends to produce mismatched pairs.
    # Drill enforces 2-step structure by checking for both a question
    # prompt and an answer prompt.
    if "Question:" not in src:
        print("x must have explicit 'Question:' prompt for step 1")
        return 1
    if "Answer:" not in src:
        print("x must have explicit 'Answer:' prompt for step 2")
        return 1
    # Both prompts must include the passage
    pair_idx = src.find("def generate_pair")
    pair_end = src.find("def generate_set", pair_idx)
    pair_body = src[pair_idx:pair_end]
    passage_count = pair_body.count("Passage:")
    if passage_count < 2:
        print(f"x both prompts must include Passage:; found {passage_count}")
        return 1
    print("  ok: 2-step prompting (question + answer; both grounded in passage)")

    print("-- 7. NEGATIVE: SKIP-output handling (model can decline cleanly) --")
    # Per the algorithm: prompts say "if you can't extract a clean
    # factual question, output exactly: SKIP". The handler must
    # recognize this signal and drop the pair (instead of treating
    # 'SKIP' as a question).
    if "SKIP" not in src:
        print("x must instruct model to use SKIP signal when declining")
        return 1
    # Both Q and A must check for SKIP
    skip_check_count = src.count('"SKIP"')
    if skip_check_count < 2:
        print(f"x must check for SKIP in both Q and A handler; found {skip_check_count}")
        return 1
    print("  ok: SKIP signal recognized + bad pairs dropped")

    print("-- 8. POSITIVE: status() reports stage=1 + Stage-2 wiring + quality gate --")
    os.environ["EVAL_SET_GENERATOR_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "available", "model", "max_pairs",
                "wiring_status", "next_stage", "quality_gate"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2")
        return 1
    if "AutoRAG" not in s["next_stage"] and "autorag" not in s["next_stage"].lower():
        print("x next_stage must mention AutoRAG (downstream consumer)")
        return 1
    if "synthetic" not in s["quality_gate"].lower() or "benchmark" not in s["quality_gate"].lower():
        print("x quality_gate must explicitly note 'synthetic ≠ benchmark'")
        return 1
    print("  ok: stage=1 + Stage-2 path + quality_gate disclaimer")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
