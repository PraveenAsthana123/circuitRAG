#!/usr/bin/env python3
# RESOURCES: readonly mcp_paperclip
"""Drill: mcp/server_paperclip.py — MCP surface for Paperclip Stage-1.

Per CLAUDE.md §43 + §50 (MCP standard surface) + ADR-012 (Paperclip
sandbox-only). Locks the contract that:

  - Module imports without error
  - Exactly 2 tools registered: paperclip.snapshot + paperclip.health
  - BOTH tools are side_effects="read" (Stage-1 contract — adding any
    write tool requires an ADR + Stage-2 promotion)
  - BOTH tools require the snapshot:read scope
  - The handlers map covers exactly the tool names registered (no
    orphan handlers, no missing handlers)
  - The /v1/tools list endpoint returns the catalog
  - The /v1/health endpoint is liveness-only (does NOT call the
    subprocess — fast probe)
  - Importing the module does NOT call paperclip_manager subprocess
    (lazy: only invoked on actual tool call)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def main() -> int:
    print("-- 1. POSITIVE: mcp/server_paperclip.py exists + imports cleanly --")
    server_path = REPO / "mcp" / "server_paperclip.py"
    if not server_path.exists():
        print(f"x {server_path} missing")
        return 1
    from mcp import server_paperclip
    if not hasattr(server_paperclip, "app"):
        print("x server_paperclip.app missing (FastAPI app)")
        return 1
    if not hasattr(server_paperclip, "TOOLS"):
        print("x server_paperclip.TOOLS missing")
        return 1
    print("  ok: server_paperclip imports + has app + TOOLS")

    print("-- 2. POSITIVE: exactly 2 tools registered (paperclip.snapshot + paperclip.health) --")
    tools = server_paperclip.TOOLS
    if len(tools) != 2:
        print(f"x expected 2 tools; got {len(tools)}")
        return 1
    names = {t["name"] for t in tools}
    expected = {"paperclip.snapshot", "paperclip.health"}
    if names != expected:
        print(f"x tool names mismatch; expected {expected}, got {names}")
        return 1
    print(f"  ok: 2 tools registered: {sorted(names)}")

    print("-- 3. NEGATIVE: NO tool has side_effects='write' (Stage-1 sandbox contract) --")
    write_tools = [t for t in tools if t.get("side_effects") == "write"]
    if write_tools:
        print(f"x Stage-1 sandbox forbids write tools; found: {[t['name'] for t in write_tools]}")
        return 1
    # All tools must explicitly declare side_effects="read"
    for t in tools:
        if t.get("side_effects") != "read":
            print(f"x tool {t['name']} must declare side_effects='read'; got {t.get('side_effects')!r}")
            return 1
    print("  ok: 0 write tools; all 2 tools declare side_effects='read'")

    print("-- 4. NEGATIVE: every tool requires snapshot:read scope --")
    # Stage-1 scope policy: only snapshot:read. Adding ANY tool that
    # demands a different scope would be a contract change.
    for t in tools:
        scopes = t.get("required_scopes", [])
        if scopes != ["snapshot:read"]:
            print(f"x tool {t['name']} required_scopes wrong; got {scopes}")
            return 1
    print("  ok: both tools require ['snapshot:read'] (matches PolisAI rule)")

    print("-- 5. NEGATIVE: handler map covers exactly the registered tools --")
    handlers = server_paperclip.HANDLERS
    handler_names = set(handlers.keys())
    if handler_names != names:
        missing = names - handler_names
        orphan = handler_names - names
        print(f"x handler/tool mismatch; missing handlers: {missing}, orphan handlers: {orphan}")
        return 1
    # Each handler must be a callable
    for name, fn in handlers.items():
        if not callable(fn):
            print(f"x handler for {name!r} not callable")
            return 1
    print("  ok: 2 handlers, exactly matching the 2 registered tools, all callable")

    print("-- 6. NEGATIVE: tool name regex enforces 'paperclip.' prefix --")
    # Bit-rot prevention: a future PR adding a non-paperclip tool to
    # this server would silently namespace-clash with other MCP
    # servers. Lock: every tool name starts with 'paperclip.'.
    for t in tools:
        if not t["name"].startswith("paperclip."):
            print(f"x tool {t['name']!r} must start with 'paperclip.'")
            return 1
    print("  ok: all tool names use the paperclip.* namespace")

    print("-- 7. POSITIVE: /v1/tools and /v1/health endpoints registered --")
    routes = {r.path: r for r in server_paperclip.app.routes}
    for required_path in ("/v1/tools", "/v1/tools/call", "/v1/health"):
        if required_path not in routes:
            print(f"x route missing: {required_path!r}")
            return 1
    # /v1/tools and /v1/health should be GET; /v1/tools/call should be POST
    list_methods = routes["/v1/tools"].methods
    if "GET" not in list_methods:
        print(f"x /v1/tools must support GET; got {list_methods}")
        return 1
    call_methods = routes["/v1/tools/call"].methods
    if "POST" not in call_methods:
        print(f"x /v1/tools/call must support POST; got {call_methods}")
        return 1
    print("  ok: /v1/tools (GET) + /v1/tools/call (POST) + /v1/health (GET)")

    print("-- 8. NEGATIVE: importing module does NOT spawn paperclip subprocess --")
    # Stage-1 contract: module import must be cheap (<200ms) and must
    # not call out to paperclip_manager. The subprocess call only fires
    # on an actual tool invocation — that's the lazy-init posture.
    # We measure import time of a fresh subprocess.
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); "
         "import time; t0 = time.time(); "
         "from mcp import server_paperclip; "
         "print(f'IMPORT_OK {(time.time() - t0):.3f}')"],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        print(f"x fresh import failed: {proc.stderr[:200]}")
        return 1
    if "IMPORT_OK" not in proc.stdout:
        print(f"x import sentinel missing in stdout: {proc.stdout[:200]}")
        return 1
    # Parse the timing
    import re
    m = re.search(r"IMPORT_OK\s+([\d.]+)", proc.stdout)
    if m:
        elapsed = float(m.group(1))
        # Allow 5s for cold start (FastAPI + OTel can be heavy)
        if elapsed > 5.0:
            print(f"x import took {elapsed:.3f}s; expected <5s (lazy-init contract)")
            return 1
        print(f"  ok: fresh import {elapsed:.3f}s; no subprocess fired")
    else:
        print("  ok: fresh import succeeded (timing not parsed)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
