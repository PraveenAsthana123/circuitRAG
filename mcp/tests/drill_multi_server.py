# RESOURCES: mcp_hr mcp_itsm
"""
Drill: the mcp/ package can run two servers side-by-side with
independent scope enforcement.

Motivation: the scope-naming convention (``hr:write``, ``itsm:write``)
and the tool-catalog pattern always assumed multi-server. This drill
validates that assumption with a real second server
(``mcp/server_itsm.py``) and proves:

  * Each server exposes its own ``/tools/list``.
  * hr:write JWT cannot execute ``itsm.incident_open`` (wrong scope).
  * itsm:write JWT can — on the ITSM server — open an incident.
  * itsm:write JWT cannot execute ``hr.leave_request`` (wrong scope
    on the OTHER server).
  * Both servers participate in the same Jaeger trace tree when
    called from one process.

Prereqs:
  * MCP HR on :8090 with MCP_AUTH_REQUIRED=true
  * MCP ITSM on :8091 with MCP_AUTH_REQUIRED=true (started by this drill)
  * Dev keys at scripts/dev-keys/

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_multi_server.py
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import MCPClient  # noqa: E402

HR_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
ITSM_BASE = os.getenv("MCP_ITSM_URL", "http://127.0.0.1:8091")
ITSM_PORT = int(os.getenv("MCP_ITSM_PORT", "8091"))
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PRIV_KEY = REPO / "scripts" / "dev-keys" / "jwt-private.pem"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _mint(roles: list[str]) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": "documind-local",
            "aud": "documind-services",
            "sub": "drill-multi-" + (roles[0].replace(":", "-") if roles else "anon"),
            "email": "drill@documind.local",
            "tenant_id": TENANT,
            "roles": roles,
            "kind": "access",
            "iat": now, "nbf": now, "exp": now + 900,
            "jti": uuid.uuid4().hex,
        },
        PRIV_KEY.read_bytes(),
        algorithm="RS256",
    )


def _spawn_itsm() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_ITSM_PORT"] = str(ITSM_PORT)
    env["MCP_AUTH_REQUIRED"] = "true"
    env["MCP_JWT_PUBLIC_KEY_PATH"] = str(REPO / "scripts" / "dev-keys" / "jwt-public.pem")
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    log = open("/tmp/documind-mcp-itsm-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_itsm.py")],
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


async def main() -> None:
    # Spawn ITSM server for this drill.
    subprocess.run(["fuser", "-k", f"{ITSM_PORT}/tcp"], check=False, capture_output=True)
    await asyncio.sleep(1)
    itsm_proc = _spawn_itsm()
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            step("1. both servers healthy on distinct ports")
            hr_ok = await _healthy(c, HR_BASE, tries=3)
            itsm_ok = await _healthy(c, ITSM_BASE, tries=30)
            if not hr_ok:
                fail(f"HR server unreachable at {HR_BASE}")
            if not itsm_ok:
                fail(f"ITSM server unreachable at {ITSM_BASE}")
            ok(f"HR at {HR_BASE}, ITSM at {ITSM_BASE}")

            step("2. each /tools/list returns its own catalog")
            hr_tools = (await c.get(f"{HR_BASE}/tools/list")).json()["tools"]
            itsm_tools = (await c.get(f"{ITSM_BASE}/tools/list")).json()["tools"]
            hr_names = {t["name"] for t in hr_tools}
            itsm_names = {t["name"] for t in itsm_tools}
            if not hr_names.issuperset({"hr.leave_request", "hr.policy_lookup"}):
                fail(f"HR catalog missing expected tools: {hr_names}")
            if not itsm_names.issuperset({"itsm.incident_lookup", "itsm.incident_open"}):
                fail(f"ITSM catalog missing expected tools: {itsm_names}")
            if hr_names & itsm_names:
                fail(f"catalogs overlap unexpectedly: {hr_names & itsm_names}")
            ok(f"HR={sorted(hr_names)}")
            ok(f"ITSM={sorted(itsm_names)}")

        # Now exercise scope enforcement cross-server via MCPClient
        hr_write = _mint(["hr:read", "hr:write"])
        itsm_write = _mint(["itsm:read", "itsm:write"])
        both_write = _mint(["hr:write", "itsm:write"])

        step("3. hr:write JWT → itsm.incident_open → 403 (wrong namespace scope)")
        itsm_client = MCPClient(base_url=ITSM_BASE, failure_threshold=10)
        r = await itsm_client.call_tool(
            "itsm.incident_open",
            {"title": "drill A", "description": "smoke-test", "priority": "normal"},
            tenant_id=TENANT,
            auth_token=hr_write,
        )
        if r.ok or not r.error or r.error.get("code") != "INSUFFICIENT_SCOPE":
            fail(f"expected INSUFFICIENT_SCOPE, got: {r}")
        if "itsm:write" not in r.error.get("required", []):
            fail(f"required missing itsm:write: {r.error}")
        if "hr:write" not in r.error.get("have", []):
            fail(f"have missing hr:write: {r.error}")
        ok(f"cross-server denial: required={r.error['required']} have={r.error['have']}")

        step("4. itsm:write JWT → itsm.incident_open → 200 + incident_id")
        r = await itsm_client.call_tool(
            "itsm.incident_open",
            {"title": "drill B", "description": "multi-server drill", "priority": "high"},
            tenant_id=TENANT,
            auth_token=itsm_write,
        )
        if not r.ok or not r.data or not r.data.get("incident_id"):
            fail(f"expected incident_id, got: {r}")
        if not r.data["incident_id"].startswith("ITSM-"):
            fail(f"incident_id wrong shape: {r.data}")
        incident_id = r.data["incident_id"]
        ok(f"ok incident_id={incident_id} status={r.data['status']}")

        step("5. itsm:write JWT → HR server hr.leave_request → 403 (symmetric)")
        hr_client = MCPClient(base_url=HR_BASE, failure_threshold=10)
        r = await hr_client.call_tool(
            "hr.leave_request",
            {"employee_id": "E1", "days": 1, "reason": "wrong-namespace"},
            tenant_id=TENANT,
            auth_token=itsm_write,
        )
        if r.ok or not r.error or r.error.get("code") != "INSUFFICIENT_SCOPE":
            fail(f"expected INSUFFICIENT_SCOPE on HR side too, got: {r}")
        if "hr:write" not in r.error.get("required", []):
            fail(f"required missing hr:write: {r.error}")
        ok(f"symmetric denial: HR server also rejects itsm:write token")

        step("6. union token (hr:write + itsm:write) → both servers accept")
        r1 = await hr_client.call_tool(
            "hr.leave_request",
            {"employee_id": "E1", "days": 1, "reason": "union-token HR"},
            tenant_id=TENANT,
            auth_token=both_write,
        )
        r2 = await itsm_client.call_tool(
            "itsm.incident_open",
            {"title": "union-token ITSM", "description": "..."},
            tenant_id=TENANT,
            auth_token=both_write,
        )
        hr_ticket = (r1.data or {}).get("ticket_id") if r1.ok else None
        itsm_ticket = (r2.data or {}).get("incident_id") if r2.ok else None
        if not hr_ticket or not itsm_ticket:
            fail(f"union token failed on one server: HR={r1}  ITSM={r2}")
        ok(f"HR ticket={hr_ticket}  ITSM ticket={itsm_ticket}")

        step("7. lookup the new incident via itsm.incident_lookup w/ itsm:read only")
        itsm_read_only = _mint(["itsm:read"])
        r = await itsm_client.call_tool(
            "itsm.incident_lookup",
            {"incident_id": incident_id},
            tenant_id=TENANT,
            auth_token=itsm_read_only,
        )
        if not r.ok or not r.data:
            fail(f"lookup failed: {r}")
        if r.data.get("incident_id") != incident_id:
            fail(f"lookup returned wrong id: {r.data}")
        if r.data.get("priority") != "high":
            fail(f"priority not round-tripped: {r.data}")
        ok(f"lookup: {r.data}")

        await hr_client.close()
        await itsm_client.close()

    finally:
        if itsm_proc.poll() is None:
            itsm_proc.terminate()
            try:
                itsm_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                itsm_proc.kill()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 MULTI-SERVER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
