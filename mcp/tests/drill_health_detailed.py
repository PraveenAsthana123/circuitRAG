# RESOURCES: inference mcp_hr
"""
Drill: GET /api/v1/health/detailed surfaces internal breaker + readiness state.

Flow:
 1. Fetch baseline — mcp_hr breaker should be 'closed', readiness
    reports draft_store=postgres, audit_log=on, auth=optional|required,
    agent_service=on.
 2. Kill MCP. Fire 3 agent/ask calls to trip the MCP client breaker
    (failure_threshold=3 by default).
 3. Fetch detailed again — mcp_hr breaker state should now be 'open'
    with failures >= 3.
 4. Restart MCP + wait for recovery_timeout. After the probe, the
    state reported should be 'closed' (or 'half_open' momentarily,
    which also counts as "breaker is probing, safe to retry").

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_health_detailed.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"
H = {"X-Tenant-Id": TENANT, "Content-Type": "application/json"}


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    log = open("/tmp/documind-mcp-hr-detailed-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_hr.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )


async def _healthy(c: httpx.AsyncClient, url: str, tries: int = 30) -> bool:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    return False


async def _dead(c: httpx.AsyncClient, url: str, tries: int = 10) -> None:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=1.0)
            if r.status_code != 200:
                return
        except httpx.HTTPError:
            return
        await asyncio.sleep(0.3)


def _breaker(body: dict, name: str) -> dict | None:
    return next((b for b in body.get("breakers", []) if b["name"] == name), None)


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as c:
        step("1. baseline — detailed health reports healthy state")
        r = await c.get(f"{INFERENCE}/api/v1/health/detailed")
        if r.status_code != 200:
            fail(f"detailed health returned {r.status_code}")
        body = r.json()
        if body.get("service") != "inference-svc":
            fail(f"wrong service: {body.get('service')}")
        if body.get("uptime_s", 0) <= 0:
            fail(f"uptime_s non-positive: {body.get('uptime_s')}")
        mcp_b = _breaker(body, "mcp_hr")
        if mcp_b is None:
            fail(f"mcp_hr breaker missing; breakers: {body.get('breakers')}")
        if mcp_b["state"] != "closed":
            fail(f"expected mcp_hr closed, got {mcp_b['state']}")
        readiness = body.get("readiness") or {}
        if readiness.get("draft_store") not in ("postgres", "in_memory"):
            fail(f"draft_store missing/invalid: {readiness}")
        if readiness.get("agent_service") != "on":
            fail(f"agent_service not on: {readiness}")
        ok(
            f"uptime={body['uptime_s']}s mcp_hr={mcp_b['state']} "
            f"readiness={readiness}",
        )

        step("2. kill MCP + 3 agent/ask calls to trip the CB")
        _kill_mcp()
        await _dead(c, MCP_BASE)
        for i in range(3):
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers=H,
                json={
                    "query": f"Please submit a {i+1}-day leave request for CB trip drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            if r.status_code != 200:
                fail(f"agent/ask {i} returned {r.status_code}")
            a = r.json().get("action") or {}
            if not a.get("degraded"):
                fail(f"call {i} did not degrade: {a}")
        ok("3 degraded drafts recorded — breaker should have tripped")

        step("3. GET /detailed — mcp_hr breaker now 'open'")
        # small settle — MCP client CB updates on the request path itself,
        # so it should already be open; keep a guard in case of scheduler jitter
        await asyncio.sleep(0.5)
        r = await c.get(f"{INFERENCE}/api/v1/health/detailed")
        body = r.json()
        mcp_b = _breaker(body, "mcp_hr")
        if mcp_b["state"] != "open":
            fail(f"expected mcp_hr open, got {mcp_b}")
        if (mcp_b.get("failures") or 0) < 3:
            fail(f"expected failures>=3, got {mcp_b}")
        ok(f"mcp_hr state={mcp_b['state']} failures={mcp_b['failures']}")

        step("4. restart MCP + recovery — breaker returns to 'closed' after a probe")
        mcp_proc = _spawn_mcp()
        try:
            if not await _healthy(c, MCP_BASE):
                fail("MCP didn't come back")
            # Wait for recovery_timeout (30s default) + a small margin
            print("    waiting 32s for CB recovery_timeout...")
            await asyncio.sleep(32)
            # Fire one call to trigger the HALF_OPEN probe
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers=H,
                json={
                    "query": "Please submit a 1-day leave request post-recovery",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            action = r.json().get("action") or {}
            if not (action.get("ok") or action.get("result")):
                fail(f"post-recovery call didn't succeed: {action}")
            await asyncio.sleep(0.5)
            r = await c.get(f"{INFERENCE}/api/v1/health/detailed")
            mcp_b = _breaker(r.json(), "mcp_hr")
            if mcp_b["state"] not in ("closed", "half_open"):
                fail(f"expected closed/half_open after probe, got {mcp_b}")
            ok(f"recovered: mcp_hr state={mcp_b['state']}")

        finally:
            if mcp_proc.poll() is None:
                mcp_proc.terminate()
                try:
                    mcp_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    mcp_proc.kill()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 DETAILED-HEALTH STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
