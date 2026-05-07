#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for B6 — ObserverAgent + migration 012 (Phase B6 scaffold).

Tests the two-signal rollback rule per §47.7:
  - alerts_fired ≥ 1 AND p95 > 2x baseline → rollback_required
  - only one signal → degraded (operator reviews)
  - neither signal → healthy

Negative assertions:
  1. ONE-signal events MUST NOT trigger rollback (operator review only)
  2. both signals breach → MUST mark rollback_required
  3. healthy path → recommended_action mentions 'finalize'
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MIGRATION = SVC / "migrations" / "012_observe_windows.sql"


def _load(name, file, package=None):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap():
    pkg = "b6_app"
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
    return _load(f"{pkg}.observer", SVC / "app" / "observer.py", pkg)


def main() -> int:
    print("-- 1. POSITIVE: migration 012 exists with soak window fields --")
    assert MIGRATION.exists()
    sql = MIGRATION.read_text()
    for needle in ("observe_windows", "soak_started_at", "soak_ends_at",
                   "alerts_seen_json", "p95_baseline_ms", "p95_observed_ms",
                   "ROW LEVEL SECURITY", "WHERE status = 'pending'"):
        assert needle in sql, f"missing in 012: {needle}"
    print("  ok: observe_windows schema + partial index for sweep")

    print("-- 2. POSITIVE: ObserverAgent loads --")
    obs = _bootstrap()
    agent = obs.ObserverAgent()
    print("  ok: ObserverAgent instantiable")

    print("-- 3. POSITIVE: healthy when both signals OK --")
    out = asyncio.run(agent.observe(alerts_fired=0, p95_baseline_ms=100, p95_observed_ms=110))
    assert out["status"] == "healthy", f"expected healthy, got {out['status']}"
    assert "finalize" in out["recommended_action"]
    print("  ok: healthy → finalize")

    print("-- 4. NEGATIVE: ONE signal (alerts only) → degraded, NOT rollback --")
    out = asyncio.run(agent.observe(alerts_fired=2, p95_baseline_ms=100, p95_observed_ms=110))
    assert out["status"] == "degraded", (
        f"single-signal MUST be 'degraded' (operator review), got {out['status']}"
    )
    print(f"  ok: alerts-only → {out['status']}")

    print("-- 5. NEGATIVE: ONE signal (p95 only) → degraded --")
    out = asyncio.run(agent.observe(alerts_fired=0, p95_baseline_ms=100, p95_observed_ms=300))
    assert out["status"] == "degraded", (
        f"single-signal MUST be 'degraded'; got {out['status']}"
    )
    print(f"  ok: p95-only → {out['status']}")

    print("-- 6. NEGATIVE: BOTH signals → rollback_required --")
    out = asyncio.run(agent.observe(alerts_fired=3, p95_baseline_ms=100, p95_observed_ms=300))
    assert out["status"] == "rollback_required"
    assert "rollback" in out["recommended_action"]
    print("  ok: both signals → rollback_required")

    print("-- 7. POSITIVE: pure decision function is callable directly --")
    status, concerns = obs.ObserverAgent.evaluate_metrics(
        alerts_fired=5, p95_baseline_ms=100, p95_observed_ms=500,
    )
    assert status == "rollback_required"
    assert len(concerns) == 2
    print("  ok: evaluate_metrics is pure, drillable")

    print()
    print("ALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
