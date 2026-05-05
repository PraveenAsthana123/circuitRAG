#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: autorag_optimizer env-only gate (per §43 + §47 + §56).

Locks the contract change made 2026-05-05: search_config_space() is
gated by env flag ALONE — autorag-package-installed is informational
only. Reason: autorag pins matplotlib<3.7 (configparser.SafeConfigParser
removed in py3.12+); requiring it would block py3.13 operators from
running their own empirical search, violating §47 fail-safe.

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OPT = REPO / "scripts" / "autorag_optimizer.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: 3 gate-related surfaces present --")
    if not OPT.exists():
        print(f"x {OPT} missing")
        return 1
    src = OPT.read_text(encoding="utf-8")
    os.environ["AUTORAG_OPTIMIZER_ENABLED"] = "1"
    mod, spec = _load_module(OPT)
    for name in ("is_env_enabled", "is_package_installed", "is_available"):
        if not hasattr(mod, name):
            print(f"x autorag_optimizer.{name} missing")
            return 1
    print("  ok: 3 gate surfaces present (is_env_enabled / is_package_installed / is_available)")

    print("-- 2. NEGATIVE: env-flag controls search regardless of pkg state --")
    # The whole point of the split: env flag alone gates the search.
    # Drill enforces that is_env_enabled returns True with just env set.
    os.environ["AUTORAG_OPTIMIZER_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    if not mod.is_env_enabled():
        print("x is_env_enabled must be True when AUTORAG_OPTIMIZER_ENABLED=1")
        return 1
    if not mod.is_available():
        print("x is_available (alias) must mirror is_env_enabled")
        return 1
    print("  ok: env flag alone gates the search")

    print("-- 3. NEGATIVE: package-installed probe is INDEPENDENT of env --")
    # is_package_installed must NOT consult the env flag — it's purely
    # an import probe. Drill enforces this by setting env=0 and checking
    # is_package_installed responds based on actual import state only.
    os.environ.pop("AUTORAG_OPTIMIZER_ENABLED", None)
    spec.loader.exec_module(mod)
    pkg_state = mod.is_package_installed()
    # Independent of env: state should be the same whether env is set or not
    os.environ["AUTORAG_OPTIMIZER_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    if mod.is_package_installed() != pkg_state:
        print("x is_package_installed must be independent of env flag")
        return 1
    print(f"  ok: package probe independent of env (current state: {pkg_state})")

    print("-- 4. NEGATIVE: search_config_space gated by ENV ONLY (not package) --")
    # Verify the source: search_config_space calls is_env_enabled (or
    # is_available), NOT is_package_installed. If it called the latter,
    # py3.13 operators would be blocked.
    sce_idx = src.find("def search_config_space(")
    sce_end = src.find("\n\ndef ", sce_idx + 100)
    if sce_end < 0:
        sce_end = sce_idx + 3000
    sce_body = src[sce_idx:sce_end]
    if "if not is_env_enabled" not in sce_body and "if not is_available" not in sce_body:
        print("x search_config_space must gate on is_env_enabled / is_available, not is_package_installed")
        return 1
    if "is_package_installed" in sce_body and "if not is_package_installed" in sce_body:
        print("x search_config_space must NOT gate on is_package_installed")
        return 1
    print("  ok: search gated by env flag only")

    print("-- 5. NEGATIVE: default-deny preserved — env unset → search RAISES --")
    os.environ.pop("AUTORAG_OPTIMIZER_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.search_config_space(
            eval_set=[],
            run_rag=lambda q, c: {"answer": ""},
        )
    except mod.AutoRAGOptimizerDisabled as exc:
        raised = True
        if "AUTORAG_OPTIMIZER_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x search_config_space must raise when env unset")
        return 1
    print("  ok: default-deny preserved")

    print("-- 6. NEGATIVE: error message documents the OPTIONAL pkg install --")
    # Operators reading the error must know that pkg install is optional.
    # Drill enforces the message wording (regression guard against future
    # 'helpfully' adding 'and ensure autorag is installed' back).
    raise_idx = src.find("raise AutoRAGOptimizerDisabled(")
    if raise_idx < 0:
        print("x raise AutoRAGOptimizerDisabled site missing")
        return 1
    raise_end = src.find(")", raise_idx + 30)
    raise_block = src[raise_idx:raise_end + 1]
    if "OPTIONAL" not in raise_block and "optional" not in raise_block:
        print(f"x error message must clarify autorag pkg is OPTIONAL; block={raise_block!r}")
        return 1
    if "and ensure autorag is installed" in raise_block:
        print("x error message must NOT say 'and ensure autorag is installed' (false requirement)")
        return 1
    print("  ok: error message correctly documents optional pkg state")

    print("-- 7. POSITIVE: status() reports BOTH enabled_env AND package_installed --")
    os.environ["AUTORAG_OPTIMIZER_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    st = mod.status()
    for k in ("enabled_env", "available", "package_installed"):
        if k not in st:
            print(f"x status() missing field {k}")
            return 1
    if not isinstance(st["package_installed"], bool):
        print(f"x package_installed must be bool; got {type(st['package_installed'])}")
        return 1
    print("  ok: status surfaces both env + package state")

    print("-- 8. NEGATIVE: contract docstrings cite the matplotlib/py3.13 reason --")
    # Drill locks the WHY: future refactors might 're-tighten' the gate
    # without realizing the matplotlib pin is still broken. The
    # docstring must record the reason.
    env_idx = src.find("def is_env_enabled")
    env_end = src.find('"""', src.find('"""', env_idx) + 3) + 3
    env_doc = src[env_idx:env_end]
    if "matplotlib" not in env_doc and "configparser" not in env_doc and "py3.1" not in env_doc and "Python 3.1" not in env_doc:
        print("x is_env_enabled docstring must cite the matplotlib/py3.13 reason")
        return 1
    print("  ok: docstring records the empirical reason for the split")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
