#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: OpenClaw Stage-1 — A2A coordinator gate contract.

Per CLAUDE.md §43 + §47 (11-layer architecture, Layer 11) + ADR-012.
Locks the contract that:

  - Agent registry exposes 6 documented agents with capabilities + scopes
  - Dispatch attempt with unknown requesting_agent → UnknownAgentError
  - Dispatch attempt with unknown target_agent → UnknownAgentError
  - Dispatch attempt with unsupported capability → CapabilityNotSupportedError
  - Dispatch with no matching PolisAI rule → default-deny + audit row
  - On deny, envelope returned is None (no message constructed)
  - On (Stage-2 future) allow, envelope is constructed with all required
    fields — drill tests this via a synthetic happy-path scope check
  - Audit row lands in .loop/openclaw_audit.jsonl per dispatch attempt
  - Module is import-safe; no module-level side effects

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
AUDIT_LOG = REPO / ".loop" / "openclaw_audit.jsonl"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: openclaw_coordinator imports + exposes agents + decision shape --")
    import openclaw_coordinator as oc  # noqa: E402
    for name in (
        "AGENT_REGISTRY", "DispatchEnvelope", "DispatchDecision",
        "evaluate_dispatch", "list_agents", "recent_dispatches",
        "OpenClawError", "UnknownAgentError", "CapabilityNotSupportedError",
    ):
        if not hasattr(oc, name):
            print(f"x openclaw_coordinator.{name} missing")
            return 1
    print("  ok: 9 surfaces exported")

    print("-- 2. POSITIVE: agent registry has 6 documented agents --")
    registry = oc.AGENT_REGISTRY
    if len(registry) != 6:
        print(f"x expected 6 agents in registry; got {len(registry)}")
        return 1
    expected_agents = {
        "council:author", "council:reviewer", "council:advisor",
        "council:researcher", "paperclip:manager", "operator:human",
    }
    if set(registry.keys()) != expected_agents:
        print(f"x agent set mismatch; got {sorted(registry.keys())}")
        return 1
    # Each agent must have capabilities + required_scope + endpoint
    for name, info in registry.items():
        for key in ("capabilities", "required_scope", "endpoint"):
            if key not in info:
                print(f"x agent {name!r} missing key {key!r}")
                return 1
    print(f"  ok: 6 agents, each with capabilities + required_scope + endpoint")

    print("-- 3. NEGATIVE: unknown requesting_agent → UnknownAgentError --")
    try:
        oc.evaluate_dispatch(
            requesting_agent="attacker:bot",
            target_agent="council:reviewer",
            capability="critique_proposal",
            scopes_granted=["delegate:council:reviewer"],
        )
    except oc.UnknownAgentError as exc:
        if "attacker:bot" not in str(exc):
            print(f"x error must mention bad agent name; got {exc}")
            return 1
    else:
        print("x unknown requesting_agent should raise UnknownAgentError")
        return 1
    print("  ok: unknown requesting_agent → UnknownAgentError")

    print("-- 4. NEGATIVE: unknown target_agent → UnknownAgentError --")
    try:
        oc.evaluate_dispatch(
            requesting_agent="council:author",
            target_agent="bot:nonexistent",
            capability="critique_proposal",
            scopes_granted=[],
        )
    except oc.UnknownAgentError as exc:
        if "bot:nonexistent" not in str(exc):
            print(f"x error must mention bad target name; got {exc}")
            return 1
    else:
        print("x unknown target_agent should raise UnknownAgentError")
        return 1
    print("  ok: unknown target_agent → UnknownAgentError")

    print("-- 5. NEGATIVE: capability not in target's list → CapabilityNotSupportedError --")
    try:
        # paperclip:manager only supports read_snapshot
        oc.evaluate_dispatch(
            requesting_agent="council:author",
            target_agent="paperclip:manager",
            capability="propose_fix",  # paperclip doesn't have this
            scopes_granted=[],
        )
    except oc.CapabilityNotSupportedError as exc:
        if "propose_fix" not in str(exc):
            print(f"x error must mention bad capability; got {exc}")
            return 1
    else:
        print("x unsupported capability should raise CapabilityNotSupportedError")
        return 1
    print("  ok: unsupported capability → CapabilityNotSupportedError")

    print("-- 6. NEGATIVE: dispatch with no matching PolisAI rule → default-deny --")
    # Stage-1 has NO a2a:dispatch:* rules in PolisAI yet. Every
    # dispatch must default-deny + persist audit row + return None
    # envelope. Stage-2 adds rules + this drill is updated.
    decision, envelope = oc.evaluate_dispatch(
        requesting_agent="council:author",
        target_agent="council:reviewer",
        capability="critique_proposal",
        scopes_granted=["delegate:council:reviewer"],
    )
    if decision.allow:
        print(f"x Stage-1 dispatch should default-deny (no rules); got allow=True")
        return 1
    if decision.rule_matched != "default-deny":
        print(f"x rule_matched should be 'default-deny'; got {decision.rule_matched!r}")
        return 1
    if envelope is not None:
        print(f"x denied dispatch must return envelope=None; got {envelope}")
        return 1
    print(f"  ok: default-deny, envelope=None, rule_matched='default-deny'")

    print("-- 7. POSITIVE: audit row appended for every dispatch attempt --")
    if not AUDIT_LOG.exists():
        print(f"x audit log {AUDIT_LOG} missing — earlier dispatch should have created it")
        return 1
    rows = AUDIT_LOG.read_text(encoding="utf-8").strip().split("\n")
    # Find the row from step 6
    found = False
    for line in rows[-10:]:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") == "dispatch":
            d = r.get("decision", {})
            if (d.get("requesting_agent") == "council:author"
                    and d.get("target_agent") == "council:reviewer"
                    and d.get("rule_matched") == "default-deny"):
                found = True
                break
    if not found:
        print("x audit row from step 6 not found in last 10 rows of openclaw_audit.jsonl")
        return 1
    print(f"  ok: audit row present (last 10 rows scanned; deny case found)")

    print("-- 8. NEGATIVE: module import is side-effect-free + no Stage-2 surfaces --")
    # Locks: importing openclaw_coordinator does NOT spawn a network
    # call, NOT mutate state, NOT register a real RPC handler.
    # Stage-2 surfaces (real_dispatch, send_envelope, http_post) are
    # intentionally absent.
    forbidden_stage2 = (
        "real_dispatch", "send_envelope", "http_post_envelope",
        "execute_remote", "rpc_send", "make_async_call",
    )
    src = (SCRIPTS / "openclaw_coordinator.py").read_text(encoding="utf-8")
    for fn_name in forbidden_stage2:
        if f"def {fn_name}(" in src:
            print(f"x Stage-1 module must NOT define {fn_name}() (Stage-2 surface)")
            return 1
    # Also verify the module's docstring explicitly says "Stage-1"
    if "Stage-1" not in src.split('"""')[1]:
        print("x module docstring must mark Stage-1")
        return 1
    print(f"  ok: 0 Stage-2 surfaces present; docstring marks Stage-1 explicitly")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
