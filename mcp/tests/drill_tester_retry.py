#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for B4 — TesterAgent + migration 010 (Phase B4 scaffold).

Negative assertions:
  1. Heuristic MUST default passed=False ('unknown' is NEVER 'green')
  2. failed_json MUST be JSONB list (parseable, not arbitrary text)
  3. test_results table FK CASCADE on agent_tasks (no orphan rows)
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MIGRATION = SVC / "migrations" / "010_test_results.sql"


def _load(name, file, package=None):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap():
    pkg = "b4_app"
    if pkg not in sys.modules:
        sys.modules[pkg] = ModuleType(pkg)
        sys.modules[pkg].__path__ = [str(SVC / "app")]
    sys.modules[f"{pkg}.llm_clients"] = ModuleType(f"{pkg}.llm_clients")
    sys.modules[f"{pkg}.llm_clients"].__path__ = [str(SVC / "app" / "llm_clients")]
    proto = _load(f"{pkg}.llm_clients.protocol", SVC / "app" / "llm_clients" / "protocol.py", f"{pkg}.llm_clients")
    pool = _load(f"{pkg}.llm_clients.pool", SVC / "app" / "llm_clients" / "pool.py", f"{pkg}.llm_clients")
    init = sys.modules[f"{pkg}.llm_clients"]
    init.LlmClientPool = pool.LlmClientPool
    init.AllBackendsUnavailable = pool.AllBackendsUnavailable
    fake_mcp = ModuleType("mcp"); fake_mcp.MCPClient = type("S", (), {})
    sys.modules["mcp"] = fake_mcp
    fake_oll = ModuleType(f"{pkg}.ollama_client")
    class _O:
        async def generate(self, **k): return ""
        async def close(self): return None
    fake_oll.OllamaGenerateClient = _O
    sys.modules[f"{pkg}.ollama_client"] = fake_oll
    _load(f"{pkg}.model_catalog", SVC / "app" / "model_catalog.py", pkg)
    _load(f"{pkg}.model_router", SVC / "app" / "model_router.py", pkg)
    _load(f"{pkg}.agent_registry", SVC / "app" / "agent_registry.py", pkg)
    _load(f"{pkg}.agents", SVC / "app" / "agents.py", pkg)
    return _load(f"{pkg}.tester", SVC / "app" / "tester.py", pkg)


def main() -> int:
    print("-- 1. POSITIVE: migration 010 exists --")
    assert MIGRATION.exists()
    sql = MIGRATION.read_text()
    for needle in ("test_results", "ON DELETE CASCADE", "ROW LEVEL SECURITY",
                   "passed", "failed_json", "coverage_pct", "retry_count"):
        assert needle in sql, f"missing in 010: {needle}"
    print("  ok: test_results schema + RLS")

    print("-- 2. NEGATIVE: ON DELETE CASCADE on task_id (no orphans) --")
    import re
    pattern = r"task_id\s+TEXT\s+NOT\s+NULL\s+REFERENCES\s+orchestration\.agent_tasks\(task_id\)\s+ON\s+DELETE\s+CASCADE"
    assert re.search(pattern, sql, flags=re.IGNORECASE), (
        "task_id FK with ON DELETE CASCADE not found"
    )
    print("  ok: cascade prevents orphan test_results rows")

    print("-- 3. POSITIVE: TesterAgent loads --")
    tester = _bootstrap()
    agent = tester.TesterAgent()
    print("  ok: TesterAgent instantiable with no clients")

    print("-- 4. NEGATIVE: heuristic defaults passed=False --")
    out = asyncio.run(agent.run_tests(worker_output="some code"))
    assert out["passed"] is False, (
        f"COST GUARD: heuristic must default passed=False (unknown != green); got {out}"
    )
    print(f"  ok: heuristic passed=False ({out['source_origin']})")

    print("-- 5. POSITIVE: failed is a list (JSON-friendly) --")
    assert isinstance(out["failed"], list)
    print(f"  ok: failed={out['failed']}")

    print("-- 6. POSITIVE: result includes runner field --")
    assert out["runner"] == "pytest"
    out2 = asyncio.run(agent.run_tests(worker_output="x", runner="jest"))
    assert out2["runner"] == "jest"
    print("  ok: runner field round-trips")

    print()
    print("ALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
