#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for P0-A1 (InMemoryTaskStore bound) + P0-A2 (Strategist own timeout).

Two will-break-prod fixes:

  P0 #35 — InMemoryTaskStore unbounded memory leak in long-running dev mode
  P0 #1  — StrategistAgent had no own deadline; relied entirely on caller config

Negative assertions:
  - Adding 2× max_tasks → store size ≤ max_tasks (LRU eviction)
  - Strategist with hung pool → returns heuristic within timeout (NOT hangs)
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"


def _load_store():
    spec = importlib.util.spec_from_file_location("p0_store", SVC / "app" / "store.py")
    sys.modules.setdefault("p0_pkg", ModuleType("p0_pkg"))
    sys.modules["p0_pkg"].__path__ = [str(SVC / "app")]
    spec_models = importlib.util.spec_from_file_location("p0_pkg.models", SVC / "app" / "models.py")
    models = importlib.util.module_from_spec(spec_models)
    models.__package__ = "p0_pkg"
    sys.modules["p0_pkg.models"] = models
    spec_models.loader.exec_module(models)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "p0_pkg"
    sys.modules["p0_pkg.store"] = mod
    spec.loader.exec_module(mod)
    return mod, models


def _bootstrap_strategist():
    pkg = "p0a_app"
    if pkg not in sys.modules:
        sys.modules[pkg] = ModuleType(pkg)
        sys.modules[pkg].__path__ = [str(SVC / "app")]
    sys.modules[f"{pkg}.llm_clients"] = ModuleType(f"{pkg}.llm_clients")
    sys.modules[f"{pkg}.llm_clients"].__path__ = [str(SVC / "app" / "llm_clients")]
    proto_spec = importlib.util.spec_from_file_location(
        f"{pkg}.llm_clients.protocol",
        SVC / "app" / "llm_clients" / "protocol.py",
    )
    proto = importlib.util.module_from_spec(proto_spec)
    proto.__package__ = f"{pkg}.llm_clients"
    sys.modules[f"{pkg}.llm_clients.protocol"] = proto
    proto_spec.loader.exec_module(proto)
    pool_spec = importlib.util.spec_from_file_location(
        f"{pkg}.llm_clients.pool",
        SVC / "app" / "llm_clients" / "pool.py",
    )
    pool = importlib.util.module_from_spec(pool_spec)
    pool.__package__ = f"{pkg}.llm_clients"
    sys.modules[f"{pkg}.llm_clients.pool"] = pool
    pool_spec.loader.exec_module(pool)
    init = sys.modules[f"{pkg}.llm_clients"]
    init.LlmClientPool = pool.LlmClientPool
    init.AllBackendsUnavailable = pool.AllBackendsUnavailable
    init.LlmClientUnavailable = proto.LlmClientUnavailable
    init.LlmCallResult = proto.LlmCallResult
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
    sys.modules[f"{pkg}.model_catalog"] = cat
    cat_spec.loader.exec_module(cat)
    rt_spec = importlib.util.spec_from_file_location(f"{pkg}.model_router", SVC / "app" / "model_router.py")
    rt = importlib.util.module_from_spec(rt_spec); rt.__package__ = pkg
    sys.modules[f"{pkg}.model_router"] = rt
    rt_spec.loader.exec_module(rt)
    reg_spec = importlib.util.spec_from_file_location(f"{pkg}.agent_registry", SVC / "app" / "agent_registry.py")
    reg = importlib.util.module_from_spec(reg_spec); reg.__package__ = pkg
    sys.modules[f"{pkg}.agent_registry"] = reg
    reg_spec.loader.exec_module(reg)
    agt_spec = importlib.util.spec_from_file_location(f"{pkg}.agents", SVC / "app" / "agents.py")
    agt = importlib.util.module_from_spec(agt_spec); agt.__package__ = pkg
    sys.modules[f"{pkg}.agents"] = agt
    agt_spec.loader.exec_module(agt)
    return agt, reg, rt, pool, proto


def main() -> int:
    print("-- 1. POSITIVE: InMemoryTaskStore accepts max_tasks kwarg + uses OrderedDict --")
    store_mod, models_mod = _load_store()
    s = store_mod.InMemoryTaskStore(max_tasks=5)
    assert s.max_tasks == 5
    from collections import OrderedDict
    assert isinstance(s._items, OrderedDict)
    print("  ok: max_tasks=5; _items is OrderedDict")

    print("-- 2. NEGATIVE: adding 2× max_tasks evicts oldest (LRU) --")
    async def _hammer():
        for i in range(10):
            t = models_mod.TaskView(
                task_id=f"task_{i:03d}",
                tenant_id="acme",
                goal=f"goal {i}",
                status="created",
                risk_level="low",
            )
            await s.save(t)
    asyncio.run(_hammer())
    assert len(s._items) == 5, f"expected 5, got {len(s._items)}"
    # Oldest 5 evicted; remaining are 005-009
    keys = list(s._items.keys())
    assert keys[0] == "task_005", f"first key should be task_005 (oldest kept), got {keys[0]}"
    assert keys[-1] == "task_009"
    print(f"  ok: cap=5 honored; oldest 5 evicted; kept {keys}")

    print("-- 3. POSITIVE: re-saving an existing task moves to end (LRU) --")
    s = store_mod.InMemoryTaskStore(max_tasks=3)
    async def _lru():
        for i in range(3):
            await s.save(models_mod.TaskView(
                task_id=f"t{i}", tenant_id="acme", goal="x",
                status="created", risk_level="low",
            ))
        # Re-save t0 — should move to end.
        await s.save(models_mod.TaskView(
            task_id="t0", tenant_id="acme", goal="updated",
            status="created", risk_level="low",
        ))
        # Now save t3 — should evict t1 (now the oldest).
        await s.save(models_mod.TaskView(
            task_id="t3", tenant_id="acme", goal="x",
            status="created", risk_level="low",
        ))
    asyncio.run(_lru())
    keys = list(s._items.keys())
    assert "t0" in keys, "re-saved t0 should still be present"
    assert "t1" not in keys, "t1 should be evicted (now oldest after t0 moved)"
    print(f"  ok: re-saving moved t0 to end; t1 evicted as expected (keys={keys})")

    print("-- 4. POSITIVE: per-task run history bounded --")
    s = store_mod.InMemoryTaskStore(max_runs_per_task=3)
    async def _runs():
        for i in range(10):
            await s.save_task_run(models_mod.TaskRunView(
                run_id=f"r{i}", task_id="task_X", tenant_id="acme",
                phase="workflow", status="started",
            ))
    asyncio.run(_runs())
    runs = asyncio.run(s.list_task_runs("task_X"))
    assert len(runs) == 3, f"expected 3, got {len(runs)}"
    print(f"  ok: per-task runs bounded to 3 (was 10 saved)")

    # ----- P0 #1: Strategist own timeout -----
    print("-- 5. POSITIVE: StrategistAgent.classify accepts classify_timeout_s --")
    agt, reg, rt, pool, proto = _bootstrap_strategist()
    s = agt.StrategistAgent()
    # Heuristic-only; classify should accept the new kwarg.
    out = asyncio.run(s.classify("some routine task", classify_timeout_s=5.0))
    assert "overall_complexity" in out
    print(f"  ok: classify accepts classify_timeout_s kwarg")

    print("-- 6. NEGATIVE: hung pool → strategist returns heuristic within timeout --")
    # Build a stub pool that hangs forever.
    class _HangingClient:
        backend = "claude_cli"
        tier = "tier_b"
        async def generate(self, **k):
            await asyncio.sleep(60.0)  # hang
            return None
        async def close(self): return None

    p = pool.LlmClientPool({"claude_cli": _HangingClient()})
    specs = reg.build_agent_specs(coder_model="x", reviewer_model="x", advisor_model="x", security_advisor_model="x")
    spec = next(s for s in specs if s.role_id == "strategist")
    s_routed = agt.StrategistAgent(spec=spec, pool=p, route_fn=rt.route, role_id="strategist")

    start = time.monotonic()
    out = asyncio.run(s_routed.classify("hang test", classify_timeout_s=0.2))
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, (
        f"P0 #1 BROKEN: strategist did not enforce own timeout; took {elapsed:.2f}s"
    )
    assert "llm_unavailable" in out, (
        "timeout should surface as llm_unavailable in heuristic fallback"
    )
    assert out["overall_complexity"], "heuristic must produce a classification"
    print(f"  ok: hung pool → heuristic returned in {elapsed*1000:.0f}ms (timeout=200ms)")

    print("-- 7. POSITIVE: classify_timeout_s respects caller value --")
    out = asyncio.run(s_routed.classify("another hang", classify_timeout_s=0.05))
    assert "exceeded 0.05s" in out["llm_unavailable"]
    print("  ok: timeout value visible in error message")

    print()
    print("ALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
