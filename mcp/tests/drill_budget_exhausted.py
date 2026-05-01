#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for C1 — tenant budget enforcement at the router (Phase C1).

Verifies:
  - migration 013 declares tenant_budgets table with cap + used + reset
  - router accepts budget_remaining_cents kwarg
  - budget_remaining_cents=0 forces Tier-A even when has_tier_b=True
    (the cost guard)
  - budget exhaustion is recorded in RouteDecision.reason for audit

Negative assertions:
  1. budget=0 + novel + high → MUST stay Tier-A (cost runaway prevention)
  2. budget=0 → reason MUST contain 'budget_exhausted' (audit visibility)
  3. budget=None (no tracking) → behavior identical to pre-C1 (backward
     compat — operators who haven't enabled budgets see no change)

Resource tag = readonly. Pure function + SQL source check.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MIGRATION = SVC / "migrations" / "013_tenant_budgets.sql"
ROUTER = SVC / "app" / "model_router.py"


def _import_router():
    pkg_name = "c1_app"
    if pkg_name not in sys.modules:
        sys.modules[pkg_name] = type(sys)(pkg_name)
    cat_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.model_catalog", SVC / "app" / "model_catalog.py"
    )
    cat_mod = importlib.util.module_from_spec(cat_spec)
    cat_mod.__package__ = pkg_name
    sys.modules[f"{pkg_name}.model_catalog"] = cat_mod
    cat_spec.loader.exec_module(cat_mod)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.model_router", ROUTER
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg_name
    sys.modules[f"{pkg_name}.model_router"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: migration 013 exists with tenant_budgets table --")
    assert MIGRATION.exists(), f"{MIGRATION} not present"
    sql = MIGRATION.read_text(encoding="utf-8")
    for needle in (
        "CREATE TABLE IF NOT EXISTS orchestration.tenant_budgets",
        "tenant_id",
        "daily_cap_cents",
        "used_today_cents",
        "reset_at",
        "ROW LEVEL SECURITY",
    ):
        assert needle in sql, f"missing in migration: {needle!r}"
    print("  ok: tenant_budgets table + RLS policy declared")

    print("-- 2. POSITIVE: router accepts budget_remaining_cents kwarg --")
    router = _import_router()
    d = router.route(
        role_id="researcher",
        complexity="high",
        novelty="novel",
        has_tier_b=True,
        budget_remaining_cents=500,  # plenty
    )
    assert d.chosen.tier == "tier_b", f"with budget, novel+high should pick tier_b"
    print(f"  ok: budget=500 → tier_b ({d.reason})")

    print("-- 3. NEGATIVE: budget=0 forces Tier-A on novel+high --")
    d = router.route(
        role_id="researcher",
        complexity="high",
        novelty="novel",
        has_tier_b=True,
        budget_remaining_cents=0,  # exhausted
    )
    assert d.chosen.tier == "tier_a", (
        f"BUDGET BREACH: novel+high with budget=0 should fall back; "
        f"got chosen={d.chosen.to_dict()}, reason={d.reason}"
    )
    print(f"  ok: budget=0 + novel+high → {d.chosen.model} (tier_a)")

    print("-- 4. NEGATIVE: reason cites budget_exhausted (audit-visible) --")
    assert "budget_exhausted" in d.reason, (
        f"budget block must be visible in reason; got: {d.reason}"
    )
    print(f"  ok: reason='{d.reason}' surfaces budget exhaustion")

    print("-- 5. NEGATIVE: budget=None preserves pre-C1 behavior --")
    d_with_none = router.route(
        role_id="researcher", complexity="high", novelty="novel", has_tier_b=True,
        budget_remaining_cents=None,
    )
    d_implicit = router.route(
        role_id="researcher", complexity="high", novelty="novel", has_tier_b=True,
    )
    # Both should pick tier_b (no budget = no enforcement).
    assert d_with_none.chosen.to_dict() == d_implicit.chosen.to_dict(), (
        "budget=None must produce same handle as pre-C1 (no kwarg)"
    )
    assert d_with_none.chosen.tier == "tier_b", "no-budget tracking should not block"
    print("  ok: budget=None ↔ no kwarg (backward compat)")

    print("-- 6. POSITIVE: budget=0 even on routine logs the exhaustion --")
    d = router.route(
        role_id="coder_executor", complexity="trivial", novelty="routine",
        has_tier_b=True, budget_remaining_cents=0,
    )
    # Already Tier-A (R5), but reason should still note budget_exhausted
    # so operator dashboards can show 'tenant X is over cap'.
    assert d.chosen.tier == "tier_a"
    assert "budget_exhausted" in d.reason, (
        f"routine task with exhausted budget should still annotate reason: {d.reason}"
    )
    print(f"  ok: routine + budget=0 → reason='{d.reason}'")

    print("-- 7. POSITIVE: routing_inputs records the budget value --")
    d = router.route(
        role_id="advisor", complexity="medium", novelty="routine",
        budget_remaining_cents=42,
    )
    assert d.inputs.get("budget_remaining_cents") == "42", (
        f"inputs must capture budget for audit; got {d.inputs}"
    )
    assert d.inputs.get("budget_blocks_tier_b") == "False"
    print("  ok: budget value + block-flag persisted in RouteDecision.inputs")

    print()
    print("ALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
