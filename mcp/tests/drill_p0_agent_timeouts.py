#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for P0 #1 — own-timeouts on Research/Tester/Deployer agents."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"


def _bootstrap():
    pkg = "p0d_app"
    if pkg not in sys.modules:
        sys.modules[pkg] = ModuleType(pkg)
        sys.modules[pkg].__path__ = [str(SVC / "app")]
    sys.modules[f"{pkg}.llm_clients"] = ModuleType(f"{pkg}.llm_clients")
    sys.modules[f"{pkg}.llm_clients"].__path__ = [str(SVC / "app" / "llm_clients")]
    proto_spec = importlib.util.spec_from_file_location(f"{pkg}.llm_clients.protocol", SVC / "app" / "llm_clients" / "protocol.py")
    proto = importlib.util.module_from_spec(proto_spec); proto.__package__ = f"{pkg}.llm_clients"
    sys.modules[f"{pkg}.llm_clients.protocol"] = proto; proto_spec.loader.exec_module(proto)
    pool_spec = importlib.util.spec_from_file_location(f"{pkg}.llm_clients.pool", SVC / "app" / "llm_clients" / "pool.py")
    pool = importlib.util.module_from_spec(pool_spec); pool.__package__ = f"{pkg}.llm_clients"
    sys.modules[f"{pkg}.llm_clients.pool"] = pool; pool_spec.loader.exec_module(pool)
    init = sys.modules[f"{pkg}.llm_clients"]
    init.LlmClientPool = pool.LlmClientPool; init.AllBackendsUnavailable = pool.AllBackendsUnavailable
    init.LlmClientUnavailable = proto.LlmClientUnavailable; init.LlmCallResult = proto.LlmCallResult
    fake_mcp = ModuleType("mcp"); fake_mcp.MCPClient = type("S", (), {})
    sys.modules["mcp"] = fake_mcp
    fake_oll = ModuleType(f"{pkg}.ollama_client")
    class _O:
        async def generate(self, **k): return ""
        async def close(self): return None
    fake_oll.OllamaGenerateClient = _O
    sys.modules[f"{pkg}.ollama_client"] = fake_oll
    cat_spec = importlib.util.spec_from_file_location(f"{pkg}.model_catalog", SVC / "app" / "model_catalog.py")
    cat = importlib.util.module_from_spec(cat_spec); cat.__package__ = pkg
    sys.modules[f"{pkg}.model_catalog"] = cat; cat_spec.loader.exec_module(cat)
    rt_spec = importlib.util.spec_from_file_location(f"{pkg}.model_router", SVC / "app" / "model_router.py")
    rt = importlib.util.module_from_spec(rt_spec); rt.__package__ = pkg
    sys.modules[f"{pkg}.model_router"] = rt; rt_spec.loader.exec_module(rt)
    reg_spec = importlib.util.spec_from_file_location(f"{pkg}.agent_registry", SVC / "app" / "agent_registry.py")
    reg = importlib.util.module_from_spec(reg_spec); reg.__package__ = pkg
    sys.modules[f"{pkg}.agent_registry"] = reg; reg_spec.loader.exec_module(reg)
    agt_spec = importlib.util.spec_from_file_location(f"{pkg}.agents", SVC / "app" / "agents.py")
    agt = importlib.util.module_from_spec(agt_spec); agt.__package__ = pkg
    sys.modules[f"{pkg}.agents"] = agt; agt_spec.loader.exec_module(agt)
    res_spec = importlib.util.spec_from_file_location(f"{pkg}.research", SVC / "app" / "research.py")
    res = importlib.util.module_from_spec(res_spec); res.__package__ = pkg
    sys.modules[f"{pkg}.research"] = res; res_spec.loader.exec_module(res)
    tst_spec = importlib.util.spec_from_file_location(f"{pkg}.tester", SVC / "app" / "tester.py")
    tst = importlib.util.module_from_spec(tst_spec); tst.__package__ = pkg
    sys.modules[f"{pkg}.tester"] = tst; tst_spec.loader.exec_module(tst)
    dep_spec = importlib.util.spec_from_file_location(f"{pkg}.deployer", SVC / "app" / "deployer.py")
    dep = importlib.util.module_from_spec(dep_spec); dep.__package__ = pkg
    sys.modules[f"{pkg}.deployer"] = dep; dep_spec.loader.exec_module(dep)
    return res, tst, dep, agt, reg, rt, pool, proto


def main() -> int:
    res, tst, dep, agt, reg, rt, pool, proto = _bootstrap()

    class _HangingClient:
        backend = "claude_cli"
        tier = "tier_b"
        async def generate(self, **k):
            await asyncio.sleep(60.0)
            return None
        async def close(self): return None

    p = pool.LlmClientPool({"claude_cli": _HangingClient()})
    specs = reg.build_agent_specs(coder_model="x", reviewer_model="x", advisor_model="x", security_advisor_model="x")
    res_spec = next(s for s in specs if s.role_id == "researcher")

    print("-- 1. POSITIVE: ResearchAgent.research accepts research_timeout_s --")
    r = res.ResearchAgent(spec=res_spec, pool=p, route_fn=rt.route, role_id="researcher")
    start = time.monotonic()
    out = asyncio.run(r.research("hung topic", research_timeout_s=0.2))
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"P0 #1 BROKEN: research did not honor timeout; took {elapsed}s"
    assert "llm_unavailable" in out and "exceeded 0.2s" in out["llm_unavailable"]
    print(f"  ok: research timed out at {elapsed*1000:.0f}ms (cap=200ms)")

    print("-- 2. POSITIVE: TesterAgent.run_tests accepts tests_timeout_s --")
    tst_spec = next(s for s in specs if s.role_id == "tester"); t = tst.TesterAgent(spec=tst_spec, pool=p, route_fn=rt.route, role_id="tester")
    start = time.monotonic()
    out = asyncio.run(t.run_tests(worker_output="x", tests_timeout_s=0.2))
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"P0 #1 BROKEN: tester did not honor timeout; took {elapsed}s"
    assert "llm_unavailable" in out
    print(f"  ok: tester timed out at {elapsed*1000:.0f}ms")

    print("-- 3. POSITIVE: DeployerAgent.preflight accepts preflight_timeout_s --")
    dep_spec = next(s for s in specs if s.role_id == "deployer"); d = dep.DeployerAgent(spec=dep_spec, pool=p, route_fn=rt.route, role_id="deployer")
    start = time.monotonic()
    out = asyncio.run(d.preflight(diff_summary="x", preflight_timeout_s=0.2))
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"P0 #1 BROKEN: deployer did not honor timeout; took {elapsed}s"
    # Heuristic should still mark approval_required + auto_applied=False (§42 hard stop holds)
    assert out["auto_applied"] is False, "§42 BREACH on timeout"
    assert out["approval_required"] is True
    print(f"  ok: deployer timed out at {elapsed*1000:.0f}ms; §42 hard stop survives")

    print("-- 4. NEGATIVE: timeout fallback preserves §42 invariants --")
    # Even when deployer times out, auto_applied must NEVER be True.
    out = asyncio.run(d.preflight(diff_summary="dangerous", preflight_timeout_s=0.05))
    assert out["auto_applied"] is False
    assert out["approval_required"] is True
    print("  ok: §42 hard stop survives timeout path (auto_applied=False)")

    print("-- 5. POSITIVE: timeout values surface in error message --")
    out = asyncio.run(r.research("x", research_timeout_s=0.05))
    assert "0.05" in out["llm_unavailable"]
    print(f"  ok: timeout duration in error: '{out['llm_unavailable']}'")

    print()
    print("ALL 5 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
