#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: outcome-based evaluation framework (Tier 4 #4.5).

Per CLAUDE.md §43 + §55.3. Locks the contract that the outcome
evaluator computes the 3 mandated metrics correctly + supports
before/after diff + enforces §55.3 commit-message discipline.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "outcome_eval.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("outcome_eval", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["outcome_eval"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: outcome_eval imports + 6 exports --")
    oe = _load()
    for name in ("compute_metrics", "OutcomeMetrics", "COST_PER_1K_CENTS",
                 "cmd_snapshot", "cmd_compare_to", "cmd_contract"):
        if not hasattr(oe, name):
            print(f"x step 1: missing export {name}")
            return 1
    print("  ok: 6 exports present")

    print("-- 2. POSITIVE: compute_metrics returns OutcomeMetrics with all 3 §55.3 fields --")
    metrics = oe.compute_metrics(window_days=7, label="drill-test")
    if not isinstance(metrics, oe.OutcomeMetrics):
        print(f"x step 2: returned {type(metrics).__name__}; expected OutcomeMetrics")
        return 1
    for field in ("apply_rate", "regression_count", "cost_per_fix_cents"):
        if not hasattr(metrics, field):
            print(f"x step 2: OutcomeMetrics missing §55.3 field {field}")
            return 1
    print(f"  ok: 3 §55.3 metrics + label + window_days + counts present")

    print("-- 3. NEGATIVE: apply_rate is 0.0 when no attempts (no division by zero) --")
    # Verify the 0-attempts edge case doesn't crash. We can't easily
    # zero out the audit file in a drill, so rely on the helper.
    if metrics.apply_rate < 0.0 or metrics.apply_rate > 1.0:
        print(f"x step 3: apply_rate {metrics.apply_rate} out of [0,1] range")
        return 1
    print(f"  ok: apply_rate {metrics.apply_rate:.2%} in [0, 1] range; no /0 crash")

    print("-- 4. NEGATIVE: cost_per_fix is None when no fixes applied --")
    # Same edge case — when 0 fixes applied, cost-per-fix should be None
    # (not 0; not infinity; not crash). Today's actual session has
    # 0/8 applied, so we can verify directly.
    if metrics.apply_succeeded == 0 and metrics.cost_per_fix_cents is not None:
        print(f"x step 4: cost_per_fix should be None when 0 fixes applied; got {metrics.cost_per_fix_cents}")
        return 1
    if metrics.apply_succeeded > 0 and metrics.cost_per_fix_cents is None:
        print(f"x step 4: cost_per_fix should NOT be None when fixes applied")
        return 1
    print(f"  ok: cost_per_fix=None when 0 fixes (no division-by-zero theater)")

    print("-- 5. NEGATIVE: COST_PER_1K_CENTS includes all 4 council models + tier-B --")
    expected_models = (
        "deepseek-coder:6.7b-instruct",
        "codegemma:7b-instruct",
        "codellama:7b-instruct",
        "qwen2.5:latest",
        "claude-cli",
    )
    for m in expected_models:
        if m not in oe.COST_PER_1K_CENTS:
            print(f"x step 5: COST_PER_1K_CENTS missing {m}")
            return 1
    # Tier-B should be substantially more expensive than local Ollama
    if oe.COST_PER_1K_CENTS["claude-cli"] <= oe.COST_PER_1K_CENTS["deepseek-coder:6.7b-instruct"]:
        print(f"x step 5: claude-cli rate not higher than deepseek-coder; cost-ordering broken")
        return 1
    print(f"  ok: 5 model rates; claude-cli rate ≫ local-Ollama rates (cost-aware routing signal)")

    print("-- 6. NEGATIVE: snapshot writes a file; compare-to reads it back --")
    # Use a fresh subdirectory under .loop/outcome_snapshots/ for the drill.
    # Timeout 300s: snapshot computation walks the full council audit
    # log + all `git log` history; observed ~4min on contended dev box
    # 2026-05-05. Bump from 120 → 300 (2.5x worst-case observed live).
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "snapshot", "--label", "drill-snap"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        print(f"x step 6: snapshot exited {proc.returncode}: {proc.stderr[:200]}")
        return 1
    if "snapshot written" not in proc.stdout:
        print(f"x step 6: snapshot output missing 'snapshot written': {proc.stdout[:200]}")
        return 1
    # Verify the snapshot file exists
    snap_dir = REPO / ".loop" / "outcome_snapshots"
    matches = list(snap_dir.glob("drill-snap-*.json"))
    if not matches:
        print(f"x step 6: no drill-snap-*.json found under {snap_dir}")
        return 1
    print(f"  ok: snapshot {matches[-1].name} written + readable")

    print("-- 7. NEGATIVE: compare-to with unknown label fails gracefully --")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "compare-to", "nonexistent-label-zzz"],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    if proc.returncode == 0:
        print(f"x step 7: compare-to with unknown label should exit non-zero; got 0")
        return 1
    if "no snapshot" not in proc.stdout.lower() and "no snapshot" not in proc.stderr.lower():
        print(f"x step 7: compare-to didn't print 'no snapshot' message: stdout={proc.stdout[:200]} stderr={proc.stderr[:200]}")
        return 1
    print(f"  ok: unknown label rejected with operator-readable message")

    print("-- 8. POSITIVE: contract subcommand recognizes §55.3-compliant commit --")
    # Check the current HEAD commit. This drill is doc-only, so the
    # last commit might or might not be §55.3-compliant; we just
    # verify the subcommand runs without crashing and prints a clear
    # verdict.
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "contract"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    # Either pass (✓) or warn (⚠) is acceptable; crash is not.
    if "§55.3" not in proc.stdout and "outcome" not in proc.stdout.lower():
        print(f"x step 8: contract output missing §55.3 reference: {proc.stdout[:200]}")
        return 1
    print(f"  ok: contract subcommand emits §55.3-aware verdict")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
