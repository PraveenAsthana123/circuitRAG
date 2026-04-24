# RESOURCES: mcp_drills
"""
Drill: the mcp-server-drills server exposes drill.list + drill.run
as real MCP tools.

Meta: this drill is a drill for running drills. It proves the MCP
wrapper works independently of the CLI runner.

Flow:
 1. Server healthy on :8092
 2. /tools/list returns {drill.list, drill.run}
 3. /tools/call drill.list — returns >= 20 entries, each has a
    'name' and 'resources' field.
 4. /tools/call drill.run on a fast known-green drill
    (drill_tool_catalog_ttl) → ok=True, steps_passed=5, exit_code=0
 5. Idempotency-Key replay of step 4 returns identical result +
    idempotent_replay=true (drill NOT re-run).
 6. /tools/call drill.run on an unknown drill → ok=False,
    error code, no execution attempted.

Prereqs: mcp-server-drills running on :8092, OTel collector present
(optional). No auth required by default (MCP_AUTH_REQUIRED=false).

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_drill_server.py
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
BASE = os.getenv("MCP_DRILLS_URL", "http://127.0.0.1:8092")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=120.0) as c:
        step("1. /health on :8092")
        r = await c.get(f"{BASE}/health")
        if r.status_code != 200:
            fail(f"health returned {r.status_code}")
        body = r.json()
        if body.get("service") != "mcp-server-drills":
            fail(f"wrong service: {body}")
        ok(f"service={body['service']}")

        step("2. /tools/list returns drill.list + drill.run")
        r = await c.get(f"{BASE}/tools/list")
        tools = r.json().get("tools", [])
        names = {t["name"] for t in tools}
        if not {"drill.list", "drill.run"}.issubset(names):
            fail(f"expected drill.list + drill.run, got {names}")
        # Verify scope declarations
        drun = next(t for t in tools if t["name"] == "drill.run")
        if "drill:run" not in (drun.get("required_scopes") or []):
            fail(f"drill.run missing drill:run scope: {drun}")
        ok(f"tools: {sorted(names)}")

        step("3. /tools/call drill.list — has >= 20 drills, each with resources")
        r = await c.post(
            f"{BASE}/tools/call",
            json={"name": "drill.list", "arguments": {}},
        )
        body = r.json()
        if not body.get("ok"):
            fail(f"drill.list failed: {body}")
        drills = body["result"]["drills"]
        if len(drills) < 20:
            fail(f"only {len(drills)} drills discovered — expected >=20")
        for d in drills[:5]:
            if "name" not in d or "resources" not in d:
                fail(f"malformed drill entry: {d}")
        # Confirm the tagged readonly drill appears with empty resources
        ttl_entry = next((d for d in drills if d["name"] == "drill_tool_catalog_ttl"), None)
        if ttl_entry is None:
            fail("drill_tool_catalog_ttl missing from list")
        if ttl_entry["resources"]:
            fail(f"drill_tool_catalog_ttl should be empty-resources, got {ttl_entry['resources']}")
        ok(f"{len(drills)} drills listed; readonly tag roundtrips correctly")

        step("4. /tools/call drill.run on a fast green drill")
        idem = str(uuid.uuid4())
        r = await c.post(
            f"{BASE}/tools/call",
            headers={"Idempotency-Key": idem},
            json={
                "name": "drill.run",
                "arguments": {
                    "name": "drill_tool_catalog_ttl",
                    "timeout_s": 30,
                },
            },
            timeout=60.0,
        )
        body = r.json()
        if not body.get("ok"):
            fail(f"drill.run failed: {body}")
        result = body["result"]
        if not result.get("ok"):
            fail(f"drill didn't pass: {result}")
        if result["steps_passed"] != 5:
            fail(f"wrong step count: {result}")
        if result["exit_code"] != 0:
            fail(f"non-zero exit: {result}")
        first_duration = result["duration_s"]
        ok(
            f"drill ran ok={result['ok']} steps={result['steps_passed']} "
            f"time={first_duration}s exit={result['exit_code']}"
        )

        step("5. Idempotent replay — same result, idempotent_replay=True, NOT re-run")
        r = await c.post(
            f"{BASE}/tools/call",
            headers={"Idempotency-Key": idem},
            json={
                "name": "drill.run",
                "arguments": {
                    "name": "drill_tool_catalog_ttl",
                    "timeout_s": 30,
                },
            },
        )
        body = r.json()
        if not body.get("idempotent_replay"):
            fail(f"expected idempotent_replay=True: {body}")
        if body["result"]["duration_s"] != first_duration:
            fail(
                f"replay duration differs from first run — drill was re-executed! "
                f"first={first_duration}s replay={body['result']['duration_s']}s"
            )
        ok(f"replay identical (duration_s={body['result']['duration_s']} unchanged)")

        step("6. /tools/call drill.run with unknown drill name → ok=False, no execution")
        r = await c.post(
            f"{BASE}/tools/call",
            json={
                "name": "drill.run",
                "arguments": {"name": "drill_does_not_exist", "timeout_s": 30},
            },
        )
        body = r.json()
        if not body.get("ok"):
            # Tool itself might return ok=False OR an error envelope;
            # either shape is fine as long as the inner result says
            # the drill wasn't run.
            fail(f"tool call itself shouldn't error on unknown drill name: {body}")
        result = body["result"]
        if result.get("ok"):
            fail(f"unknown drill should NOT pass: {result}")
        if result.get("exit_code") != -1:
            fail(f"expected exit_code=-1 for unknown drill, got {result}")
        ok(f"unknown drill correctly rejected: tail={result.get('tail', '')[:60]!r}")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 DRILL-SERVER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
