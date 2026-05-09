#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: LangGraph scenario performs a real runtime compile.

Prevents the scenario runner from drifting back to a static grep-only
check that sees `.compile(` in source but never imports LangGraph.

NEGATIVE: static source checks must not replace a real LangGraph compile smoke.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "scripts" / "scenario_batch_and_inference.py"


def require(src: str, needle: str, label: str) -> None:
    if needle not in src:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: scenario runner parses --")
    src = SCENARIO.read_text(encoding="utf-8")
    ast.parse(src)
    print("  ok: scenario runner is Python-valid")

    print("-- 2. POSITIVE: LangGraph scenario imports production builder --")
    require(src, "_langgraph_runtime_compile_smoke", "runtime compile helper")
    require(src, "sys.path.insert(0, str(REPO))", "repo-root import precedence")
    require(src, "from app.langgraph_flow import build_graph", "production build_graph import")
    require(src, "from app.models import AgenticPolicyView", "policy model import")
    print("  ok: runtime helper imports production graph builder")

    print("-- 3. POSITIVE: scenario compiles full optional-node graph --")
    for needle in ("strategist=_Strategist()", "researcher=_Researcher()", "tester=_Tester()", "deployer=_Deployer()"):
        require(src, needle, needle)
    require(src, "compiled.get_graph()", "compiled graph introspection")
    require(src, "runtime_compile_passed", "runtime compile evidence")
    print("  ok: full optional-node graph compile is evidenced")

    print("-- 4. NEGATIVE: PASS must require runtime compile --")
    require(src, "passed = static_ok and runtime_compile[\"runtime_compile_passed\"]", "strict pass condition")
    if '"status": "PASS" if (has_state_graph and has_add_node and has_compile) else "FAIL"' in src:
        raise AssertionError("LangGraph scenario still passes on static source checks only")
    print("  ok: scenario PASS requires runtime compile")

    print("\nALL 4 LANGGRAPH RUNTIME SCENARIO STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
