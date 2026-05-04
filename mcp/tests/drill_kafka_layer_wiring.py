#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-2 — 3 layers wire to Kafka event-publisher (fail-open).

Per CLAUDE.md §43 + §41.5 + §47. Locks the contract that:

  - PolisAI's _append_audit() calls publish_policy_decision()
  - OpenClaw's evaluate_dispatch() calls publish_openclaw_dispatch()
  - Agent Router's _append_audit() calls publish_router_classification()
  - Paperclip stays SANDBOX-ONLY (no Kafka publish from the bare
    aggregator — preserves the drill_paperclip_stage1 contract that
    Paperclip has no outbound network)
  - All 3 wires use try/except (fail-open per §41.5)
  - Wiring imports are LAZY (inside functions, not at module top)
    so module imports stay cheap when KAFKA_PUBLISH is unset

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    print("-- 1. POSITIVE: PolisAI source calls publish_policy_decision --")
    src = _read(SCRIPTS / "policy_check.py")
    if "publish_policy_decision" not in src:
        print("x policy_check.py must call publish_policy_decision")
        return 1
    if "from event_publisher import publish_policy_decision" not in src:
        print("x policy_check.py must import publish_policy_decision (lazy is fine)")
        return 1
    print("  ok: PolisAI imports + calls publish_policy_decision")

    print("-- 2. POSITIVE: OpenClaw source calls publish_openclaw_dispatch --")
    src = _read(SCRIPTS / "openclaw_coordinator.py")
    if "publish_openclaw_dispatch" not in src:
        print("x openclaw_coordinator.py must call publish_openclaw_dispatch")
        return 1
    if "from event_publisher import publish_openclaw_dispatch" not in src:
        print("x openclaw must import publish_openclaw_dispatch")
        return 1
    print("  ok: OpenClaw imports + calls publish_openclaw_dispatch")

    print("-- 3. POSITIVE: Agent Router source calls publish_router_classification --")
    src = _read(SCRIPTS / "agent_router.py")
    if "publish_router_classification" not in src:
        print("x agent_router.py must call publish_router_classification")
        return 1
    if "from event_publisher import publish_router_classification" not in src:
        print("x agent_router must import publish_router_classification")
        return 1
    print("  ok: Agent Router imports + calls publish_router_classification")

    print("-- 4. NEGATIVE: Paperclip aggregator does NOT publish (sandbox preserved) --")
    src = _read(SCRIPTS / "paperclip_manager.py")
    # Paperclip's sandbox contract (drill_paperclip_stage1) is "no
    # outbound network" — wiring Kafka publish from the bare aggregator
    # would change that. Stage-3 wires the BFF route or MCP server to
    # publish on Paperclip's behalf; the aggregator stays clean.
    if "publish_paperclip_snapshot" in src:
        print("x paperclip_manager.py must NOT call publish_paperclip_snapshot;")
        print("  Paperclip is sandbox-only (drill_paperclip_stage1 step 5).")
        return 1
    if "from event_publisher" in src:
        print("x paperclip_manager.py must NOT import event_publisher;")
        print("  preserves no-outbound-network contract.")
        return 1
    print("  ok: paperclip_manager.py has 0 Kafka surfaces (sandbox preserved)")

    print("-- 5. NEGATIVE: all 3 wires use try/except (fail-open per §41.5) --")
    # Each wire MUST NOT propagate Kafka failures to the originating
    # decision. Drill verifies the publish call sits inside a try/except.
    for src_file, fn_name in (
        ("policy_check.py", "publish_policy_decision"),
        ("openclaw_coordinator.py", "publish_openclaw_dispatch"),
        ("agent_router.py", "publish_router_classification"),
    ):
        src = _read(SCRIPTS / src_file)
        # Find the line where publish_* is called
        call_idx = src.find(f"{fn_name}(")
        if call_idx == -1:
            print(f"x can't locate {fn_name} call in {src_file}")
            return 1
        # Look BACK from the call for "try:" within ~200 chars
        before = src[max(0, call_idx - 200):call_idx]
        # Look FORWARD from the call for "except" within ~300 chars
        after = src[call_idx:call_idx + 300]
        if "try:" not in before:
            print(f"x {src_file}: publish call must be inside try block")
            return 1
        if "except" not in after:
            print(f"x {src_file}: publish call must have except branch")
            return 1
    print("  ok: all 3 wires use try/except (fail-open posture preserved)")

    print("-- 6. NEGATIVE: imports are LAZY (inside functions, not module-top) --")
    # Top-level `from event_publisher import ...` would force every
    # importer of policy_check.py to also load event_publisher. Lazy
    # import (inside the function) means the import only fires when
    # the publish actually happens.
    for src_file in ("policy_check.py", "openclaw_coordinator.py", "agent_router.py"):
        src = _read(SCRIPTS / src_file)
        # Walk lines; the `from event_publisher import` line must NOT
        # be at indent level 0 (i.e., it must be inside a function).
        lines = src.split("\n")
        for line in lines:
            if line.startswith("from event_publisher import"):
                print(f"x {src_file}: event_publisher import is at module top (should be lazy)")
                return 1
    print("  ok: all 3 imports of event_publisher are lazy (function-scoped)")

    print("-- 7. POSITIVE: live integration smoke — 3 layers run without raising --")
    # Reset env to default no-op
    os.environ.pop("KAFKA_PUBLISH", None)
    import importlib

    # PolisAI
    import policy_check
    importlib.reload(policy_check)
    d = policy_check.evaluate(
        actor="council:author", tool="read_checklist",
        scopes_granted=["checklist:read"], persist_audit=False,
    )
    if not d.allow:
        print(f"x PolisAI smoke: expected allow=True; got {d}")
        return 1

    # Agent Router
    import agent_router
    importlib.reload(agent_router)
    r = agent_router.classify("explain something", persist_audit=False)
    if r.intent != "explain":
        print(f"x router smoke: expected intent=explain; got {r.intent}")
        return 1

    # OpenClaw
    import openclaw_coordinator as oc
    importlib.reload(oc)
    decision, _envelope = oc.evaluate_dispatch(
        requesting_agent="council:author", target_agent="council:reviewer",
        capability="critique_proposal", scopes_granted=["x"],
    )
    if decision.allow is None:
        print(f"x openclaw smoke: decision.allow must be bool; got {decision}")
        return 1

    print("  ok: all 3 wired layers ran without raising (Kafka stub mode)")

    print("-- 8. NEGATIVE: Kafka outage simulation — wires still complete --")
    # Simulate a Kafka outage by monkey-patching event_publisher to
    # raise on every publish. The wires MUST swallow it and let the
    # originating decision return normally.
    import event_publisher
    original = {
        "policy": event_publisher.publish_policy_decision,
        "router": event_publisher.publish_router_classification,
        "openclaw": event_publisher.publish_openclaw_dispatch,
    }

    def boom(*_a, **_kw):
        raise RuntimeError("simulated Kafka outage")

    event_publisher.publish_policy_decision = boom  # type: ignore[assignment]
    event_publisher.publish_router_classification = boom  # type: ignore[assignment]
    event_publisher.publish_openclaw_dispatch = boom  # type: ignore[assignment]
    try:
        # Re-import the layers so they pick up the boom-versions on
        # their lazy imports
        importlib.reload(policy_check)
        importlib.reload(agent_router)
        importlib.reload(oc)
        # Each call goes through full wiring including the publish path
        d2 = policy_check.evaluate(
            actor="attacker:bot", tool="read_checklist",
            scopes_granted=[], persist_audit=True,
        )
        if d2.allow:
            print("x policy under outage should still default-deny")
            return 1
        r2 = agent_router.classify("xyz")
        if r2.intent != "unknown":
            print("x router under outage should still classify")
            return 1
        dec2, _ = oc.evaluate_dispatch(
            requesting_agent="council:author", target_agent="council:reviewer",
            capability="critique_proposal", scopes_granted=[],
        )
        if dec2 is None:
            print("x openclaw under outage should still return decision")
            return 1
    finally:
        # Restore originals
        event_publisher.publish_policy_decision = original["policy"]
        event_publisher.publish_router_classification = original["router"]
        event_publisher.publish_openclaw_dispatch = original["openclaw"]
    print("  ok: 3 layers complete normally even when Kafka publish raises")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
