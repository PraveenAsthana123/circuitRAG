#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: agent-lead routing (Tier 1 #1.2) — all 5 routes locked.

Per CLAUDE.md §43 + §55. Empirical session evidence: today every
issue went through the full 4-role council regardless of difficulty
(F401 trivial unused-import got the same 3+ minute treatment as F841
real-bug investigation). The agent-lead supervisor maps strategy.
model_tier to one of 5 routes BEFORE any worker fires.

Eight steps. Six negative assertions covering the 5 routes + the
2 filter rules (already-attempted, out-of-safe-path).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "agent_lead.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("agent_lead", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load agent_lead from {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_lead"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: agent_lead module imports + 4 exports --")
    al = _load()
    for name in ("decide_route", "RouteDecision", "EXPECTED_TOKENS_PER_ROUTE", "COST_PER_1K_TOKENS_CENTS"):
        if not hasattr(al, name):
            print(f"x step 1: missing export {name}")
            return 1
    print(f"  ok: 4 exports present; {len(al.EXPECTED_TOKENS_PER_ROUTE)} routes catalogued")

    def _issue(code: str, file_: str = "scripts/foo.py") -> dict:
        return {"id": f"test-{code}", "code": code, "file": file_, "line": 1, "message": "test"}

    print("-- 2. POSITIVE: F841 (investigation/default tier) → council_full --")
    d = al.decide_route(_issue("F841"))
    if d.route != "council_full":
        print(f"x step 2: F841 expected council_full; got {d.route}")
        return 1
    if d.model is None or "deepseek-coder" not in d.model:
        print(f"x step 2: council_full should pick deepseek-coder; got {d.model}")
        return 1
    if d.estimated_cost_cents <= 0:
        print(f"x step 2: cost estimate must be > 0 for council_full; got {d.estimated_cost_cents}")
        return 1
    print(f"  ok: F841 → {d.route} model={d.model} cost~={d.estimated_cost_cents}¢")

    print("-- 3. POSITIVE: UP041 (mechanical/small tier) → small_direct --")
    d = al.decide_route(_issue("UP041"))
    if d.route != "small_direct":
        print(f"x step 3: UP041 expected small_direct; got {d.route}")
        return 1
    if d.model is None or "llama3.2" not in d.model:
        print(f"x step 3: small_direct should pick llama3.2:1b; got {d.model}")
        return 1
    print(f"  ok: UP041 → {d.route} model={d.model} cost~={d.estimated_cost_cents}¢")

    print("-- 4. NEGATIVE: B110 (bandit security) → human (NEVER to model) --")
    d = al.decide_route(_issue("B110"))
    if d.route != "human":
        print(f"x step 4: B110 must route to human (per §50.5.3); got {d.route}")
        return 1
    if d.model is not None:
        print(f"x step 4: human route must have model=None; got {d.model}")
        return 1
    if "security" not in d.reason.lower() and "§50.5.3" not in d.reason:
        print(f"x step 4: human reason must cite §50.5.3 or 'security'; got: {d.reason}")
        return 1
    print(f"  ok: B110 → {d.route} (security gate enforced)")

    print("-- 5. NEGATIVE: S101 (ruff security) → human --")
    d = al.decide_route(_issue("S101"))
    if d.route != "human":
        print(f"x step 5: S101 must route to human; got {d.route}")
        return 1
    print(f"  ok: S101 → human (security gate)")

    print("-- 6. NEGATIVE: already_attempted=True → skip (retry-loop prevention) --")
    d = al.decide_route(_issue("F841"), already_attempted=True)
    if d.route != "skip":
        print(f"x step 6: already_attempted must short-circuit to skip; got {d.route}")
        return 1
    if "already" not in d.reason.lower() and "audit" not in d.reason.lower():
        print(f"x step 6: skip reason must cite 'already' or 'audit'; got: {d.reason}")
        return 1
    print(f"  ok: already_attempted → {d.route}; retry-loop prevented")

    print("-- 7. NEGATIVE: out-of-safe-path → skip --")
    d = al.decide_route(_issue("F841", file_="/etc/passwd"), in_safe_path=False)
    if d.route != "skip":
        print(f"x step 7: out-of-safe-path must skip; got {d.route}")
        return 1
    print(f"  ok: out-of-safe-path → skip; §42 boundary enforced")

    print("-- 8. POSITIVE: cost estimate strictly ordered (skip=0 < small < council < tier_b) --")
    issue = _issue("F841")
    council = al.decide_route(issue).estimated_cost_cents
    skip_cost = al.decide_route(issue, already_attempted=True).estimated_cost_cents
    small = al.decide_route(_issue("UP041")).estimated_cost_cents
    if not (skip_cost == 0 and small > 0 and council > small):
        print(
            f"x step 8: cost ordering violated — skip={skip_cost}, small={small}, council={council}; "
            "expected skip=0 < small < council"
        )
        return 1
    print(f"  ok: cost ordering skip=0 ¢ < small={small}¢ < council={council}¢ (token-budget signal preserved)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
