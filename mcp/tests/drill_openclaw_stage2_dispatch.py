#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: OpenClaw Stage-2 — dispatch() + transport via MCP gateway.

Per CLAUDE.md §43 + §47 + §44 autonomous-loop. Locks the Stage-2
promotion of OpenClaw from gate-only to gate + envelope + transport
attempt.

Behavior contract:
  - dispatch() exists as a public function alongside evaluate_dispatch()
  - DispatchResult dataclass exposes: ok / decision / envelope /
    transport_error / response_data
  - dispatch() ALWAYS calls evaluate_dispatch() FIRST (gate-before-transport)
  - When evaluate_dispatch denies → DispatchResult(ok=False) with NO
    transport attempt
  - When evaluate_dispatch allows + target endpoint is mcp:// →
    routes through mcp_gateway.check (defense in depth)
  - When mcp_gateway denies → DispatchResult(ok=False) with envelope
    populated (gate passed but transport denied)
  - When mcp_gateway disabled (Stage-2 default) → DispatchResult(ok=True)
    with transport_error="mcp_gateway_disabled (Stage-2 no-op)"
  - Existing evaluate_dispatch contract unchanged (Stage-1 callers
    still work)

Eight steps. Five negative.
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: openclaw_coordinator exposes dispatch() + DispatchResult --")
    os.environ.pop("MCP_GATEWAY_ENABLED", None)
    import openclaw_coordinator as oc
    importlib.reload(oc)
    if not hasattr(oc, "dispatch"):
        print("x openclaw_coordinator.dispatch missing")
        return 1
    if not hasattr(oc, "DispatchResult"):
        print("x openclaw_coordinator.DispatchResult missing")
        return 1
    print("  ok: dispatch + DispatchResult exported")

    print("-- 2. POSITIVE: dispatch() signature uses keyword-only args --")
    sig = inspect.signature(oc.dispatch)
    expected = ["requesting_agent", "target_agent", "capability",
                "scopes_granted", "payload", "correlation_id"]
    actual = list(sig.parameters.keys())
    if actual != expected:
        print(f"x signature mismatch — expected {expected}, got {actual}")
        return 1
    # All params must be keyword-only (matches evaluate_dispatch convention)
    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            print(f"x param {name!r} must be keyword-only; kind={param.kind}")
            return 1
    print(f"  ok: 6 keyword-only params")

    print("-- 3. POSITIVE: DispatchResult has 5 fields --")
    sample = oc.DispatchResult(
        ok=False,
        decision=oc.DispatchDecision(
            allow=False, reason="x", rule_matched="default-deny",
            requesting_agent="x", target_agent="y", capability="z",
        ),
    )
    sample_dict = sample.to_dict()
    required_fields = {"ok", "decision", "envelope", "transport_error", "response_data"}
    missing = required_fields - set(sample_dict.keys())
    if missing:
        print(f"x DispatchResult missing fields: {missing}")
        return 1
    print(f"  ok: 5 DispatchResult fields present")

    print("-- 4. NEGATIVE: dispatch() with no PolisAI rule → ok=False (gate denies) --")
    # Stage-1 has no a2a:dispatch:* rules; default-deny posture.
    result = oc.dispatch(
        requesting_agent="council:author",
        target_agent="council:reviewer",
        capability="critique_proposal",
        scopes_granted=["delegate:council:reviewer"],
    )
    if result.ok:
        print(f"x dispatch should default-deny; got ok=True")
        return 1
    if result.decision.allow:
        print(f"x decision.allow should be False")
        return 1
    if result.envelope is not None:
        print(f"x envelope should be None on deny; got {result.envelope}")
        return 1
    if "openclaw gate denied" not in (result.transport_error or ""):
        print(f"x transport_error should cite gate denial; got {result.transport_error!r}")
        return 1
    print("  ok: gate-deny → ok=False, envelope=None, error cites gate")

    print("-- 5. NEGATIVE: dispatch() with unknown agent raises UnknownAgentError --")
    raised = False
    try:
        oc.dispatch(
            requesting_agent="attacker:bot",
            target_agent="council:reviewer",
            capability="critique_proposal",
        )
    except oc.UnknownAgentError:
        raised = True
    if not raised:
        print("x unknown agent should raise UnknownAgentError")
        return 1
    print("  ok: unknown agent → UnknownAgentError (not silent deny)")

    print("-- 6. NEGATIVE: dispatch() with unsupported capability raises CapabilityNotSupported --")
    raised = False
    try:
        oc.dispatch(
            requesting_agent="council:author",
            target_agent="paperclip:manager",  # only supports read_snapshot
            capability="propose_fix",
        )
    except oc.CapabilityNotSupportedError:
        raised = True
    if not raised:
        print("x unsupported capability should raise CapabilityNotSupportedError")
        return 1
    print("  ok: unsupported capability → CapabilityNotSupportedError")

    print("-- 7. NEGATIVE: dispatch() calls evaluate_dispatch FIRST (gate before transport) --")
    # String-position check: in source, evaluate_dispatch must precede
    # any mcp_gateway.check call inside dispatch().
    src = (SCRIPTS / "openclaw_coordinator.py").read_text(encoding="utf-8")
    func_start = src.find("def dispatch(")
    func_end = src.find("\ndef ", func_start + 10)
    body = src[func_start:func_end if func_end != -1 else len(src)]

    eval_pos = body.find("evaluate_dispatch(")
    gateway_pos = body.find("_gateway_check(")
    if eval_pos == -1:
        print("x dispatch() must call evaluate_dispatch")
        return 1
    if gateway_pos != -1 and eval_pos > gateway_pos:
        print(f"x evaluate_dispatch ({eval_pos}) must precede _gateway_check ({gateway_pos})")
        return 1
    print("  ok: evaluate_dispatch precedes any transport call (gate-before-transport)")

    print("-- 8. POSITIVE: existing Stage-1 evaluate_dispatch contract unchanged --")
    # Stage-2 must NOT break Stage-1 callers — evaluate_dispatch
    # signature + return type stay the same.
    eval_sig = inspect.signature(oc.evaluate_dispatch)
    eval_params = list(eval_sig.parameters.keys())
    expected_eval = ["requesting_agent", "target_agent", "capability",
                     "scopes_granted", "payload", "correlation_id"]
    if eval_params != expected_eval:
        print(f"x evaluate_dispatch signature changed: {eval_params}")
        return 1
    # Direct call still returns (decision, envelope) tuple
    decision, envelope = oc.evaluate_dispatch(
        requesting_agent="council:author",
        target_agent="council:reviewer",
        capability="critique_proposal",
        scopes_granted=[],
    )
    if not isinstance(decision, oc.DispatchDecision):
        print(f"x evaluate_dispatch first return must be DispatchDecision")
        return 1
    print("  ok: Stage-1 evaluate_dispatch contract preserved")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
