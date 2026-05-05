#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-2 promotion-gate wire into run_autorag_empirical (per §43 + §56).

Locks the additive-only wire that gates best_config.json writes
when PROMOTION_GATE_ENABLED=1. Failure to gate = legacy 'highest wins'
write happens.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts" / "run_autorag_empirical.py"
GATE = REPO / "scripts" / "promote_best_config.py"


def main() -> int:
    print("-- 1. POSITIVE: runner imports promote_best_config getters --")
    if not RUNNER.exists():
        print(f"x {RUNNER} missing")
        return 1
    src = RUNNER.read_text(encoding="utf-8")
    if "from promote_best_config import" not in src:
        print("x runner must import from promote_best_config")
        return 1
    print("  ok: gate imported")

    print("-- 2. NEGATIVE: import is INSIDE main() (lazy, not module-level) --")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            if mod == "promote_best_config" or "promote_best_config" in names:
                print("x promote_best_config must NOT be imported at module level")
                return 1
    print("  ok: lazy import inside main()")

    print("-- 3. NEGATIVE: env-flag gate enforced (PROMOTION_GATE_ENABLED) --")
    if "PROMOTION_GATE_ENABLED" not in src:
        print("x runner must check PROMOTION_GATE_ENABLED env")
        return 1
    print("  ok: env-flag gated")

    print("-- 4. NEGATIVE: gate-disabled → LEGACY blind-write path runs --")
    # The whole point of Stage-2 additivity: callers WITHOUT the env
    # flag MUST keep getting the legacy write behavior. The drill
    # verifies the else-branch (no-gate fall-through) still writes
    # best_config.json the old way.
    if "if not gate_used:" not in src:
        print("x runner must have 'if not gate_used:' guard for legacy path")
        return 1
    if "best_dict = {" not in src:
        print("x legacy path must still construct best_dict")
        return 1
    if "json.dump(best_dict, f, indent=2)" not in src:
        print("x legacy path must still write best_dict to args.best")
        return 1
    print("  ok: gate-disabled → legacy write path preserved")

    print("-- 5. NEGATIVE: §47 fail-safe — gate import error falls back to legacy --")
    block_idx = src.find("Stage-2 promotion-gate wire")
    if block_idx < 0:
        print("x promotion-gate wire marker missing")
        return 1
    block_end = src.find("if not gate_used:", block_idx)
    block = src[block_idx:block_end]
    if "try:" not in block:
        print("x gate wire must wrap import + call in try/except")
        return 1
    if "except Exception" not in block:
        print("x must catch generic Exception (fail-safe)")
        return 1
    if "gate_used = False" not in block:
        print("x exception path must reset gate_used=False to trigger legacy write")
        return 1
    print("  ok: gate import error falls back to legacy write path")

    print("-- 6. NEGATIVE: gate REJECTION leaves prior best_config UNTOUCHED --")
    # If the gate rejects, run_autorag_empirical MUST NOT silently
    # fall through to legacy blind-write. gate_used=True even on
    # rejection prevents the legacy path from running.
    # Verify: when promote() is called and gate_used=True, the legacy
    # branch is skipped regardless of decision.promoted.
    gate_block = src[src.find("if is_available():"):src.find("if not gate_used:")]
    if "gate_used = True" not in gate_block:
        print("x gate_used=True must be set BEFORE checking decision.promoted")
        return 1
    # Specifically: gate_used=True is set BEFORE the decision.promoted
    # check. So even on rejection, legacy doesn't run. Drill enforces
    # the structural ordering.
    promoted_check = gate_block.find("if not decision.promoted:")
    set_used_idx = gate_block.find("gate_used = True")
    if promoted_check >= 0 and set_used_idx >= promoted_check:
        print("x gate_used=True must be set BEFORE 'if not decision.promoted'")
        return 1
    print("  ok: gate rejection blocks legacy fallback")

    print("-- 7. POSITIVE: ast-valid + history path derived from best_path --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x syntax error after Stage-2 wire: {exc}")
        return 1
    if "best_config_history.jsonl" not in src:
        print("x must derive history_path from best_path parent")
        return 1
    print("  ok: ast-valid; history.jsonl path derived")

    print("-- 8. NEGATIVE: promote_best_config UNCHANGED (no reverse import) --")
    gate_src = GATE.read_text(encoding="utf-8")
    rev = re.compile(
        r"^\s*(from\s+run_autorag|import\s+run_autorag|"
        r"from\s+autorag_optimizer|import\s+autorag_optimizer)",
        re.MULTILINE,
    )
    if rev.search(gate_src):
        print("x promote_best_config imports the runner (cycle risk)")
        return 1
    print("  ok: gate source clean; no cycle introduced")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
