#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-E — §41/§47/§48 integrations (#23, #24, #25).

Includes negative assertions: failure-cost metric must NOT
silently zero on shadow Tier-B fallback; observer must NOT miss
degradation when only 2 signals fire; integration tests must NOT
pass when any of the three §41/§47/§48 surfaces is unwired.

Locks 3 cross-cutting integrations:

  #23  documind_circuit_breaker_failure_cost_usd_cents_total — Tier-B
       failures still cost money; surface in finops dashboards.
  #24  Observer two-signal extended to three-signal — open breakers
       on the deployed service count as a degradation signal.
  #25  /api/v1/agentic/tasks/{id}/explain returns breaker_states —
       operator can see "this task ran while breaker X was OPEN."
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load_cb() -> object:
    sys.path.insert(0, str(REPO / "libs" / "py"))
    import documind_core.circuit_breaker as cb  # noqa: PLC0415
    return cb


def _bootstrap_app_pkg() -> None:
    """Set up a fake `cbe_app` package so observer.py + explainability.py
    import each other via relative imports."""
    from types import ModuleType
    pkg_name = "cbe_app"
    if pkg_name in sys.modules:
        return
    sys.modules[pkg_name] = ModuleType(pkg_name)
    sys.modules[pkg_name].__path__ = [
        str(REPO / "services" / "agent-orchestrator-svc" / "app")
    ]


def _load_module(name: str, file: Path, package: str = "cbe_app"):
    """Load a module under the cbe_app package so relative imports resolve."""
    _bootstrap_app_pkg()
    full_name = f"{package}.{name}"
    spec = importlib.util.spec_from_file_location(full_name, file)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = package
    sys.modules[full_name] = mod
    # Also stub the heavy llm_clients sub-package since observer
    # imports from it but we don't actually invoke that path.
    if "cbe_app.llm_clients" not in sys.modules:
        from types import ModuleType as _MT
        sys.modules["cbe_app.llm_clients"] = _MT("cbe_app.llm_clients")
        class _Stub:
            pass
        sys.modules["cbe_app.llm_clients"].LlmClientPool = _Stub
        sys.modules["cbe_app.llm_clients"].AllBackendsUnavailable = _Stub
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    cb_mod = _load_cb()
    CircuitBreaker = cb_mod.CircuitBreaker

    # -------------------------------------------------------------
    # FIX #23: failure_cost counter exposed + record_failure_cost works
    # -------------------------------------------------------------
    print("-- 1. POSITIVE: documind_circuit_breaker_failure_cost_usd_cents_total exists --")
    assert hasattr(cb_mod, "_cb_failure_cost"), "metric not declared at module level"
    print("  ok: failure_cost counter declared")

    print("-- 2. POSITIVE: record_failure_cost increments the counter --")
    cb = CircuitBreaker("cost-tracking")
    before = cb_mod._cb_failure_cost.labels(name="cost-tracking")._value.get()  # type: ignore[attr-defined]
    cb.record_failure_cost(50)   # 50 cents wasted on a failed Tier-B call
    cb.record_failure_cost(75)
    after = cb_mod._cb_failure_cost.labels(name="cost-tracking")._value.get()  # type: ignore[attr-defined]
    assert after - before == 125, f"expected delta 125 cents, got {after - before}"
    print(f"  ok: counter increased by 125 cents (50 + 75)")

    print("-- 3. NEGATIVE: record_failure_cost(0) is a no-op --")
    before = cb_mod._cb_failure_cost.labels(name="cost-tracking")._value.get()  # type: ignore[attr-defined]
    cb.record_failure_cost(0)
    cb.record_failure_cost(-10)  # negative also no-op
    after = cb_mod._cb_failure_cost.labels(name="cost-tracking")._value.get()  # type: ignore[attr-defined]
    assert after == before, f"0/negative cost should be no-op; delta={after - before}"
    print("  ok: 0 / negative cost values are no-ops (Tier-A safe)")

    # -------------------------------------------------------------
    # FIX #24: observer evaluate_metrics accepts open_breakers
    # -------------------------------------------------------------
    print("-- 4. POSITIVE: ObserverAgent.evaluate_metrics accepts open_breakers --")
    obs_mod = _load_module(
        "observer", REPO / "services" / "agent-orchestrator-svc" / "app" / "observer.py"
    )
    ObserverAgent = obs_mod.ObserverAgent
    # Pure-function signature accepts the new kwarg.
    status, concerns = ObserverAgent.evaluate_metrics(
        alerts_fired=0,
        p95_baseline_ms=100,
        p95_observed_ms=110,
        open_breakers=[],
    )
    assert status == "healthy"
    print("  ok: evaluate_metrics accepts open_breakers kwarg; healthy when empty")

    # -------------------------------------------------------------
    # FIX #24 NEGATIVE: single open breaker → degraded (not rollback)
    # -------------------------------------------------------------
    print("-- 5. NEGATIVE: single OPEN breaker → degraded (not rollback) --")
    status, concerns = ObserverAgent.evaluate_metrics(
        alerts_fired=0,
        p95_baseline_ms=100,
        p95_observed_ms=110,
        open_breakers=["mcp_research"],
    )
    assert status == "degraded", f"single signal should be degraded, got {status}"
    assert any("breaker" in c.lower() for c in concerns)
    print(f"  ok: 1 breaker open → degraded (concerns: {concerns})")

    # -------------------------------------------------------------
    # FIX #24: TWO signals (alerts + breakers) → rollback_required
    # -------------------------------------------------------------
    print("-- 6. POSITIVE: alerts + open_breakers → rollback_required --")
    status, _ = ObserverAgent.evaluate_metrics(
        alerts_fired=2,
        p95_baseline_ms=100,
        p95_observed_ms=110,        # p95 NOT breached
        open_breakers=["mcp_deploy"],
    )
    assert status == "rollback_required", (
        f"alerts + breakers (2 signals) should trigger rollback; got {status}"
    )
    print("  ok: 2 of 3 signals → rollback_required (was: would have been degraded with old 2-signal rule)")

    # -------------------------------------------------------------
    # FIX #24 NEGATIVE: single signal still keeps degraded
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: alerts alone (no breakers) → degraded (single signal) --")
    status, _ = ObserverAgent.evaluate_metrics(
        alerts_fired=5,
        p95_baseline_ms=100,
        p95_observed_ms=110,
        open_breakers=[],  # no breakers
    )
    assert status == "degraded", (
        f"single signal must NOT escalate to rollback; got {status}"
    )
    print("  ok: alerts-only stays degraded (operator review)")

    # -------------------------------------------------------------
    # FIX #25: explain endpoint returns breaker_states
    # -------------------------------------------------------------
    print("-- 8. POSITIVE: assemble_explanation accepts + surfaces breaker_states --")
    exp_mod = _load_module(
        "explainability", REPO / "services" / "agent-orchestrator-svc" / "app" / "explainability.py"
    )
    task = {
        "task_id": "t1", "tenant_id": "acme", "goal": "x", "status": "completed",
        "risk_level": "low", "tool_namespace": None, "tool_name": None,
        "tool_arguments": {}, "audit_events": [], "created_at": "2026-04-30",
    }
    row = exp_mod.assemble_explanation(
        task=task, task_runs=[],
        breaker_states={"ollama": "closed", "mcp_research": "open"},
    )
    assert "breaker_states" in row, "FIX #25 BROKEN: breaker_states key missing from row"
    assert row["breaker_states"] == {"ollama": "closed", "mcp_research": "open"}
    assert "breaker_states" in exp_mod.REQUIRED_AUDIT_FIELDS
    print("  ok: breaker_states present in /explain row + REQUIRED_AUDIT_FIELDS")

    # -------------------------------------------------------------
    # FIX #25 NEGATIVE: empty breaker_states defaults to {}
    # -------------------------------------------------------------
    print("-- 9. NEGATIVE: missing breaker_states arg defaults to {} (no None leak) --")
    row = exp_mod.assemble_explanation(task=task, task_runs=[])
    assert row["breaker_states"] == {}, (
        f"missing arg should default to {{}}, got {row['breaker_states']!r}"
    )
    print("  ok: default {} (not None — operator dashboards can render uniformly)")

    print()
    print("ALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
