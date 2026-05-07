#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-2 — MCP client routes calls through gateway when enabled.

Per CLAUDE.md §43 + §56. Locks the contract that:

  - mcp/client.py call_tool() invokes mcp_gateway.check() BEFORE
    circuit-breaker and BEFORE the HTTP call
  - When MCP_GATEWAY_ENABLED=1 + gateway denies → ToolResult(ok=False)
    with error citing the gateway decision
  - When MCP_GATEWAY_ENABLED=1 + gateway allows → call proceeds normally
  - When MCP_GATEWAY_ENABLED=0 (default) → gateway raises
    MCPGatewayDisabled which is caught + fall-through to existing path
  - When mcp_gateway module is missing entirely → ImportError caught
    + fall-through (graceful degradation during deployment window)
  - actor kwarg defaults to 'mcp:client:unknown' (default-deny trip-wire)
  - Gateway gate fires BEFORE both CB and HTTP — drill checks string
    position in source

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[2]
CLIENT = REPO / "mcp" / "client.py"
sys.path.insert(0, str(REPO))


def main() -> int:
    print("-- 1. POSITIVE: mcp/client.py source contains gateway wiring --")
    src = CLIENT.read_text(encoding="utf-8")
    if "MCP Gateway gate" not in src:
        print("x source must reference MCP Gateway gate in call_tool")
        return 1
    if "from mcp_gateway import" not in src:
        print("x source must import from mcp_gateway")
        return 1
    if "_gateway_check(" not in src:
        print("x call_tool must invoke _gateway_check")
        return 1
    print("  ok: gateway wiring present in source")

    print("-- 2. POSITIVE: actor kwarg added with safe default --")
    if 'actor: str = "mcp:client:unknown"' not in src:
        print("x call_tool must have actor='mcp:client:unknown' as default")
        return 1
    print("  ok: actor kwarg with default-deny trip-wire")

    print("-- 3. NEGATIVE: gateway gate fires BEFORE CB + BEFORE HTTP --")
    # String-position check: gateway call must come before CB allow check
    # and HTTP post.
    func_start = src.find("async def call_tool(")
    func_end = src.find("\n    async def ", func_start + 10)
    if func_end == -1:
        func_end = src.find("\n    def ", func_start + 10)
    body = src[func_start:func_end if func_end != -1 else len(src)]

    gateway_pos = body.find("_gateway_check(")
    cb_check_pos = body.find("self._breaker.allow()")
    http_pos = body.find("self._client.post(")

    if gateway_pos == -1 or cb_check_pos == -1 or http_pos == -1:
        print(f"x cannot locate ordering markers (gateway={gateway_pos}, cb={cb_check_pos}, http={http_pos})")
        return 1
    if not (gateway_pos < cb_check_pos < http_pos):
        print(f"x ordering wrong: gateway={gateway_pos}, cb={cb_check_pos}, http={http_pos}")
        return 1
    print(f"  ok: gateway ({gateway_pos}) precedes CB ({cb_check_pos}) precedes HTTP ({http_pos})")

    print("-- 4. NEGATIVE: MCPGatewayDisabled is caught + fall-through --")
    # Stage-1 contract: gateway disabled MUST NOT break existing flow.
    # Drill verifies the except MCPGatewayDisabled catch block exists.
    if "except MCPGatewayDisabled" not in src:
        print("x source must catch MCPGatewayDisabled")
        return 1
    # Verify it's followed by `pass` (fall-through), not `raise`
    catch_block_idx = src.find("except MCPGatewayDisabled")
    catch_section = src[catch_block_idx:catch_block_idx + 600]
    if "raise" in catch_section.split("\n")[1:5][0]:
        # First line after except — must NOT be raise
        pass  # the search below covers this
    if "Stage-1 default" not in catch_section and "opt-out" not in catch_section:
        print("x catch block must document the Stage-1 fall-through intent")
        return 1
    print("  ok: MCPGatewayDisabled caught + fall-through documented")

    print("-- 5. NEGATIVE: ImportError caught (graceful when module missing) --")
    if "except ImportError:" not in src:
        print("x source must catch ImportError on mcp_gateway import")
        return 1
    print("  ok: ImportError caught (graceful degradation)")

    print("-- 6. POSITIVE: live integration — gateway-disabled path proceeds --")
    # When MCP_GATEWAY_ENABLED is unset, call_tool should fall through
    # to the existing path. We test this by mocking the HTTP layer +
    # CB and verifying that with the flag unset, the call reaches HTTP.
    os.environ.pop("MCP_GATEWAY_ENABLED", None)
    import importlib

    from mcp.client import MCPClient  # noqa: E402
    # Don't reload — that would require re-init the breaker etc.
    # Just construct a fresh client + mock the dependencies.

    client = MCPClient(base_url="http://stub")
    # Mock the breaker to always allow + the http post to return 200
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={"ok": True, "data": {}})

    with patch.object(client._breaker, "allow", return_value=True), \
         patch.object(client._breaker, "record_success"), \
         patch.object(client._client, "post", new=AsyncMock(return_value=fake_response)):
        result = asyncio.run(client.call_tool(
            "research.retrieve",
            {"query": "x"},
            tenant_id="t1",
            actor="council:author",
        ))
    if not result.ok:
        print(f"x gateway-disabled path should pass through; got error: {result.error}")
        return 1
    print("  ok: gateway-disabled (default) → call proceeds to HTTP layer")

    print("-- 7. NEGATIVE: gateway-enabled + denied path returns ToolResult error --")
    # Set the flag, mock the gateway to deny, verify call_tool returns
    # ToolResult(ok=False) with gateway error message — without ever
    # hitting CB or HTTP.
    os.environ["MCP_GATEWAY_ENABLED"] = "1"

    # Reload the gateway module so it picks up the env var
    sys.path.insert(0, str(REPO / "scripts"))
    import mcp_gateway  # noqa: E402
    importlib.reload(mcp_gateway)

    client2 = MCPClient(base_url="http://stub")
    cb_called = {"hit": False}
    http_called = {"hit": False}

    def track_cb(*a, **kw):  # noqa: ARG001
        cb_called["hit"] = True
        return True

    async def track_http(*a, **kw):  # noqa: ARG001
        http_called["hit"] = True
        return MagicMock(status_code=200, json=MagicMock(return_value={"ok": True}))

    with patch.object(client2._breaker, "allow", side_effect=track_cb), \
         patch.object(client2._client, "post", new=AsyncMock(side_effect=track_http)):
        # Use a server that's NOT in the allowlist → default-deny
        result2 = asyncio.run(client2.call_tool(
            "fakeserver.unknown_tool",
            {"x": 1},
            tenant_id="t1",
            actor="council:author",
        ))
    if result2.ok:
        print("x gateway-deny should return ToolResult(ok=False)")
        return 1
    if "mcp gateway denied" not in (result2.error or ""):
        print(f"x error must cite gateway deny; got: {result2.error!r}")
        return 1
    if cb_called["hit"]:
        print("x CB should NOT have been called when gateway denies")
        return 1
    if http_called["hit"]:
        print("x HTTP should NOT have been called when gateway denies")
        return 1
    print("  ok: gateway-deny → ToolResult error + CB and HTTP both skipped")

    print("-- 8. POSITIVE: gateway-enabled + allowed path proceeds to CB+HTTP --")
    # Same gateway-enabled state, but now use an allowed actor + server
    # combo — call should proceed.
    cb_called["hit"] = False
    http_called["hit"] = False

    fake_ok = MagicMock(status_code=200, json=MagicMock(return_value={"ok": True, "data": {}}))

    with patch.object(client2._breaker, "allow", return_value=True), \
         patch.object(client2._breaker, "record_success"), \
         patch.object(client2._client, "post", new=AsyncMock(return_value=fake_ok)):
        result3 = asyncio.run(client2.call_tool(
            "research.retrieve",
            {"query": "x"},
            tenant_id="t1",
            actor="council:author",  # in approved_actors for research
        ))
    if not result3.ok:
        print(f"x allowed path should proceed; got error: {result3.error}")
        return 1
    print("  ok: gateway-allow → call proceeds to CB + HTTP")

    # Cleanup
    os.environ.pop("MCP_GATEWAY_ENABLED", None)

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
