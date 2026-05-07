#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for B1 — StrategistAgent classification (Phase B1).

Verifies StrategistAgent classifies tasks correctly via:
  - heuristic fallback (no LLM wired) — proves the conservative defaults
  - LLM JSON parsing (parses code-fence-wrapped JSON, extracts fields)

Negative assertions:
  1. Goal containing 'deploy' MUST classify as complexity='high'
     (per registry STRICT RULE 1: deploy never trivial).
  2. Goal containing 'auth' or 'oauth' MUST classify as novelty='novel'
     (per registry STRICT RULE 2).
  3. Unparseable LLM output MUST NOT crash — falls back to heuristic
     and records 'llm_text_unparseable' for forensics.
  4. Routine-token goal MUST NOT escalate to high+novel (cost guard
     double-check at the agent layer).

Resource tag = readonly. Imports the module directly with stub LLM
clients; no Ollama, no Postgres.

Why this drill: B1 is the brain. If the strategist mis-classifies, every
downstream cost decision is wrong — over-routing burns budget,
under-routing produces low-quality work.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"


def _load(name: str, file: Path, package: str | None = None) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap():
    pkg_name = "b1_app"
    if pkg_name not in sys.modules:
        sys.modules[pkg_name] = ModuleType(pkg_name)
        sys.modules[pkg_name].__path__ = [str(SVC / "app")]
    sys.modules[f"{pkg_name}.llm_clients"] = ModuleType(f"{pkg_name}.llm_clients")
    sys.modules[f"{pkg_name}.llm_clients"].__path__ = [str(SVC / "app" / "llm_clients")]

    proto = _load(f"{pkg_name}.llm_clients.protocol", SVC / "app" / "llm_clients" / "protocol.py", f"{pkg_name}.llm_clients")
    pool = _load(f"{pkg_name}.llm_clients.pool", SVC / "app" / "llm_clients" / "pool.py", f"{pkg_name}.llm_clients")
    _load(f"{pkg_name}.llm_clients.ollama_client", SVC / "app" / "llm_clients" / "ollama_client.py", f"{pkg_name}.llm_clients")
    _load(f"{pkg_name}.llm_clients.claude_cli_client", SVC / "app" / "llm_clients" / "claude_cli_client.py", f"{pkg_name}.llm_clients")
    _load(f"{pkg_name}.llm_clients.codex_cli_client", SVC / "app" / "llm_clients" / "codex_cli_client.py", f"{pkg_name}.llm_clients")
    # Manually populate __init__ exports for pool import.
    init_pkg = sys.modules[f"{pkg_name}.llm_clients"]
    init_pkg.LlmClientPool = pool.LlmClientPool
    init_pkg.AllBackendsUnavailable = pool.AllBackendsUnavailable
    init_pkg.RouteOutcome = pool.RouteOutcome
    init_pkg.LlmClient = proto.LlmClient
    init_pkg.LlmClientUnavailable = proto.LlmClientUnavailable
    init_pkg.LlmCallResult = proto.LlmCallResult

    _load(f"{pkg_name}.model_catalog", SVC / "app" / "model_catalog.py", pkg_name)
    router = _load(f"{pkg_name}.model_router", SVC / "app" / "model_router.py", pkg_name)
    registry = _load(f"{pkg_name}.agent_registry", SVC / "app" / "agent_registry.py", pkg_name)

    # Fake mcp + ollama_client modules so agents.py imports don't fail.
    fake_mcp = ModuleType("mcp")
    class _StubMCPClient:  # noqa: N801
        pass
    fake_mcp.MCPClient = _StubMCPClient
    sys.modules["mcp"] = fake_mcp

    fake_ollama_legacy = ModuleType(f"{pkg_name}.ollama_client")
    class _StubOllamaGenerateClient:  # noqa: N801
        async def generate(self, *, model, prompt): return ""
        async def close(self): return None
    fake_ollama_legacy.OllamaGenerateClient = _StubOllamaGenerateClient
    sys.modules[f"{pkg_name}.ollama_client"] = fake_ollama_legacy

    agents = _load(f"{pkg_name}.agents", SVC / "app" / "agents.py", pkg_name)
    return agents, registry, router, pool, proto


# Stub LLM clients (return canned text)
class CannedClient:
    def __init__(self, *, backend, tier, response):
        self.backend = backend
        self.tier = tier
        self._response = response
        self.calls = 0
    async def generate(self, *, model, prompt, timeout_seconds=60.0, metadata=None):
        proto = sys.modules["b1_app.llm_clients.protocol"]
        self.calls += 1
        return proto.LlmCallResult(
            text=self._response, model=model, tier=self.tier,
            tokens_in=10, tokens_out=20, cost_usd_cents=5, backend=self.backend,
        )
    async def close(self): return None


def main() -> int:
    agents, registry, router_mod, pool_mod, proto = _bootstrap()
    StrategistAgent = agents.StrategistAgent

    print("-- 1. POSITIVE: registry has 'strategist' role spec --")
    specs = registry.build_agent_specs(
        coder_model="x", reviewer_model="x", advisor_model="x",
        security_advisor_model="x",
    )
    role_ids = [s.role_id for s in specs]
    assert "strategist" in role_ids, f"strategist missing from registry: {role_ids}"
    strategist_spec = next(s for s in specs if s.role_id == "strategist")
    assert "JSON" in strategist_spec.prompt_template or "json" in strategist_spec.prompt_template
    print(f"  ok: strategist registered with model={strategist_spec.model}")

    print("-- 2. NEGATIVE: heuristic classifies deploy as complexity=high --")
    classifier = StrategistAgent()  # no LLM, heuristic-only
    out = asyncio.run(classifier.classify("deploy the new schema migration"))
    assert out["overall_complexity"] == "high", (
        f"deploy must be high complexity; got {out['overall_complexity']}"
    )
    print(f"  ok: deploy → high (source={out.get('source')})")

    print("-- 3. NEGATIVE: heuristic classifies oauth/auth as novelty=novel --")
    out = asyncio.run(classifier.classify("implement OAuth2 PKCE in Next.js"))
    assert out["overall_novelty"] == "novel", (
        f"oauth must be novel; got {out['overall_novelty']}"
    )
    print(f"  ok: oauth → novel (source={out.get('source')})")

    print("-- 4. POSITIVE: routine bugfix → routine + non-trivial+ --")
    out = asyncio.run(classifier.classify("rename a variable in the alerts router"))
    assert out["overall_novelty"] == "routine"
    assert out["overall_complexity"] in ("trivial", "medium")
    print(f"  ok: rename → {out['overall_complexity']}/{out['overall_novelty']}")

    print("-- 5. POSITIVE: LLM-routed path parses JSON output --")
    canned_json = '{"steps":[{"step_id":"impl","complexity":"high","novelty":"novel","needs_research":true}],"overall_complexity":"high","overall_novelty":"novel","needs_research":true,"summary":"OAuth flow"}'
    canned_claude = CannedClient(backend="claude_cli", tier="tier_b", response=canned_json)
    canned_ollama = CannedClient(backend="ollama", tier="tier_a", response="")
    pool = pool_mod.LlmClientPool({"claude_cli": canned_claude, "ollama": canned_ollama})
    classifier_routed = StrategistAgent(
        spec=strategist_spec,
        pool=pool,
        route_fn=router_mod.route,
        role_id="strategist",
    )
    out = asyncio.run(classifier_routed.classify("implement OAuth2 PKCE"))
    assert out.get("source") == "llm_routed", f"expected llm_routed source, got {out.get('source')}"
    assert out["overall_complexity"] == "high"
    assert out["overall_novelty"] == "novel"
    assert canned_claude.calls == 1, "strategist did not hit Tier B (D2 violation)"
    assert "routing" in out, "routing trail missing from classification output"
    print(f"  ok: LLM JSON parsed; routing recorded; cost={out.get('cost_usd_cents')} cents")

    print("-- 6. NEGATIVE: unparseable LLM output → heuristic fallback (no crash) --")
    bad_response = "Sure! Here's my analysis: this looks complicated. (no JSON)"
    canned_bad = CannedClient(backend="claude_cli", tier="tier_b", response=bad_response)
    pool2 = pool_mod.LlmClientPool({"claude_cli": canned_bad, "ollama": canned_ollama})
    classifier_bad = StrategistAgent(
        spec=strategist_spec, pool=pool2, route_fn=router_mod.route, role_id="strategist",
    )
    out = asyncio.run(classifier_bad.classify("rename a variable"))
    assert "overall_complexity" in out, "even on parse fail, classification must return"
    assert "llm_text_unparseable" in out, (
        "unparseable LLM text must be recorded for forensics"
    )
    print("  ok: parse-fail → heuristic fallback with llm_text_unparseable recorded")

    print("-- 7. NEGATIVE: backend down → AllBackendsUnavailable handled gracefully --")
    class FailClient(CannedClient):
        async def generate(self, **k):
            raise proto.LlmClientUnavailable("simulated backend down")
    pool3 = pool_mod.LlmClientPool({"claude_cli": FailClient(backend="claude_cli", tier="tier_b", response=""), "ollama": FailClient(backend="ollama", tier="tier_a", response="")})
    classifier_down = StrategistAgent(
        spec=strategist_spec, pool=pool3, route_fn=router_mod.route, role_id="strategist",
    )
    out = asyncio.run(classifier_down.classify("deploy something"))
    assert "llm_unavailable" in out, "backend-down must be recorded"
    assert out["overall_complexity"] == "high", "heuristic still classifies deploy as high"
    print("  ok: all backends down → heuristic + llm_unavailable record")

    print("-- 8. POSITIVE: classification dict is JSON-serializable --")
    import json
    # Test on the real LLM-routed output (richest dict).
    json.dumps(out)
    print("  ok: classification serializes for audit log")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
