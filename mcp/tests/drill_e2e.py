"""
End-to-end MCP drill for DEMO-DAY-3-MCP.

Run against a live MCP HR server (default localhost:8090). Covers:

  1. tools/list returns contract
  2. hr.policy_lookup (read) — happy path
  3. hr.leave_request (write) — happy path + ticket_id
  4. Idempotency: same Idempotency-Key returns same ticket_id, idempotent_replay=True
  5. CB trips after failure_threshold failures (via MCP_INJECT_FAIL)
  6. CB OPEN → agent persists draft instead of calling
  7. Recovery: unset failure flag, wait recovery_timeout, probe succeeds

Run:
    MCP_BASE_URL=http://127.0.0.1:8090 python mcp/tests/drill_e2e.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx

from mcp.client import MCPClient


BASE = os.getenv("MCP_BASE_URL", "http://127.0.0.1:8090")


async def set_fail_mode(on: bool) -> None:
    # We toggle via env on the server side in a real test by restarting.
    # For an in-process drill we rely on the server being started with the
    # right MCP_INJECT_FAIL value; the caller script handles that.
    pass


async def main() -> int:
    async with httpx.AsyncClient(timeout=5.0) as probe:
        r = await probe.get(f"{BASE}/health")
        assert r.status_code == 200, f"server not healthy: {r.status_code}"

    # Use low thresholds so the drill doesn't take forever
    client = MCPClient(base_url=BASE, failure_threshold=3, recovery_timeout=5.0)
    failures = 0

    try:
        # 1 — list tools
        tools = await client.list_tools()
        assert len(tools) >= 2, f"expected ≥2 tools, got {tools}"
        print(f"[1] tools/list → {len(tools)} tools advertised")

        # 2 — happy read
        r = await client.call_tool("hr.policy_lookup", {"policy_name": "leave"}, tenant_id="acme")
        assert r.ok, f"policy_lookup failed: {r}"
        assert "paid leave" in r.data["text"], f"bad policy text: {r.data}"
        print(f"[2] hr.policy_lookup → ok text='{r.data['text'][:40]}...'")

        # 3 — happy write
        r = await client.call_tool(
            "hr.leave_request",
            {"employee_id": "E123", "days": 3, "reason": "family event"},
            tenant_id="acme",
            idempotency_key="drill-key-1",
        )
        assert r.ok and r.data["ticket_id"].startswith("HR-"), f"leave_request failed: {r}"
        ticket_id = r.data["ticket_id"]
        print(f"[3] hr.leave_request → ticket_id={ticket_id} status={r.data['status']}")

        # 4 — idempotent replay
        r2 = await client.call_tool(
            "hr.leave_request",
            {"employee_id": "E123", "days": 3, "reason": "family event"},
            tenant_id="acme",
            idempotency_key="drill-key-1",
        )
        assert r2.ok and r2.data["ticket_id"] == ticket_id, f"idempotency broke: {r2}"
        assert r2.idempotent_replay, "expected idempotent_replay=True"
        print(f"[4] idempotent replay → same ticket_id={ticket_id} replay=True")

        # 5 — CB drill
        # Switch server into fail-inject mode via env on a SIDE endpoint.
        # We simulate it by pointing a second client at a dead port so every
        # call 502s + trips the CB after 3 failures.
        bad = MCPClient(base_url="http://127.0.0.1:19999", failure_threshold=3, recovery_timeout=5.0)
        for i in range(4):
            r = await bad.call_tool(
                "hr.leave_request",
                {"employee_id": "E999", "days": 1, "reason": f"chaos-{i}"},
                tenant_id="acme",
            )
            if r.degraded:
                failures += 1
        print(f"[5] dead-server calls → {failures} degraded; cb_state={bad.cb_state}")
        assert bad.cb_state == "open", f"expected OPEN, got {bad.cb_state}"

        # 6 — CB OPEN → draft persisted; no HTTP call happens
        before_drafts = len(MCPClient.drafts())
        r = await bad.call_tool(
            "hr.leave_request",
            {"employee_id": "E999", "days": 2, "reason": "post-open"},
            tenant_id="acme",
        )
        after_drafts = len(MCPClient.drafts())
        assert r.degraded and r.draft_id is not None, f"expected degraded+draft: {r}"
        assert after_drafts == before_drafts + 1, f"draft not persisted"
        print(f"[6] cb=OPEN → draft persisted id={r.draft_id} drafts_total={after_drafts}")

        # 7 — recovery
        print("[7] waiting recovery_timeout (5s) for HALF_OPEN probe...")
        await asyncio.sleep(5.5)
        # Point bad client at the real server to simulate dependency return
        bad._base = BASE.rstrip("/")
        r = await bad.call_tool(
            "hr.policy_lookup",
            {"policy_name": "travel"},
            tenant_id="acme",
        )
        assert r.ok, f"recovery probe failed: {r}"
        assert bad.cb_state == "closed", f"expected CLOSED after probe, got {bad.cb_state}"
        print(f"[7] recovery → cb_state={bad.cb_state} ok={r.ok}")

        print()
        print("=" * 60)
        print("ALL 7 E2E STEPS PASSED")
        print("=" * 60)
        return 0

    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
