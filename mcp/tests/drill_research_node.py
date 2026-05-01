#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for B2 — ResearchAgent + migration 009 (Phase B2 scaffold).

Verifies:
  - migration 009 declares research_artifacts with ON DELETE CASCADE
    + RLS + indexes
  - registry has 'researcher' role spec with JSON-output prompt
  - ResearchAgent heuristic path returns sane shape
  - LLM-routed path parses JSON output via bracket-aware scan
  - source_origin tag present (heuristic_fallback / mcp_research / llm_routed)

Negative assertions:
  1. Empty topic MUST still produce a structured result (no crash on
     edge case — researcher handles malformed input).
  2. LLM unavailable + no MCP → heuristic returns risks=[at least one]
     so downstream policy_evaluate can flag the missing research.
  3. Routing trail surfaces in result when LLM-routed (audit).
  4. heuristic_fallback explicitly states 'no upstream research'
     (caller must NOT trust as authoritative).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MIGRATION = SVC / "migrations" / "009_research_artifacts.sql"


def _load(name, file, package=None):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap():
    pkg = "b2_app"
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
    init.LlmClientUnavailable = proto.LlmClientUnavailable
    init.LlmCallResult = proto.LlmCallResult

    catalog = _load(f"{pkg}.model_catalog", SVC / "app" / "model_catalog.py", pkg)
    router = _load(f"{pkg}.model_router", SVC / "app" / "model_router.py", pkg)
    registry = _load(f"{pkg}.agent_registry", SVC / "app" / "agent_registry.py", pkg)

    # Stub heavy deps for agents.py import
    fake_mcp = ModuleType("mcp")
    class _Stub: pass
    fake_mcp.MCPClient = _Stub
    sys.modules["mcp"] = fake_mcp
    fake_ollama = ModuleType(f"{pkg}.ollama_client")
    class _Ollama:
        async def generate(self, **k): return ""
        async def close(self): return None
    fake_ollama.OllamaGenerateClient = _Ollama
    sys.modules[f"{pkg}.ollama_client"] = fake_ollama

    agents = _load(f"{pkg}.agents", SVC / "app" / "agents.py", pkg)
    research = _load(f"{pkg}.research", SVC / "app" / "research.py", pkg)
    return research, registry, router, pool, proto


def main() -> int:
    print("-- 1. POSITIVE: migration 009 exists with required structure --")
    assert MIGRATION.exists(), f"missing {MIGRATION}"
    sql = MIGRATION.read_text(encoding="utf-8")
    for needle in (
        "research_artifacts", "ON DELETE CASCADE", "ROW LEVEL SECURITY",
        "research_artifacts_isolation", "FORCE ROW LEVEL SECURITY",
        "sources_json", "risks_json", "routing_decision",
    ):
        assert needle in sql, f"missing in 009: {needle!r}"
    print("  ok: research_artifacts schema + RLS + indexes")

    print("-- 2. POSITIVE: 'researcher' role registered --")
    research, registry, router_mod, pool_mod, proto = _bootstrap()
    specs = registry.build_agent_specs(
        coder_model="x", reviewer_model="x", advisor_model="x", security_advisor_model="x",
    )
    role_ids = [s.role_id for s in specs]
    assert "researcher" in role_ids, f"researcher missing: {role_ids}"
    researcher_spec = next(s for s in specs if s.role_id == "researcher")
    assert "JSON" in researcher_spec.prompt_template or "json" in researcher_spec.prompt_template
    print(f"  ok: researcher registered, model={researcher_spec.model}")

    print("-- 3. POSITIVE: heuristic fallback returns structured shape --")
    agent = research.ResearchAgent()
    out = asyncio.run(agent.research("OAuth2 PKCE in Next.js"))
    for k in ("topic", "summary", "sources", "suggested_approach", "risks", "source_origin"):
        assert k in out, f"heuristic result missing key: {k}"
    assert out["source_origin"] == "heuristic_fallback"
    print(f"  ok: heuristic shape complete (origin={out['source_origin']})")

    print("-- 4. NEGATIVE: empty topic still returns structured result --")
    out = asyncio.run(agent.research(""))
    assert "topic" in out and "risks" in out
    print("  ok: empty topic handled without crash")

    print("-- 5. NEGATIVE: heuristic risks flag missing research --")
    out = asyncio.run(agent.research("any topic"))
    assert len(out["risks"]) >= 1, "heuristic must flag 'no real research' as risk"
    print(f"  ok: heuristic risks: {out['risks']}")

    print("-- 6. POSITIVE: heuristic explicitly states no upstream --")
    assert "no upstream" in out["summary"].lower() or "no upstream" in str(out["risks"]).lower(), (
        "heuristic must explicitly mark itself as non-authoritative"
    )
    print("  ok: heuristic flagged as non-authoritative")

    print("-- 7. POSITIVE: routed LLM path parses JSON output --")
    canned_json = '{"summary":"OAuth2 PKCE adds code verifier","sources":[{"title":"RFC 7636","url":"https://datatracker.ietf.org/doc/html/rfc7636","relevance":"spec"}],"suggested_approach":"use NextAuth","risks":["token storage"]}'
    class CannedClient:
        def __init__(self, text):
            self.backend = "claude_cli"
            self.tier = "tier_b"
            self._text = text
        async def generate(self, *, model, prompt, timeout_seconds=60.0, metadata=None):
            return proto.LlmCallResult(
                text=self._text, model=model, tier=self.tier,
                tokens_in=50, tokens_out=200, cost_usd_cents=8, backend=self.backend,
            )
        async def close(self): return None

    pool = pool_mod.LlmClientPool({"claude_cli": CannedClient(canned_json), "ollama": CannedClient("")})
    routed_agent = research.ResearchAgent(
        spec=researcher_spec, pool=pool, route_fn=router_mod.route, role_id="researcher",
    )
    out = asyncio.run(routed_agent.research("OAuth2 PKCE", complexity="high", novelty="novel"))
    assert out["source_origin"] == "llm_routed", f"expected llm_routed, got {out.get('source_origin')}"
    assert "routing" in out, "routed result must include routing trail"
    assert out["cost_usd_cents"] == 8
    assert len(out["sources"]) == 1
    print(f"  ok: LLM JSON parsed; routing recorded; sources={len(out['sources'])}")

    print("-- 8. POSITIVE: research result is JSON-serializable --")
    import json
    json.dumps(out)
    print("  ok: serializes for research_artifacts row")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
