#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for B5 — DeployerAgent + §42 HARD STOP (Phase B5 scaffold).

Negative assertions (the locks):
  1. preflight() MUST return auto_applied=False (always — §42)
  2. preflight() MUST return approval_required=True
  3. heuristic deploy_safety defaults to 'review_required' (conservative)
  4. migration 011 deploy_records table has approval_id column (so a
     row CANNOT be persisted without an approval to point at)
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MIGRATION = SVC / "migrations" / "011_deploy_records.sql"


def _load(name, file, package=None):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap():
    pkg = "b5_app"
    if pkg not in sys.modules:
        sys.modules[pkg] = ModuleType(pkg)
        sys.modules[pkg].__path__ = [str(SVC / "app")]
    sys.modules[f"{pkg}.llm_clients"] = ModuleType(f"{pkg}.llm_clients")
    sys.modules[f"{pkg}.llm_clients"].__path__ = [str(SVC / "app" / "llm_clients")]
    _load(f"{pkg}.llm_clients.protocol", SVC / "app" / "llm_clients" / "protocol.py", f"{pkg}.llm_clients")
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
    return _load(f"{pkg}.deployer", SVC / "app" / "deployer.py", pkg)


def main() -> int:
    print("-- 1. POSITIVE: migration 011 exists --")
    assert MIGRATION.exists()
    sql = MIGRATION.read_text()
    for needle in ("deploy_records", "approval_id", "rollback_handle",
                   "ROW LEVEL SECURITY", "ON DELETE CASCADE"):
        assert needle in sql, f"missing in 011: {needle}"
    print("  ok: deploy_records + approval_id + rollback_handle")

    print("-- 2. POSITIVE: DeployerAgent loads --")
    dep = _bootstrap()
    agent = dep.DeployerAgent()
    print("  ok: DeployerAgent instantiable")

    print("-- 3. NEGATIVE: preflight NEVER auto-applies (§42) --")
    out = asyncio.run(agent.preflight(diff_summary="add column foo"))
    assert out["auto_applied"] is False, (
        f"§42 BREACH: deployer auto-applied! got {out}"
    )
    print("  ok: auto_applied=False (always)")

    print("-- 4. NEGATIVE: preflight ALWAYS requires approval --")
    assert out["approval_required"] is True
    print("  ok: approval_required=True")

    print("-- 5. NEGATIVE: heuristic deploy_safety is conservative --")
    assert out["deploy_safety"] in ("review_required", "block"), (
        f"heuristic must be conservative; got {out['deploy_safety']}"
    )
    print(f"  ok: heuristic safety='{out['deploy_safety']}'")

    print("-- 6. POSITIVE: target round-trips --")
    out_k8s = asyncio.run(agent.preflight(diff_summary="x", target="k8s"))
    assert out_k8s["target"] == "k8s"
    print("  ok: target field preserved")

    print()
    print("ALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
