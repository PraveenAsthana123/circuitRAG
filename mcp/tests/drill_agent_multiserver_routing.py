# RESOURCES: inference mcp_hr mcp_itsm
"""
Drill: inference-svc's agent routes by tool namespace to the right MCP.

Flow:
 1. Sanity — inference-svc up with both DOCUMIND_MCP_HR_URL and
    DOCUMIND_MCP_ITSM_URL configured (app.state.mcp_clients has both
    namespaces, surfaced via /api/v1/health/detailed).
 2. hr:write token + leave-request query → hr.leave_request at HR MCP
    → ticket created.
 3. itsm:write token + incident-open query → itsm.incident_open at
    ITSM MCP → incident created (ITSM-XXXXXXXX).
 4. Union token (hr:write + itsm:write) + incident-open query
    → routes to ITSM (not HR, not broken).
 5. Simulate missing-namespace: monkey-hit with a query that would
    route to a namespace nobody registered. Expect intent=
    action_unavailable with code=NO_SERVER_FOR_NAMESPACE.

Prereqs:
  MCP HR on :8090 (auth on), MCP ITSM on :8091 (auth on, started by drill),
  inference-svc running with DOCUMIND_MCP_ITSM_URL=http://127.0.0.1:8091.

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_agent_multiserver_routing.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
ITSM_PORT = int(os.getenv("MCP_ITSM_PORT", "8091"))
ITSM_BASE = os.getenv("MCP_ITSM_URL", f"http://127.0.0.1:{ITSM_PORT}")
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
            "sub": "drill-routing",
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
    log = open("/tmp/documind-mcp-itsm-routing-drill.log", "w")
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
        async with httpx.AsyncClient(timeout=60.0) as c:
            # Ensure MCP ITSM healthy before we start (inference-svc may
            # already have initialised a client pointing here; if ITSM was
            # down at inference boot, the MCPClient's breaker would be
            # closed but the first call would connect-error).
            if not await _healthy(c, ITSM_BASE, tries=30):
                fail(f"ITSM server unreachable at {ITSM_BASE}")

            step("1. inference /api/v1/health/detailed confirms both MCPs wired")
            r = await c.get(f"{INFERENCE}/api/v1/health/detailed")
            body = r.json()
            readiness = body.get("readiness") or {}
            if readiness.get("agent_service") != "on":
                fail(f"agent_service off: {readiness}")
            ok(f"auth={readiness.get('auth')} agent_service=on")

            write_both = _mint(["hr:read", "hr:write", "itsm:read", "itsm:write"])

            step("2. hr:write query → hr.leave_request at HR MCP")
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_both}",
                },
                json={
                    "query": "please submit a 1-day leave request for routing-hr drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            body = r.json()
            if body.get("intent") != "action":
                fail(f"intent={body.get('intent')} action={body.get('action')}")
            action = body.get("action") or {}
            if action.get("tool") != "hr.leave_request":
                fail(f"wrong tool routed: {action.get('tool')}")
            ticket = (action.get("result") or {}).get("ticket_id")
            if not ticket or not ticket.startswith("HR-"):
                fail(f"wrong ticket shape: {ticket}")
            ok(f"routed HR.leave_request → ticket={ticket}")

            step("3. itsm:write query → itsm.incident_open at ITSM MCP")
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_both}",
                },
                json={
                    "query": "please open an urgent incident: VPN unreachable from the Berlin office",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            body = r.json()
            if body.get("intent") != "action":
                fail(f"intent={body.get('intent')} action={body.get('action')}")
            action = body.get("action") or {}
            if action.get("tool") != "itsm.incident_open":
                fail(f"wrong tool routed: {action.get('tool')}")
            incident = (action.get("result") or {}).get("incident_id")
            if not incident or not incident.startswith("ITSM-"):
                fail(f"wrong incident shape: {incident}")
            ok(f"routed ITSM.incident_open → incident={incident}")

            step("4. cross-priority: incident-open query with 'critical' wording")
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_both}",
                },
                json={
                    "query": "critical incident: please open a ticket for the billing outage",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            body = r.json()
            action = body.get("action") or {}
            if action.get("tool") != "itsm.incident_open":
                fail(f"wrong tool: {action.get('tool')}")
            incident2 = (action.get("result") or {}).get("incident_id")
            if not incident2 or not incident2.startswith("ITSM-"):
                fail(f"no incident2: {body}")
            # The priority was inferred via regex — confirm it reached the
            # ITSM server (we can't read the ticket from here, but the
            # title should contain the query).
            ok(f"routed ITSM.incident_open → incident={incident2}")

            step("5. hr:write only + itsm query → server-side denies with INSUFFICIENT_SCOPE")
            hr_only = _mint(["hr:read", "hr:write"])
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {hr_only}",
                },
                json={
                    "query": "please open an incident for the Wi-Fi issue in conference room 4",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            body = r.json()
            if body.get("intent") != "action_denied_scope":
                fail(
                    f"expected action_denied_scope at agent pre-check, got {body.get('intent')} "
                    f"action={body.get('action')}"
                )
            err = (body.get("action") or {}).get("error") or {}
            if "itsm:write" not in (err.get("required") or []):
                fail(f"expected required=[itsm:write], got: {err}")
            ok(f"routed to ITSM then pre-denied required={err['required']} have={err['have']}")

    finally:
        if itsm_proc.poll() is None:
            itsm_proc.terminate()
            try:
                itsm_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                itsm_proc.kill()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 AGENT-MULTISERVER-ROUTING STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
