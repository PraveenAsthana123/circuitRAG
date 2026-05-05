#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for P1 #21 — ResearchAgent caching (eliminate duplicate fetches).

Includes negative assertions: different topics must NOT share a cache
slot; cache_max=0 must NOT cache; expired entries must NOT serve
stale data; cached values must NOT be mutated by callers (deep-copy).
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


def _bootstrap():
    pkg = "p1c_app"
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
    return res


def main() -> int:
    res = _bootstrap()

    print("-- 1. POSITIVE: ResearchAgent accepts cache_ttl_s + cache_max kwargs --")
    r = res.ResearchAgent(cache_ttl_s=10, cache_max=5)
    assert r._cache_ttl_s == 10
    assert r._cache_max == 5
    print("  ok: kwargs honored")

    print("-- 2. POSITIVE: same topic → second call is cache hit --")
    out1 = asyncio.run(r.research("topic_X"))
    assert out1["cache_hit"] is False
    out2 = asyncio.run(r.research("topic_X"))
    assert out2["cache_hit"] is True, "P1 #21 BROKEN: second call should hit cache"
    print(f"  ok: 1st={out1['cache_hit']}, 2nd={out2['cache_hit']}")

    print("-- 3. NEGATIVE: different topic → cache miss --")
    out3 = asyncio.run(r.research("topic_Y"))
    assert out3["cache_hit"] is False
    print("  ok: different topic → fresh fetch")

    print("-- 4. NEGATIVE: cache_max=0 disables caching --")
    r0 = res.ResearchAgent(cache_max=0)
    a = asyncio.run(r0.research("disabled"))
    b = asyncio.run(r0.research("disabled"))
    assert a["cache_hit"] is False
    assert b["cache_hit"] is False, "P1 #21 BROKEN: cache_max=0 should disable"
    print("  ok: cache_max=0 → always miss")

    print("-- 5. NEGATIVE: TTL expiry → fresh fetch --")
    r_ttl = res.ResearchAgent(cache_ttl_s=0.05, cache_max=10)
    a = asyncio.run(r_ttl.research("ttl_test"))
    assert a["cache_hit"] is False
    time.sleep(0.1)  # exceed TTL
    b = asyncio.run(r_ttl.research("ttl_test"))
    assert b["cache_hit"] is False, "P1 #21 BROKEN: TTL did not expire entry"
    print("  ok: TTL expired → fresh fetch")

    print("-- 6. POSITIVE: LRU eviction at cache_max --")
    r_lru = res.ResearchAgent(cache_max=3, cache_ttl_s=999)
    for i in range(5):
        asyncio.run(r_lru.research(f"topic_{i}"))
    # cache has 3 entries (LRU evicted oldest 2)
    assert len(r_lru._cache) == 3
    # topic_0 + topic_1 should be evicted; topic_2,3,4 in cache
    out = asyncio.run(r_lru.research("topic_0"))
    assert out["cache_hit"] is False, "topic_0 should have been evicted"
    print(f"  ok: cache size={len(r_lru._cache)} (cap=3); oldest evicted")

    print("-- 7. POSITIVE: clear_cache() returns count + drops all --")
    r2 = res.ResearchAgent()
    asyncio.run(r2.research("a"))
    asyncio.run(r2.research("b"))
    assert len(r2._cache) == 2
    n = r2.clear_cache()
    assert n == 2
    assert len(r2._cache) == 0
    print(f"  ok: clear_cache() evicted {n} entries")

    print("-- 8. NEGATIVE: cache returns COPY (mutation doesn't affect cached) --")
    r3 = res.ResearchAgent()
    asyncio.run(r3.research("immutable"))
    cached = asyncio.run(r3.research("immutable"))
    cached["summary"] = "MUTATED"  # mutate
    cached2 = asyncio.run(r3.research("immutable"))
    # cached2 should still have its original sources
    assert cached2["summary"] != "MUTATED", "P1 #21 BROKEN: mutation of returned dict affected cached value"
    print("  ok: cache returns deep-copy (mutation safe)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
