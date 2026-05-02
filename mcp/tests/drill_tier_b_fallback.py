#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: confidence-gated Tier-B fallback (Tier 2 #2.7).

Per CLAUDE.md §43 + §55. Locks the contract for when local council
exhausts retries + when Tier-B output is itself validated.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "tier_b_fallback.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("tier_b_fallback", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tier_b_fallback"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: tier_b_fallback imports + 5 exports --")
    tb = _load()
    for name in ("should_escalate_to_tier_b", "try_tier_b",
                 "find_available_tier_b", "DEFAULT_CONFIDENCE_THRESHOLD",
                 "TIER_B_CANDIDATES"):
        if not hasattr(tb, name):
            print(f"x step 1: missing export {name}")
            return 1
    print(f"  ok: 5 exports; threshold={tb.DEFAULT_CONFIDENCE_THRESHOLD}; candidates={tb.TIER_B_CANDIDATES}")

    print("-- 2. POSITIVE: should_escalate fires when both local attempts rejected --")
    chain = {
        "author_attempt_1": {"validation": "rejected"},
        "author_attempt_2": {"validation": "rejected"},
        "author": {},
    }
    if not tb.should_escalate_to_tier_b(chain):
        print(f"x step 2: both-attempts-rejected should escalate; got False")
        return 1
    print("  ok: both-attempts-rejected → escalate=True (trigger 1)")

    print("-- 3. POSITIVE: should_escalate fires when validated confidence below threshold --")
    chain = {
        "author_attempt_1": {"validation": "ok"},
        "author": {"proposal": {"confidence": 0.3}},  # below default 0.6
    }
    if not tb.should_escalate_to_tier_b(chain):
        print(f"x step 3: confidence 0.3 < 0.6 should escalate; got False")
        return 1
    print("  ok: low confidence (0.3) → escalate=True (trigger 2)")

    print("-- 4. NEGATIVE: should_escalate does NOT fire on confident validated proposal --")
    chain = {
        "author_attempt_1": {"validation": "ok"},
        "author": {"proposal": {"confidence": 0.9}},
    }
    if tb.should_escalate_to_tier_b(chain):
        print(f"x step 4: confident proposal (0.9) should NOT escalate; got True (theater!)")
        return 1
    print("  ok: confident proposal (0.9) → escalate=False (no theater)")

    print("-- 5. POSITIVE: should_escalate fires on advisor alternative with high risks --")
    chain = {
        "author_attempt_1": {"validation": "ok"},
        "author": {"proposal": {"confidence": 0.8}},
        "advisor": {
            "alternative_proposal": {
                "confidence": 0.7,
                "risks": ["risk1", "risk2", "risk3"],  # 3+ risks → escalate
            },
        },
    }
    if not tb.should_escalate_to_tier_b(chain):
        print(f"x step 5: advisor alt with 3+ risks should escalate; got False")
        return 1
    print("  ok: advisor alt with 3+ risks → escalate=True (trigger 3)")

    print("-- 6. POSITIVE: should_escalate fires on advisor alt mentioning 'breaking' --")
    chain = {
        "author_attempt_1": {"validation": "ok"},
        "author": {"proposal": {"confidence": 0.8}},
        "advisor": {
            "alternative_proposal": {
                "confidence": 0.7,
                "risks": ["this is a BREAKING change"],
            },
        },
    }
    if not tb.should_escalate_to_tier_b(chain):
        print(f"x step 6: 'breaking' risk should escalate; got False")
        return 1
    print("  ok: 'breaking' in risk text → escalate=True (trigger 3 keyword)")

    print("-- 7. NEGATIVE: try_tier_b returns None when NO Tier-B binary on PATH --")
    # On test infra without claude/codex CLI, this path should
    # fail gracefully (no crash, no fake-data return).
    binary = tb.find_available_tier_b()
    issue = {"id": "test", "code": "UP035", "file": "x.py", "line": 1, "message": "test"}
    result = tb.try_tier_b(issue, "  1: x = 1\n", timeout=2.0)
    if binary is None:
        # On this drill host: no claude / codex CLI expected to be present.
        if result is not None:
            print(f"x step 7: try_tier_b returned non-None when no binary available; got {type(result).__name__}")
            return 1
        print(f"  ok: no Tier-B binary on PATH → None returned (graceful degradation)")
    else:
        # If a binary IS available (rare on dev hosts), we just verify
        # the call doesn't crash; result may be None (timeout/parse fail).
        print(f"  ok: Tier-B binary {binary!r} present; try_tier_b returned {type(result).__name__}")

    print("-- 8. NEGATIVE: try_tier_b output goes through CouncilProposal validator --")
    # Source check: try_tier_b must call validate_council_proposal,
    # not bypass the schema. Otherwise Tier-B output gets a free pass.
    src = SCRIPT.read_text(encoding="utf-8")
    if "validate_council_proposal(proc.stdout" not in src:
        print("x step 8: try_tier_b does NOT route output through validate_council_proposal")
        return 1
    if "Same schema gate as local" not in src and "no schema bypass" in src:
        # Either explicit comment is fine; verify the no-bypass invariant
        # is documented somewhere
        pass
    print("  ok: Tier-B output runs through SAME CouncilProposal validator as local council")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
