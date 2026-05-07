#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Performance Agent layer (user-recommendation Gap #3).

Per CLAUDE.md §43 + §55. Locks the contract for the new 4th layer
in verifiability_framework. Foundation-only: presence-detection of
perf binaries (k6 / lighthouse / pytest-benchmark). Actual perf
execution against operator-configured targets is a future iter.

Eight steps. Six negative assertions covering each empirical
failure mode for a layered gate extension.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "verifiability_framework.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("verifiability_framework", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verifiability_framework"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: PERFORMANCE_GATE_BINARIES + budgets exported --")
    vf = _load()
    if not hasattr(vf, "PERFORMANCE_GATE_BINARIES"):
        print("x step 1: PERFORMANCE_GATE_BINARIES missing")
        return 1
    if not hasattr(vf, "PERFORMANCE_BUDGETS"):
        print("x step 1: PERFORMANCE_BUDGETS missing")
        return 1
    if not hasattr(vf, "_check_performance_binaries"):
        print("x step 1: _check_performance_binaries helper missing")
        return 1
    expected_bins = ("k6", "lighthouse")
    for b in expected_bins:
        if b not in vf.PERFORMANCE_GATE_BINARIES:
            print(f"x step 1: PERFORMANCE_GATE_BINARIES missing {b}")
            return 1
    print(f"  ok: gate binaries={vf.PERFORMANCE_GATE_BINARIES}; "
          f"budgets keys={sorted(vf.PERFORMANCE_BUDGETS.keys())}")

    print("-- 2. POSITIVE: budgets cover k6 / lighthouse / pytest-benchmark --")
    for budget_key in ("k6_p95_ms", "lighthouse_lcp_ms", "pytest_benchmark_p95_ms"):
        if budget_key not in vf.PERFORMANCE_BUDGETS:
            print(f"x step 2: missing budget for {budget_key}")
            return 1
        if not isinstance(vf.PERFORMANCE_BUDGETS[budget_key], float):
            print(f"x step 2: budget {budget_key} not float")
            return 1
    print("  ok: 3 budgets defined (k6 / lighthouse / pytest-benchmark)")

    print("-- 3. NEGATIVE: budgets are POSITIVE numbers (no zero/negative) --")
    for k, v in vf.PERFORMANCE_BUDGETS.items():
        if v <= 0:
            print(f"x step 3: budget {k}={v} not positive")
            return 1
    print("  ok: all 3 budgets > 0 (sanity check)")

    print("-- 4. POSITIVE: _check_performance_binaries returns ToolResult --")
    result = vf._check_performance_binaries(REPO)
    if not isinstance(result, vf.ToolResult):
        print(f"x step 4: returned {type(result).__name__}; expected ToolResult")
        return 1
    if result.tool != "performance":
        print(f"x step 4: tool name should be 'performance'; got {result.tool!r}")
        return 1
    print(f"  ok: ToolResult(tool='performance', ok={result.ok})")

    print("-- 5. NEGATIVE: missing perf binaries → ok=True (graceful skip, NOT failure) --")
    # Force-detect by temporarily patching shutil.which to return None
    import shutil as _sh
    original_which = _sh.which
    _sh.which = lambda binary: None  # type: ignore[assignment]
    try:
        # Need to also confirm pytest-benchmark file is absent
        # (it lives at .venv/bin/pytest-benchmark in the test repo)
        result = vf._check_performance_binaries(REPO)
        if not result.ok:
            print(f"x step 5: missing perf binaries should NOT fail gate; got ok={result.ok}")
            return 1
        if "skipped" not in result.output_truncated and "no perf binary" not in result.output_truncated:
            # The msg also depends on whether .venv/bin/pytest-benchmark exists.
            # Accept either "skipped" or "perf-ready".
            if "perf-ready" not in result.output_truncated:
                print(f"x step 5: unexpected output: {result.output_truncated[:100]}")
                return 1
    finally:
        _sh.which = original_which
    print("  ok: missing binaries → ok=True (graceful no-op; gate not weaponized)")

    print("-- 6. NEGATIVE: run_technical_verification accepts skip_performance kwarg --")
    import inspect
    sig = inspect.signature(vf.run_technical_verification)
    if "skip_performance" not in sig.parameters:
        print(f"x step 6: skip_performance kwarg missing; got params {list(sig.parameters)}")
        return 1
    print("  ok: skip_performance kwarg present in signature")

    print("-- 7. NEGATIVE: skip_performance=True OMITS the perf layer --")
    result = vf.run_technical_verification(
        skip_mypy=True, skip_pytest=True, skip_performance=True,
        timeout=10.0,
    )
    layer_names = [layer.tool for layer in result.layers]
    if "performance" in layer_names:
        print(f"x step 7: skip_performance=True still ran perf layer: {layer_names}")
        return 1
    if "ruff" not in layer_names:
        print(f"x step 7: ruff missing despite always-required: {layer_names}")
        return 1
    print("  ok: skip_performance=True omits perf layer; ruff still required")

    print("-- 8. POSITIVE: skip_performance=False (default) INCLUDES the layer --")
    result = vf.run_technical_verification(
        skip_mypy=True, skip_pytest=True, timeout=10.0,
    )
    layer_names = [layer.tool for layer in result.layers]
    if "performance" not in layer_names:
        print(f"x step 8: default run missing perf layer: {layer_names}")
        return 1
    print("  ok: default verification includes perf layer (4 layers total when no skips)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
