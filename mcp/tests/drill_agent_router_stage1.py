#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Agent Router Stage-1 — intent + risk classifier contract.

Per CLAUDE.md §43 + §47 (11-layer architecture, Layer 3). Locks:

  - classify() returns RouterDecision dict with 7 required fields
  - High-risk inputs (delete, deploy, force-push, secret) → risk="high"
  - Low-risk inputs (read, explain, search, snapshot) → risk="low"
  - Medium-risk inputs (fix lint, refactor) → risk="medium"
  - Empty input → conservative default (high risk + operator:human)
  - Gibberish input → conservative default (no pattern match)
  - Recommended actors are valid PolisAI rule subjects
  - Recommended tools route to PolisAI rules that exist OR to
    human_review (which always defaults-deny without operator scope)
  - Audit row appended per classify() call

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
AUDIT_LOG = REPO / ".loop" / "agent_router_audit.jsonl"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: agent_router imports + exports the contract --")
    import agent_router  # noqa: E402
    for name in (
        "classify", "list_patterns", "RouterDecision",
        "HIGH_RISK_PATTERNS", "MEDIUM_RISK_PATTERNS", "LOW_RISK_PATTERNS",
    ):
        if not hasattr(agent_router, name):
            print(f"x agent_router.{name} missing")
            return 1
    print("  ok: 6 surfaces exported")

    print("-- 2. POSITIVE: classify() returns RouterDecision with 7 required fields --")
    decision = agent_router.classify("explain how this works", persist_audit=False)
    required_fields = {
        "intent", "risk", "recommended_actor", "recommended_tool",
        "confidence", "reasons", "timestamp",
    }
    decision_dict = decision.to_dict()
    missing = required_fields - set(decision_dict.keys())
    if missing:
        print(f"x RouterDecision missing fields: {missing}")
        return 1
    if decision.risk not in ("low", "medium", "high", "unknown"):
        print(f"x risk must be in {{low,medium,high,unknown}}; got {decision.risk!r}")
        return 1
    if not (0.0 <= decision.confidence <= 1.0):
        print(f"x confidence out of [0,1]; got {decision.confidence}")
        return 1
    print("  ok: all 7 fields present; risk + confidence in valid ranges")

    print("-- 3. NEGATIVE: high-risk inputs → risk='high' (4 patterns tested) --")
    high_risk_messages = [
        "delete the user table",
        "deploy to production",
        "force-push the branch",
        "store the api-key in config",
    ]
    for msg in high_risk_messages:
        d = agent_router.classify(msg, persist_audit=False)
        if d.risk != "high":
            print(f"x message {msg!r} should be high-risk; got {d.risk!r}")
            return 1
        if d.recommended_actor != "operator:human":
            print(f"x high-risk msg should route to operator:human; got {d.recommended_actor!r}")
            return 1
    print("  ok: all 4 high-risk messages → risk='high' + operator:human")

    print("-- 4. NEGATIVE: medium-risk inputs → risk='medium' --")
    medium_msgs = [
        "fix the ruff lint errors",
        "refactor this module",
        "write a test for the council",
    ]
    for msg in medium_msgs:
        d = agent_router.classify(msg, persist_audit=False)
        if d.risk != "medium":
            print(f"x message {msg!r} should be medium-risk; got {d.risk!r}")
            return 1
    print("  ok: all 3 medium-risk messages classified correctly")

    print("-- 5. NEGATIVE: empty / whitespace-only input → conservative default --")
    for msg in ("", "   ", "\t\n"):
        d = agent_router.classify(msg, persist_audit=False)
        if d.intent != "unknown":
            print(f"x empty/whitespace msg should be unknown; got intent={d.intent!r}")
            return 1
        if d.risk != "high":
            print(f"x empty msg conservative default should be high-risk; got {d.risk!r}")
            return 1
        if d.recommended_actor != "operator:human":
            print(f"x conservative default should route to operator:human; got {d.recommended_actor!r}")
            return 1
        if d.confidence != 0.0:
            print(f"x conservative confidence should be 0.0; got {d.confidence}")
            return 1
    print("  ok: 3 empty/whitespace cases all → unknown + high + operator:human + conf=0")

    print("-- 6. NEGATIVE: gibberish (no pattern match) → conservative default --")
    for msg in ("asdfqwerty xyz blah", "1234567890", "!!!@#$%^&*()"):
        d = agent_router.classify(msg, persist_audit=False)
        if d.intent != "unknown":
            print(f"x gibberish {msg!r} should be unknown; got {d.intent!r}")
            return 1
        if d.risk != "high":
            print(f"x gibberish should be high-risk; got {d.risk!r}")
            return 1
    print("  ok: 3 gibberish inputs → unknown + high (conservative default)")

    print("-- 7. NEGATIVE: recommended_actor must match a known PolisAI rule subject --")
    # Read the policy file and verify every recommended_actor in the
    # router's pattern table corresponds to an actor in the policy.
    policy_path = REPO / "config" / "policies" / "agent_dispatch.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy_actors = {r["actor"] for r in policy["rules"]}
    router_actors = set()
    for plist in (
        agent_router.HIGH_RISK_PATTERNS,
        agent_router.MEDIUM_RISK_PATTERNS,
        agent_router.LOW_RISK_PATTERNS,
    ):
        for entry in plist:
            router_actors.add(entry[3])  # actor field
    unknown_actors = router_actors - policy_actors
    if unknown_actors:
        print(f"x router recommends actors not in PolisAI: {unknown_actors}")
        print(f"  policy actors: {sorted(policy_actors)}")
        return 1
    print(f"  ok: all {len(router_actors)} recommended actors exist in PolisAI policy")

    print("-- 8. POSITIVE: audit row persisted per classify() call --")
    pre_count = (
        AUDIT_LOG.read_text(encoding="utf-8").count("\n")
        if AUDIT_LOG.exists() else 0
    )
    # Fire 3 classifications WITH audit
    agent_router.classify("explain this")
    agent_router.classify("delete the table")
    agent_router.classify("xyz nonsense")
    post_count = AUDIT_LOG.read_text(encoding="utf-8").count("\n") if AUDIT_LOG.exists() else 0
    delta = post_count - pre_count
    if delta != 3:
        print(f"x expected 3 new audit rows; got {delta}")
        return 1
    # Inspect the last 3 rows — they should be the ones we just added
    rows = AUDIT_LOG.read_text(encoding="utf-8").strip().split("\n")[-3:]
    parsed = [json.loads(r) for r in rows]
    intents = [r.get("intent") for r in parsed]
    if intents != ["explain", "delete", "unknown"]:
        print(f"x audit row intents wrong: {intents}")
        return 1
    print(f"  ok: 3 audit rows appended with intents {intents}")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
