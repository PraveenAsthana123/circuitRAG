# RESOURCES: mcp_hr
"""
Drill: MCPClient maps server-side 4xx responses into a structured
ToolResult.error — and does NOT trip the circuit breaker on them.

Companion to drill_mcp_server_scope.py. That drill proves the MCP
*server* returns correct HTTP codes + payloads; this one proves the
*client* surfaces them intact to its caller.

Prerequisite: MCP running with MCP_AUTH_REQUIRED=true (same setup as
drill_mcp_server_scope.py).

Flow:
 1. No token → ToolResult(ok=False, error={code=NOT_AUTHENTICATED,
    http_status=401, ...}).
 2. Bogus token → error.code=INVALID_TOKEN, http_status=401.
 3. hr:read on write tool → error.code=INSUFFICIENT_SCOPE,
    error.required=['hr:write'], error.have=['hr:read'], http_status=403.
 4. Unknown tool name w/ valid auth → error.code=tool_not_found,
    http_status=404.
 5. Valid hr:write token → ok=True, data.ticket_id populated.
 6. CB stays CLOSED through all of the above — 4xx is not a CB trip.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_client_error_envelope.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import MCPClient  # noqa: E402

MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
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
            "sub": "drill-envelope",
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


async def main() -> None:
    # High threshold so 4xx responses can't accidentally contribute
    # to the CB on some future refactor that mis-categorises them.
    client = MCPClient(
        base_url=MCP_BASE,
        failure_threshold=20,
        recovery_timeout=5.0,
    )

    step("1. no Authorization → error.code=NOT_AUTHENTICATED http_status=401")
    r = await client.call_tool(
        "hr.leave_request",
        {"employee_id": "E1", "days": 1, "reason": "x"},
        tenant_id=TENANT,
    )
    if r.ok:
        fail(f"expected ok=False: {r}")
    if not r.error:
        fail(f"expected structured error, got None: {r}")
    if r.error.get("code") != "NOT_AUTHENTICATED":
        fail(f"wrong code: {r.error}")
    if r.error.get("http_status") != 401:
        fail(f"wrong http_status: {r.error}")
    ok(f"error={r.error}")

    step("2. bogus token → error.code=INVALID_TOKEN http_status=401")
    r = await client.call_tool(
        "hr.leave_request",
        {"employee_id": "E1", "days": 1, "reason": "x"},
        tenant_id=TENANT,
        auth_token="not.a.real.jwt",
    )
    if r.ok or not r.error or r.error.get("code") != "INVALID_TOKEN":
        fail(f"expected INVALID_TOKEN, got: {r}")
    if r.error.get("http_status") != 401:
        fail(f"wrong http_status: {r.error}")
    ok(f"error={r.error}")

    read_tok = _mint(["hr:read"])
    write_tok = _mint(["hr:read", "hr:write"])

    step("3. hr:read on write tool → INSUFFICIENT_SCOPE w/ required+have+http_status")
    r = await client.call_tool(
        "hr.leave_request",
        {"employee_id": "E1", "days": 1, "reason": "x"},
        tenant_id=TENANT,
        auth_token=read_tok,
    )
    if r.ok or not r.error or r.error.get("code") != "INSUFFICIENT_SCOPE":
        fail(f"expected INSUFFICIENT_SCOPE, got: {r}")
    required = r.error.get("required") or []
    have = r.error.get("have") or []
    if "hr:write" not in required or "hr:read" not in have:
        fail(f"missing required/have lists: {r.error}")
    if r.error.get("http_status") != 403:
        fail(f"wrong http_status: {r.error}")
    ok(f"error={r.error}")

    step("4. unknown tool → error.code=tool_not_found http_status=404")
    r = await client.call_tool(
        "hr.does_not_exist",
        {"anything": 1},
        tenant_id=TENANT,
        auth_token=write_tok,
    )
    if r.ok or not r.error or r.error.get("code") != "tool_not_found":
        fail(f"expected tool_not_found, got: {r}")
    if r.error.get("http_status") != 404:
        fail(f"wrong http_status: {r.error}")
    ok(f"error={r.error}")

    step("5. hr:write → ok=True, ticket_id populated")
    r = await client.call_tool(
        "hr.leave_request",
        {"employee_id": "E1", "days": 1, "reason": "envelope-happy-path"},
        tenant_id=TENANT,
        auth_token=write_tok,
    )
    if not r.ok:
        fail(f"expected ok=True, got: {r}")
    if not (r.data or {}).get("ticket_id"):
        fail(f"no ticket_id: {r}")
    ok(f"ok=True ticket_id={r.data['ticket_id']}")

    step("6. CB still CLOSED — 4xx did NOT trip it")
    if client.cb_state != "closed":
        fail(f"CB should be closed, got {client.cb_state}")
    ok(f"cb_state={client.cb_state}")

    await client.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 ENVELOPE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
