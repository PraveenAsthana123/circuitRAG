#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: run_gepa_empirical Stage-3 compile path (per ADR-024-style transition).

Locks the --mode=compile flag added 2026-05-05 that invokes
dspy.GEPA().compile() against the Gemma council program. The Stage-2
preflight default must remain a working fallback; --mode=compile is
the explicit operator opt-in for the expensive path.

Eight steps. Six negative. AST-only — no Ollama required.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "run_gepa_empirical.py"


def main() -> int:
    print("-- 1. POSITIVE: --mode=compile flag declared --")
    if not SCRIPT.exists():
        print(f"x {SCRIPT} missing")
        return 1
    src = SCRIPT.read_text(encoding="utf-8")
    if '"--mode"' not in src:
        print("x --mode flag must be declared")
        return 1
    if 'choices=["preflight", "compile"]' not in src:
        print("x --mode must enforce choices=preflight|compile")
        return 1
    if 'default="preflight"' not in src:
        print("x --mode default must be 'preflight' (Stage-2 stays the safe default)")
        return 1
    print("  ok: --mode preflight|compile, default preflight")

    print("-- 2. POSITIVE: --auto budget flag with 3 tiers (GEPA contract) --")
    if '"--auto"' not in src:
        print("x --auto flag must exist")
        return 1
    if 'choices=["light", "medium", "heavy"]' not in src:
        print("x --auto must enforce GEPA's 3 budget tiers")
        return 1
    print("  ok: --auto light|medium|heavy")

    print("-- 3. NEGATIVE: _stage3_compile is INVOKED only when mode=='compile' --")
    # If preflight unconditionally calls _stage3_compile, the EXPENSIVE
    # path runs by default — defeating the whole opt-in design.
    main_idx = src.find("def main()")
    if main_idx < 0:
        print("x main() must exist")
        return 1
    main_end = src.find("\nif __name__", main_idx)
    main_body = src[main_idx:main_end]
    if 'if args.mode == "compile":' not in main_body:
        print("x main() must guard _stage3_compile behind mode=='compile'")
        return 1
    if "return _stage3_compile(args, eval_set)" not in main_body:
        print("x main() must call _stage3_compile when mode=='compile'")
        return 1
    print("  ok: compile path gated behind explicit --mode=compile")

    print("-- 4. NEGATIVE: dspy.GEPA imports are LAZY (no cold-import on preflight) --")
    # Preflight should be cheap (<1s); pulling in dspy + GEPA adds
    # ~3-5s of cold-import. Drill enforces the imports live INSIDE
    # _stage3_compile, NOT at module top.
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            if mod == "dspy" or "dspy" in names or mod.startswith("dspy."):
                print("x dspy must NOT be imported at module level (preflight cold-start)")
                return 1
    # Verify the import is inside _stage3_compile
    s3_idx = src.find("def _stage3_compile")
    if s3_idx < 0:
        print("x _stage3_compile function must exist")
        return 1
    s3_end = src.find("\ndef main(", s3_idx)
    s3_body = src[s3_idx:s3_end]
    if "import dspy" not in s3_body:
        print("x _stage3_compile must lazy-import dspy")
        return 1
    if "from dspy.teleprompt import GEPA" not in s3_body:
        print("x _stage3_compile must lazy-import GEPA from dspy.teleprompt")
        return 1
    print("  ok: dspy + GEPA imports deferred to compile path")

    print("-- 5. NEGATIVE: §47 fail-safe — compile errors write report instead of raising --")
    # GEPA compile is heavy + flaky (Ollama timeouts, OOM, etc).
    # Drill enforces try/except around the .compile() call so failure
    # produces a structured report rather than crashing.
    if "try:" not in s3_body:
        print("x _stage3_compile must wrap GEPA + LM config in try/except")
        return 1
    failed_states = re.findall(r'"status":\s*"stage_3_(?:failed|compile_failed)[^"]*"', s3_body)
    if not failed_states:
        print("x _stage3_compile must record stage_3_failed_* status on exception")
        return 1
    print(f"  ok: §47 fail-safe — {len(failed_states)} failure-mode reports")

    print("-- 6. NEGATIVE: trainset built from question + ground_truth (eval_set shape) --")
    # The eval_set rows have question + ground_truth (not 'expected').
    # If we miswire the field name, GEPA optimizes against empty strings
    # → all metric scores 0 → no learning signal.
    if 'row.get("question"' not in s3_body:
        print("x trainset must read 'question' from eval_set rows")
        return 1
    if 'row.get("ground_truth"' not in s3_body:
        print("x trainset must read 'ground_truth' from eval_set rows")
        return 1
    if "dspy.Example(question=" not in s3_body:
        print("x trainset must build dspy.Example with question= field")
        return 1
    if '.with_inputs("question")' not in s3_body:
        print("x trainset rows must mark 'question' as input field")
        return 1
    print("  ok: trainset shape matches eval_set + DSPy Example contract")

    print("-- 7. NEGATIVE: Stage-2 preflight default UNCHANGED — no behavior shift --")
    # Existing operators running run_gepa_empirical.py with NO --mode
    # flag MUST get the preflight path (cheap, no LLM). Drill enforces
    # default=preflight and that the preflight branch still writes
    # the shape-report.
    if "Stage-2 GEPA preflight" not in src:
        print("x preflight branch must still log Stage-2 banner")
        return 1
    if '"status": "stage_2_preflight"' not in src:
        print("x preflight branch must still write stage_2_preflight report")
        return 1
    print("  ok: preflight default-path preserved")

    print("-- 8. POSITIVE: optimized_prompts persisted in stage_3_compiled report --")
    # Stage-4 wires the persisted prompts back into prompt_repo. The
    # compile report MUST carry the tuned instructions.
    if "optimized_prompts" not in s3_body:
        print("x compile report must include optimized_prompts dict")
        return 1
    if "named_predictors()" not in s3_body:
        print("x must extract via compiled.named_predictors() (DSPy contract)")
        return 1
    if 'getattr(sig, "instructions"' not in s3_body:
        print("x must extract sig.instructions per predictor")
        return 1
    if "Stage-4" not in s3_body:
        print("x compile report's next_stage must reference Stage-4 prompt_repo wire")
        return 1
    print("  ok: optimized prompts extracted + Stage-4 path documented")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
