#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: MCP Gateway Stage-1 — allowlist + PolisAI gate + audit.

Per CLAUDE.md §43 + §56 + the 2026-05-04 enterprise-architecture page's
brutal rule: "do not allow direct MCP access. Put every MCP server
behind MCP Gateway + OPA + sandbox + audit."

Locks:

  - Module exposes is_available / check / status / 4 exception types
  - Default disabled (MCP_GATEWAY_ENABLED=1 opt-in)
  - check() raises MCPGatewayDisabled when feature flag off
  - Allowlist file present + has 9 servers + default-deny
  - Server NOT in allowlist → allow=False + rule_matched=default-deny
  - Actor NOT in approved_actors → allow=False + rule_matched=
    server-allowlist:<server>
  - Approved actor + rate-limit-not-exceeded → allow=True
  - Audit row persisted on every decision
  - All 4 risk tiers documented in allowlist (low/medium/high/critical)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
ALLOWLIST = REPO / "config" / "mcp" / "allowlist.json"
AUDIT_LOG = REPO / ".loop" / "mcp_gateway_audit.jsonl"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: module exports the 4 contract surfaces + 4 exceptions --")
    os.environ.pop("MCP_GATEWAY_ENABLED", None)
    import mcp_gateway
    importlib.reload(mcp_gateway)
    for name in (
        "is_available", "check", "status",
        "MCPGatewayDisabled", "ServerNotAllowed", "ActorNotApproved", "RateLimitExceeded",
        "GatewayDecision",
    ):
        if not hasattr(mcp_gateway, name):
            print(f"x mcp_gateway.{name} missing")
            return 1
    print("  ok: 8 surfaces exported")

    print("-- 2. POSITIVE: allowlist has 9 servers + default-deny + 4 risk tiers --")
    if not ALLOWLIST.exists():
        print(f"x {ALLOWLIST} missing")
        return 1
    doc = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    if doc.get("default_decision") != "deny":
        print(f"x default_decision must be 'deny'; got {doc.get('default_decision')!r}")
        return 1
    servers = doc.get("servers", [])
    if len(servers) != 9:
        print(f"x expected 9 servers; got {len(servers)}")
        return 1
    risks = {s["risk"] for s in servers}
    expected_risks = {"low", "medium", "high", "critical"}
    missing_risks = expected_risks - risks
    if missing_risks:
        print(f"x risk tiers missing: {missing_risks}")
        return 1
    # Each server entry must have required fields
    for s in servers:
        for key in ("name", "module", "risk", "approved_actors", "max_calls_per_minute", "rationale"):
            if key not in s:
                print(f"x server {s.get('name', '?')} missing key: {key!r}")
                return 1
    print(f"  ok: 9 servers, default-deny, 4 risk tiers, all required fields")

    print("-- 3. NEGATIVE: default is_available() = False (MCP_GATEWAY_ENABLED unset) --")
    if mcp_gateway.is_available():
        print("x default is_available should be False")
        return 1
    print("  ok: feature flag opt-in posture preserved")

    print("-- 4. NEGATIVE: check() raises MCPGatewayDisabled when feature flag off --")
    raised = False
    try:
        mcp_gateway.check(actor="council:author", server="research", tool="retrieve")
    except mcp_gateway.MCPGatewayDisabled as exc:
        raised = True
        if "MCP_GATEWAY_ENABLED" not in str(exc):
            print(f"x error must cite MCP_GATEWAY_ENABLED; got: {str(exc)[:200]}")
            return 1
    if not raised:
        print("x check() should have raised MCPGatewayDisabled")
        return 1
    print("  ok: MCPGatewayDisabled raised + cites feature flag")

    print("-- 5. NEGATIVE: server NOT in allowlist → default-deny --")
    os.environ["MCP_GATEWAY_ENABLED"] = "1"
    importlib.reload(mcp_gateway)
    decision = mcp_gateway.check(
        actor="council:author", server="fake-server", tool="x",
        persist_audit=False,
    )
    if decision.allow:
        print(f"x unknown server should default-deny; got allow=True")
        return 1
    if decision.rule_matched != "default-deny":
        print(f"x rule_matched should be 'default-deny'; got {decision.rule_matched!r}")
        return 1
    print("  ok: unknown server → default-deny + rule_matched=default-deny")

    print("-- 6. NEGATIVE: actor NOT in approved_actors → server-allowlist deny --")
    decision = mcp_gateway.check(
        actor="attacker:bot", server="research", tool="retrieve",
        persist_audit=False,
    )
    if decision.allow:
        print(f"x unauthorized actor should be denied; got allow=True")
        return 1
    if "approved_actors" not in decision.reason:
        print(f"x reason must cite approved_actors; got: {decision.reason!r}")
        return 1
    if decision.rule_matched != "server-allowlist:research":
        print(f"x rule_matched should be 'server-allowlist:research'; got {decision.rule_matched!r}")
        return 1
    print("  ok: unauthorized actor → deny + rule_matched=server-allowlist:research")

    print("-- 7. POSITIVE: approved actor + rate-limit OK → allow=True --")
    importlib.reload(mcp_gateway)  # reset rate-limit state
    decision = mcp_gateway.check(
        actor="council:author", server="research", tool="retrieve",
        persist_audit=False,
    )
    if not decision.allow:
        print(f"x approved actor should allow; got allow=False, reason={decision.reason!r}")
        return 1
    if decision.risk != "medium":
        print(f"x risk should be 'medium' for research server; got {decision.risk!r}")
        return 1
    print(f"  ok: approved actor + rate-OK → allow=True; risk=medium")

    print("-- 8. POSITIVE: audit row persisted on every decision (allow + deny) --")
    pre_count = (
        AUDIT_LOG.read_text(encoding="utf-8").count("\n") if AUDIT_LOG.exists() else 0
    )
    importlib.reload(mcp_gateway)
    # Fire 1 allow + 1 deny WITH audit
    mcp_gateway.check(actor="council:author", server="research", tool="retrieve")
    mcp_gateway.check(actor="attacker:bot", server="research", tool="retrieve")
    post_count = AUDIT_LOG.read_text(encoding="utf-8").count("\n") if AUDIT_LOG.exists() else 0
    delta = post_count - pre_count
    if delta != 2:
        print(f"x expected 2 new audit rows; got {delta}")
        return 1
    # Last 2 rows must have correct outcomes
    rows = AUDIT_LOG.read_text(encoding="utf-8").strip().split("\n")[-2:]
    parsed = [json.loads(r) for r in rows]
    outcomes = [r.get("allow") for r in parsed]
    if outcomes != [True, False]:
        print(f"x audit rows wrong outcomes: {outcomes}")
        return 1
    print(f"  ok: 2 audit rows appended (1 allow + 1 deny)")

    # Cleanup
    os.environ.pop("MCP_GATEWAY_ENABLED", None)

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
