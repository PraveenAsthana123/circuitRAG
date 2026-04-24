"""
Drill: MCPClient.list_tools respects a TTL — without one, catalog
changes on the MCP server side silently go un-picked-up until
client restart, and the agent's scope pre-check enforces stale
policy indefinitely.

Flow:
 1. MCPClient(tools_cache_ttl_s=2). Call list_tools. tools_fetch_count
    should be 1 (one real round-trip).
 2. Call list_tools 3 more times immediately. tools_fetch_count
    should STILL be 1 — all cache hits within TTL.
 3. Wait 2.5s. Call list_tools. tools_fetch_count becomes 2 — TTL
    expired, a real fetch happened.
 4. Within the new TTL, further calls still return cached
    (fetch_count stays 2).
 5. CB-open degrade path: make the MCP server look dead (fire enough
    bad calls at a bogus base_url client to trip its CB), then call
    list_tools with a stale cache — it must return the stale cache
    rather than raise. fetch_count unchanged.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_tool_catalog_ttl.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import MCPClient  # noqa: E402

MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def main() -> None:
    # sanity: the real MCP must be up or /tools/list would fail
    async with httpx.AsyncClient(timeout=3.0) as c:
        r = await c.get(f"{MCP_BASE}/health")
        if r.status_code != 200:
            fail(f"MCP not reachable at {MCP_BASE}; start it first")

    step("1. fresh MCPClient with TTL=2s — first list_tools → fetch_count=1")
    client = MCPClient(base_url=MCP_BASE, tools_cache_ttl_s=2.0)
    tools = await client.list_tools()
    if len(tools) < 2:
        fail(f"expected >=2 tools, got {len(tools)}")
    if client.tools_fetch_count != 1:
        fail(f"expected fetch_count=1, got {client.tools_fetch_count}")
    tool_names = sorted(t["name"] for t in tools)
    ok(f"fetch_count=1 tools={tool_names}")

    step("2. 3 immediate calls — all cache hits (fetch_count stays 1)")
    for i in range(3):
        t = await client.list_tools()
        if sorted(x["name"] for x in t) != tool_names:
            fail(f"tools changed across cache-hit calls: {t}")
    if client.tools_fetch_count != 1:
        fail(
            f"fetch_count grew on cache hits: expected 1 got "
            f"{client.tools_fetch_count}"
        )
    ok(f"fetch_count=1 after 3 extra calls — cache held")

    step("3. wait 2.5s → next call refetches, fetch_count=2")
    await asyncio.sleep(2.5)
    tools = await client.list_tools()
    if sorted(x["name"] for x in tools) != tool_names:
        fail(f"catalog unexpectedly changed post-TTL: {tools}")
    if client.tools_fetch_count != 2:
        fail(f"expected fetch_count=2 after TTL, got {client.tools_fetch_count}")
    ok(f"fetch_count=2 — TTL-triggered refetch fired")

    step("4. within new TTL — next call still cache hit (fetch_count=2)")
    await client.list_tools()
    if client.tools_fetch_count != 2:
        fail(f"fetch_count moved spuriously: {client.tools_fetch_count}")
    ok(f"fetch_count=2 — new TTL window covering next call")

    await client.close()

    step("5. stale-serve on CB open (fire 3 connect errors to a dead port)")
    # Separate client against a port nothing listens on.
    dead = MCPClient(
        base_url="http://127.0.0.1:19999",
        failure_threshold=2,
        recovery_timeout=10.0,
        tools_cache_ttl_s=2.0,
    )
    # Seed the cache manually so list_tools has SOMETHING to serve
    # once the breaker opens.
    import time as _t
    dead._tools_cache = [{"name": "fake.tool", "required_scopes": []}]
    dead._tools_cache_fetched_at = _t.monotonic()
    dead._tools_fetch_count = 1

    # Trip the CB with real calls through call_tool
    for _ in range(3):
        try:
            await dead.call_tool(
                "fake.tool", {}, tenant_id="00000000-0000-0000-0000-000000000001",
            )
        except Exception:
            pass
    if dead.cb_state != "open":
        fail(f"CB should be open after 3 connect errors, got {dead.cb_state}")

    # Age the cache past TTL so list_tools is ELIGIBLE for refetch
    dead._tools_cache_fetched_at = _t.monotonic() - 60
    before_fetches = dead.tools_fetch_count
    served = await dead.list_tools()
    if not served or served[0]["name"] != "fake.tool":
        fail(f"expected stale cache served, got {served}")
    if dead.tools_fetch_count != before_fetches:
        fail(
            f"CB-open should NOT increment fetch_count: "
            f"{before_fetches} → {dead.tools_fetch_count}"
        )
    ok(f"stale cache served under CB-open (fetch_count unchanged at {before_fetches})")

    await dead.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 CATALOG-TTL STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
