#!/usr/bin/env python3
# RESOURCES: readonly
"""Structural + decision drill for app/model_router.py (Phase A3).

Locks the 5 routing rules and the fallback-chain contract.

Negative assertions (drilled):
  1. (routine, trivial) → NEVER returns tier_b even with has_tier_b=True
     AND a tier_b model present. Cost guard.
  2. Unknown role_id → UnknownRoleError. No silent default.
  3. has_tier_b=False with novel+high → falls back to tier_a_heavy with
     reason='*tier_b_unavailable_fallback*'. Audit-visible.
  4. Fallback chain must NOT contain the chosen handle (would waste a
     retry slot).
  5. strategist with tier_b available → ALWAYS tier_b (D2 default).

Resource tag = readonly (pure-function drill, no I/O).

Why this drill: A3 is the highest-leverage commit for cost control. A
misroute (cheap → expensive) costs 10x. Pure function + drill = the
contract is auditable forever.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
ROUTER_FILE = SVC / "app" / "model_router.py"
CATALOG_FILE = SVC / "app" / "model_catalog.py"


def _import_pkg():
    catalog = importlib.util.spec_from_file_location("a3_catalog", CATALOG_FILE)
    cat_mod = importlib.util.module_from_spec(catalog)
    sys.modules["a3_catalog"] = cat_mod
    catalog.loader.exec_module(cat_mod)

    sys.modules.setdefault("a3_pkg", type(sys)("a3_pkg"))
    sys.modules["a3_pkg.model_catalog"] = cat_mod

    spec = importlib.util.spec_from_file_location("a3_pkg.model_router", ROUTER_FILE)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "a3_pkg"
    sys.modules["a3_pkg.model_router"] = mod
    spec.loader.exec_module(mod)
    return mod, cat_mod


def main() -> int:
    router, catalog = _import_pkg()

    print("-- 1. POSITIVE: routine+trivial+coder → tier_a primary --")
    d = router.route(role_id="coder_executor", complexity="trivial", novelty="routine", has_tier_b=True)
    assert d.chosen.tier == "tier_a", f"expected tier_a, got {d.chosen.tier}"
    assert d.reason.startswith("R5_"), f"expected R5_*, got {d.reason}"
    assert d.chosen.backend == "ollama"
    print(f"  ok: chose {d.chosen.model} ({d.reason})")

    print("-- 2. NEGATIVE: routine+trivial → NEVER tier_b (cost guard) --")
    # Even with novel role like researcher, if novelty=routine + trivial,
    # never escalate. Tests R1 doesn't accidentally fire on non-strategist.
    d = router.route(role_id="researcher", complexity="trivial", novelty="routine", has_tier_b=True)
    assert d.chosen.tier == "tier_a", (
        f"COST GUARD VIOLATION: routine+trivial routed to tier_b! "
        f"chosen={d.chosen.to_dict()}, reason={d.reason}"
    )
    print(f"  ok: routine+trivial held to tier_a ({d.reason})")

    print("-- 3. POSITIVE: novel+high+coder → tier_b (Codex backend) --")
    d = router.route(role_id="coder_executor", complexity="high", novelty="novel", has_tier_b=True)
    assert d.chosen.tier == "tier_b", f"expected tier_b, got {d.chosen.tier}"
    # Coder's tier_b_backend is codex_cli per D1 default.
    assert d.chosen.backend == "codex_cli", f"expected codex_cli, got {d.chosen.backend}"
    assert d.reason.startswith("R2_"), f"expected R2_*, got {d.reason}"
    print(f"  ok: chose {d.chosen.model} on {d.chosen.backend} ({d.reason})")

    print("-- 4. POSITIVE: novel+high+researcher → tier_b (Claude backend) --")
    d = router.route(role_id="researcher", complexity="high", novelty="novel", has_tier_b=True)
    assert d.chosen.tier == "tier_b"
    assert d.chosen.backend == "claude_cli"
    print(f"  ok: chose {d.chosen.model} on {d.chosen.backend} ({d.reason})")

    print("-- 5. POSITIVE: strategist always tier_b (D2 rule R1) --")
    d = router.route(role_id="strategist", complexity="trivial", novelty="routine", has_tier_b=True)
    assert d.chosen.tier == "tier_b", (
        "R1 broken: strategist with tier_b available must always be tier_b"
    )
    assert d.reason == "R1_strategist_always_tier_b"
    print(f"  ok: strategist always tier_b ({d.reason})")

    print("-- 6. NEGATIVE: unknown role_id → UnknownRoleError --")
    raised = False
    try:
        router.route(role_id="ghost_agent_does_not_exist", complexity="medium", novelty="routine")
    except router.UnknownRoleError:
        raised = True
    assert raised, "unknown role_id MUST raise UnknownRoleError, not silent default"
    print("  ok: unknown role raises UnknownRoleError")

    print("-- 7. NEGATIVE: has_tier_b=False with novel+high → tier_a fallback --")
    d = router.route(role_id="coder_executor", complexity="high", novelty="novel", has_tier_b=False)
    assert d.chosen.tier == "tier_a", f"expected fallback to tier_a, got {d.chosen.tier}"
    assert "tier_b_unavailable_fallback" in d.reason, (
        f"expected fallback reason to mention tier_b unavailability; got {d.reason}"
    )
    print(f"  ok: tier_b absent → fell back to {d.chosen.model} ({d.reason})")

    print("-- 8. NEGATIVE: chosen handle MUST NOT appear in fallback_chain --")
    d = router.route(role_id="coder_executor", complexity="trivial", novelty="routine")
    chosen_key = (d.chosen.model, d.chosen.backend)
    for h in d.fallback_chain:
        assert (h.model, h.backend) != chosen_key, (
            f"WASTED RETRY: chosen={chosen_key} also in fallback chain"
        )
    # Ensure chain isn't empty (we should have at least primary+backup minus chosen = 1+).
    assert len(d.fallback_chain) >= 1, "fallback chain unexpectedly empty"
    print(f"  ok: chosen excluded from chain; chain length={len(d.fallback_chain)}")

    print("-- 9. POSITIVE: roles without tier_b never route to tier_b --")
    # Reviewer + tester have no tier_b in the default catalog.
    for role in ("reviewer", "tester"):
        d = router.route(role_id=role, complexity="high", novelty="novel", has_tier_b=True)
        assert d.chosen.tier == "tier_a", (
            f"role={role} has no tier_b in catalog, but routed to tier_b!"
        )
    print("  ok: tier_b-less roles always stay on tier_a")

    print("-- 10. POSITIVE: route_decision is JSON-serializable --")
    d = router.route(role_id="advisor", complexity="high", novelty="novel", has_tier_b=True)
    payload = d.to_dict()
    import json
    json.dumps(payload)  # raises if not serializable
    assert payload["chosen"]["tier"] in ("tier_a", "tier_b")
    assert "fallback_chain" in payload
    assert payload["reason"]
    print("  ok: RouteDecision.to_dict() serializes for audit log")

    print()
    print("ALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
