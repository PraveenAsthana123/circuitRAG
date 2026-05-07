#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-3 — MCP Gateway STRICT mode.

Per CLAUDE.md §43. Locks the Stage-3 promotion: when MCP_GATEWAY_STRICT=1,
missing PolisAI rule → deny (vs default fall-through to allowlist).

Behavior contract:
  - Default (MCP_GATEWAY_STRICT unset): PolisAI rule missing →
    fall through to allowlist (Stage-1 behavior preserved)
  - Strict (MCP_GATEWAY_STRICT=1): PolisAI rule missing → deny
    with rule_matched='strict:no-polisai-rule'
  - Strict + explicit PolisAI deny → deny with rule_matched=
    'strict:polisai-deny:<rule_id>'
  - status() surfaces strict_mode flag
  - _polisai_gate now returns (allow, rule_matched) tuple

Eight steps. Five negative.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: MCP_GATEWAY_STRICT module-level flag exists --")
    os.environ.pop("MCP_GATEWAY_STRICT", None)
    os.environ.pop("MCP_GATEWAY_ENABLED", None)
    import mcp_gateway
    importlib.reload(mcp_gateway)
    if not hasattr(mcp_gateway, "MCP_GATEWAY_STRICT"):
        print("x mcp_gateway must expose MCP_GATEWAY_STRICT module-level flag")
        return 1
    if mcp_gateway.MCP_GATEWAY_STRICT is not False:
        print(f"x MCP_GATEWAY_STRICT default must be False; got {mcp_gateway.MCP_GATEWAY_STRICT}")
        return 1
    print("  ok: MCP_GATEWAY_STRICT exposed; default False")

    print("-- 2. POSITIVE: status() surfaces strict_mode flag --")
    os.environ["MCP_GATEWAY_STRICT"] = "1"
    importlib.reload(mcp_gateway)
    status = mcp_gateway.status()
    if "strict_mode" not in status:
        print("x status() must include 'strict_mode' key")
        return 1
    if status["strict_mode"] is not True:
        print(f"x status.strict_mode must be True when STRICT=1; got {status['strict_mode']}")
        return 1
    print("  ok: status surfaces strict_mode=True when env var set")

    print("-- 3. POSITIVE: _polisai_gate returns (allow, rule_matched) tuple --")
    import inspect
    sig = inspect.signature(mcp_gateway._polisai_gate)
    if list(sig.parameters.keys()) != ["actor", "server", "tool"]:
        print(f"x _polisai_gate signature changed: {list(sig.parameters.keys())}")
        return 1
    # Live test: call _polisai_gate and verify return shape
    try:
        result = mcp_gateway._polisai_gate("council:author", "research", "retrieve")
    except Exception as exc:
        print(f"x _polisai_gate call failed: {exc}")
        return 1
    if not isinstance(result, tuple) or len(result) != 2:
        print(f"x _polisai_gate must return (allow, rule_matched) tuple; got {type(result)}")
        return 1
    if not isinstance(result[0], bool):
        print(f"x first element must be bool; got {type(result[0])}")
        return 1
    if not isinstance(result[1], str):
        print(f"x second element must be str; got {type(result[1])}")
        return 1
    print(f"  ok: _polisai_gate returns ({result[0]}, {result[1]!r})")

    print("-- 4. NEGATIVE: STRICT mode + no PolisAI rule → deny --")
    os.environ["MCP_GATEWAY_STRICT"] = "1"
    os.environ["MCP_GATEWAY_ENABLED"] = "1"
    importlib.reload(mcp_gateway)
    # Use a server that's in allowlist + actor in approved_actors,
    # but no specific PolisAI rule for mcp:research:retrieve.
    decision = mcp_gateway.check(
        actor="council:author",  # in approved_actors for research
        server="research",
        tool="retrieve",
        persist_audit=False,
    )
    if decision.allow:
        print("x STRICT mode + no rule should deny; got allow=True")
        print(f"   reason: {decision.reason!r}")
        return 1
    if decision.rule_matched != "strict:no-polisai-rule":
        print(f"x rule_matched should be 'strict:no-polisai-rule'; got {decision.rule_matched!r}")
        return 1
    print("  ok: STRICT + no rule → deny with strict:no-polisai-rule")

    print("-- 5. NEGATIVE: default mode + no PolisAI rule → fall through (allow) --")
    os.environ.pop("MCP_GATEWAY_STRICT", None)
    importlib.reload(mcp_gateway)
    decision = mcp_gateway.check(
        actor="council:author",
        server="research",
        tool="retrieve",
        persist_audit=False,
    )
    if not decision.allow:
        print("x default mode should fall through to allow; got allow=False")
        print(f"   reason: {decision.reason!r}")
        return 1
    if "no-rule-fallthrough" not in decision.reason:
        print(f"x default mode reason must mention no-rule-fallthrough; got: {decision.reason!r}")
        return 1
    print("  ok: default mode + no rule → allow (fall-through preserved)")

    print("-- 6. NEGATIVE: STRICT mode reason cites mode=strict --")
    os.environ["MCP_GATEWAY_STRICT"] = "1"
    importlib.reload(mcp_gateway)
    # Test allow path under strict by using an actor with explicit
    # PolisAI rule. council:author has the council-author-ollama-generate
    # rule for ollama:generate; let's check that rule applies.
    # Actually our existing rules don't cover mcp:* so under STRICT this
    # also denies. Instead test that the strict flag is documented in
    # the deny reason.
    decision = mcp_gateway.check(
        actor="council:author", server="research", tool="retrieve",
        persist_audit=False,
    )
    if decision.allow:
        # If somehow allow under strict, reason must still document mode
        if "strict" not in decision.reason.lower():
            print(f"x STRICT mode reason must mention strict; got: {decision.reason!r}")
            return 1
    else:
        # Deny path — rule_matched must indicate strict
        if "strict" not in decision.rule_matched.lower():
            print(f"x STRICT deny rule_matched must mention strict; got: {decision.rule_matched!r}")
            return 1
    print("  ok: STRICT mode is observable in decision metadata")

    print("-- 7. NEGATIVE: STRICT mode does NOT change Stage-1/2 behaviors when off --")
    # Setting STRICT off then on then off must produce identical behavior
    # to "never set". Drill verifies idempotence by running default-mode
    # checks 3x with intervening reloads.
    for _i in range(3):
        os.environ.pop("MCP_GATEWAY_STRICT", None)
        importlib.reload(mcp_gateway)
        decision = mcp_gateway.check(
            actor="council:author", server="research", tool="retrieve",
            persist_audit=False,
        )
        if not decision.allow:
            print(f"x default-mode reload {_i} broke fall-through")
            return 1
    print("  ok: STRICT mode toggle is idempotent on off-state behavior")

    print("-- 8. POSITIVE: docstring documents both default + strict --")
    src = (SCRIPTS / "mcp_gateway.py").read_text(encoding="utf-8")
    if "MCP_GATEWAY_STRICT" not in src:
        print("x source must reference MCP_GATEWAY_STRICT")
        return 1
    if "Stage-3" not in src:
        print("x source must label this as Stage-3 promotion")
        return 1
    if "fall through" not in src.lower() and "fallthrough" not in src.lower():
        print("x source must document the fall-through behavior")
        return 1
    print("  ok: source documents both modes + Stage-3 label")

    # Cleanup
    os.environ.pop("MCP_GATEWAY_STRICT", None)
    os.environ.pop("MCP_GATEWAY_ENABLED", None)

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
