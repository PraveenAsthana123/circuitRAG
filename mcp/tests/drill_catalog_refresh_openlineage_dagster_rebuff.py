#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: catalog refresh for OpenLineage, Dagster, RAGAS, Giskard, Rebuff.

NEGATIVE: catalog rows must not claim shipped without importable/runtime evidence.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "config" / "agentic_observability" / "oss_tooling_catalog.yaml"
sys.path.insert(0, str(REPO / "libs" / "py"))
sys.path.insert(0, str(REPO / "scripts"))


def tool_map() -> dict[str, dict]:
    doc = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    return {tool["name"]: tool for tool in doc["tools"]}


def importable(module: str) -> bool:
    try:
        importlib.import_module(module)
    except Exception:
        return False
    return True


def main() -> int:
    print("-- 1. POSITIVE: catalog loads and target tools exist --")
    tools = tool_map()
    targets = {"openlineage", "marquez", "dagster", "rebuff", "ragas", "giskard"}
    missing = targets - set(tools)
    if missing:
        print(f"x missing catalog tools: {sorted(missing)}")
        return 1
    print("  ok: all target tools present")

    print("-- 2. POSITIVE: target catalog rows use truthful statuses --")
    expected_status = {
        "openlineage": "planned",
        "marquez": "planned",
        "dagster": "planned",
        "ragas": "planned",
        "giskard": "planned",
        "rebuff": "shipped",
    }
    stale = {
        name: tools[name].get("status")
        for name, expected in expected_status.items()
        if tools[name].get("status") != expected
    }
    if stale:
        print(f"x stale statuses: {stale}; expected={expected_status}")
        return 1
    print("  ok: installed Rebuff remains shipped; not-installed rows are planned")

    print("-- 3. NEGATIVE: OpenLineage and Dagster are not marked shipped while absent --")
    absent = [name for name, module in {"openlineage": "openlineage", "dagster": "dagster"}.items() if not importable(module)]
    wrongly_shipped = [name for name in absent if tools[name].get("status") == "shipped"]
    if wrongly_shipped:
        print(f"x absent packages still marked shipped: {wrongly_shipped}")
        return 1
    print(f"  ok: absent packages are planned, not shipped: {absent}")

    print("-- 4. NEGATIVE: RAGAS and Giskard are not marked shipped while absent --")
    absent = [name for name, module in {"ragas": "ragas", "giskard": "giskard"}.items() if not importable(module)]
    wrongly_shipped = [name for name in absent if tools[name].get("status") == "shipped"]
    if wrongly_shipped:
        print(f"x absent packages still marked shipped: {wrongly_shipped}")
        return 1
    print(f"  ok: absent packages are planned, not shipped: {absent}")

    print("-- 5. NEGATIVE: Rebuff shipped via compatibility adapter, not raw import assumption --")
    from documind_core.rebuff_detector import prepare_langchain_vectorstore_compat

    prepare_langchain_vectorstore_compat()
    if not importable("rebuff"):
        print("x rebuff must import after compatibility shim")
        return 1
    if "compatibility shim" not in tools["rebuff"].get("evidence", ""):
        print(f"x rebuff evidence must mention compatibility shim: {tools['rebuff'].get('evidence')}")
        return 1
    print("  ok: Rebuff package drift handled by adapter")

    print("-- 6. NEGATIVE: target rows have evidence, not empty status flips --")
    for name in targets:
        if not tools[name].get("evidence"):
            print(f"x tool missing evidence: {name}")
            return 1
    print("  ok: target rows carry evidence")

    print("\nALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
