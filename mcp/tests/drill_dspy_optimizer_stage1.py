#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: DSPy 3 + GEPA optimizer Stage-1 (per §43 + §56).

Locks the DSPy 3 wrapper around the Gemma Agent Council:

  - dspy_optimizer.py exists as a SEPARATE module (not modifying council)
  - 5 contract surfaces: is_available, status, get_council_program,
    make_simple_metric, DSPyOptimizerDisabled
  - Default-deny via DSPY_OPTIMIZER_ENABLED=1
  - dspy 3.x installed + GEPA available via dspy.teleprompt.GEPA
  - Lazy dspy import (NOT loaded at module top — keeps cold-start fast)
  - get_council_program wraps gemma_agent_council.run_council
  - Existing council source UNCHANGED (purely additive)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DSPY_OPT = REPO / "scripts" / "dspy_optimizer.py"
COUNCIL = REPO / "scripts" / "gemma_agent_council.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: dspy_optimizer.py exists + non-trivial size --")
    if not DSPY_OPT.exists():
        print(f"x {DSPY_OPT} missing")
        return 1
    src = DSPY_OPT.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x dspy_optimizer too short ({len(src)} chars)")
        return 1
    print(f"  ok: dspy_optimizer present ({len(src)} chars)")

    print("-- 2. NEGATIVE: gemma_agent_council source UNCHANGED (additive only) --")
    if COUNCIL.exists():
        council_src = COUNCIL.read_text(encoding="utf-8")
        if "dspy_optimizer" in council_src or "DSPyCouncil" in council_src:
            print("x gemma_agent_council has DSPy reference — Stage-1 must be additive")
            return 1
    print("  ok: council source unchanged")

    print("-- 3. POSITIVE: dspy 3.x installed + GEPA available --")
    try:
        import dspy
    except ImportError:
        print("x dspy not installed")
        return 1
    if not dspy.__version__.startswith("3"):
        print(f"x dspy must be 3.x; got {dspy.__version__}")
        return 1
    if not hasattr(dspy.teleprompt, "GEPA"):
        print("x GEPA optimizer must be available via dspy.teleprompt.GEPA")
        return 1
    print(f"  ok: dspy {dspy.__version__} + GEPA")

    print("-- 4. POSITIVE: 5 contract surfaces exported --")
    os.environ.pop("DSPY_OPTIMIZER_ENABLED", None)
    mod, spec = _load_module(DSPY_OPT)
    for name in ("is_available", "status", "get_council_program",
                 "make_simple_metric", "DSPyOptimizerDisabled"):
        if not hasattr(mod, name):
            print(f"x dspy_optimizer.{name} missing")
            return 1
    print("  ok: 5 surfaces exported")

    print("-- 5. NEGATIVE: default-deny — get_council_program raises when env unset --")
    os.environ.pop("DSPY_OPTIMIZER_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.get_council_program()
    except mod.DSPyOptimizerDisabled as exc:
        raised = True
        if "DSPY_OPTIMIZER_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x get_council_program must raise when flag off")
        return 1
    # Same for make_simple_metric
    raised_m = False
    try:
        mod.make_simple_metric()
    except mod.DSPyOptimizerDisabled:
        raised_m = True
    if not raised_m:
        print("x make_simple_metric must raise when flag off")
        return 1
    print("  ok: both gated functions fail closed")

    print("-- 6. NEGATIVE: lazy dspy import (NOT at module top) --")
    # dspy is a heavy import (loads litellm, mlflow, etc). Module top
    # must stay light so cold-start callers don't pay the cost.
    lines_before_def = src[:src.find("def is_available")]
    if re.search(r"^import dspy\b", lines_before_def, re.MULTILINE):
        print("x dspy must NOT be imported at module top")
        return 1
    if re.search(r"^from dspy\b", lines_before_def, re.MULTILINE):
        print("x dspy must NOT be 'from'-imported at module top")
        return 1
    print("  ok: dspy lazy-loaded inside is_available / get_council_program")

    print("-- 7. NEGATIVE: status() reflects DSPy + GEPA availability --")
    os.environ["DSPY_OPTIMIZER_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "available", "lm_model", "ollama_host",
                "wraps", "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "dspy_version" not in s:
        print("x status must surface dspy_version when available")
        return 1
    if not s.get("gepa_available"):
        print("x status must report gepa_available=True (DSPy 3 has GEPA)")
        return 1
    if "gemma_agent_council" not in s["wraps"]:
        print(f"x status.wraps must reference gemma_agent_council; got {s['wraps']!r}")
        return 1
    print("  ok: status reports stage=1 + dspy_version + gepa_available + wraps council")

    print("-- 8. POSITIVE: status next_stage describes GEPA wiring path --")
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2")
        return 1
    if "GEPA" not in s["next_stage"]:
        print("x next_stage must mention GEPA (the optimization target)")
        return 1
    if "eval set" not in s["next_stage"].lower() and "eval_set" not in s["next_stage"].lower():
        print("x next_stage must mention eval set curation (Stage-2 prereq)")
        return 1
    if "prompt registry" not in s["next_stage"].lower():
        print("x next_stage must mention prompt registry (where optimized prompts land)")
        return 1
    print("  ok: next_stage path covers eval-set + GEPA + prompt-registry persistence")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
