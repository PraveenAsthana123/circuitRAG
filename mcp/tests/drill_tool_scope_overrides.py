"""
Drill: agent reads tool.required_scopes from the MCP catalog instead
of hard-coding the ``<namespace>:write`` convention.

Motivation: earlier commits wrote the agent's pre-check as
``required_role_for_tool(tool) == "<ns>:write"`` for every tool. The
MCP tool catalog declares hr.policy_lookup needs only ``hr:read``.
That mismatch meant an hr:read caller asking the agent to look up a
policy got denied at the agent, even though MCP would have allowed
it. This drill pins the fix.

Flow:
 1. hr:read + "look up leave policy" → intent=action, OK (catalog says
    policy_lookup needs hr:read, and caller has it).
 2. hr:read + "submit a 1-day leave request" → intent=action_denied_scope,
    required=[hr:write] (from catalog, not hardcoded).
 3. hr:write + "submit a 1-day leave request" → intent=action, ticket
    created (happy path still works).
 4. Kill MCP + hr:read + "submit a leave request" → fallback to the
    ``<ns>:write`` convention, intent=action_denied_scope.
    Proves: when catalog is unreachable the agent is conservative, not
    permissive.

Prereqs: inference-svc running DOCUMIND_AUTH_REQUIRED=true + MCP
running with MCP_AUTH_REQUIRED=true (or off; the test only cares that
MCP replies with the catalog on /tools/list).

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_tool_scope_overrides.py
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
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
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
            "sub": "drill-overrides",
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


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    # drill_tool_scope_overrides tests BOTH catalog-driven and fallback
    # paths; the catalog-driven ones need MCP_AUTH_REQUIRED on too so
    # we don't accidentally get a 2xx when we expect scope enforcement
    # end-to-end. But the fallback path (step 4) only needs /tools/list
    # to fail — which happens when MCP is dead.
    env["MCP_AUTH_REQUIRED"] = "true"
    env["MCP_JWT_PUBLIC_KEY_PATH"] = str(REPO / "scripts" / "dev-keys" / "jwt-public.pem")
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4317"
    log = open("/tmp/documind-mcp-hr-overrides-drill.log", "w")
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


async def main() -> None:
    read_tok = _mint(["hr:read"])
    write_tok = _mint(["hr:read", "hr:write"])

    async with httpx.AsyncClient(timeout=60.0) as c:
        step("0. sanity — inference auth=required, MCP reachable")
        readiness = (await c.get(f"{INFERENCE}/api/v1/health/detailed")).json().get("readiness") or {}
        if readiness.get("auth") != "required":
            fail(f"inference auth={readiness.get('auth')} — need 'required'")
        if not await _healthy(c, MCP_BASE, tries=2):
            fail("MCP not reachable; start it first")
        ok("ok")

        step("1. hr:read + policy_lookup — catalog says hr:read OK → intent=action")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {read_tok}",
            },
            json={"query": "please look up the leave policy"},
            timeout=60.0,
        )
        body = r.json()
        if body.get("intent") != "action":
            fail(
                f"expected intent=action (catalog allows hr:read), "
                f"got {body.get('intent')}  action={body.get('action')}"
            )
        action = body.get("action") or {}
        if not action.get("ok"):
            fail(f"action not ok on policy_lookup: {action}")
        result = action.get("result") or {}
        if result.get("policy_name") != "leave" or "paid leave" not in result.get("text", ""):
            fail(f"policy_lookup returned unexpected result: {result}")
        ok(f"intent=action policy_name={result['policy_name']} text[:40]={result['text'][:40]!r}...")

        step("2. hr:read + leave_request — catalog says hr:write → denied")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {read_tok}",
            },
            json={
                "query": "please submit a 1-day leave request for overrides drill",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        body = r.json()
        if body.get("intent") != "action_denied_scope":
            fail(f"expected action_denied_scope, got {body.get('intent')}")
        err = (body.get("action") or {}).get("error") or {}
        if err.get("required") != ["hr:write"]:
            fail(f"expected required=[hr:write], got {err.get('required')}")
        if err.get("have") != ["hr:read"]:
            fail(f"expected have=[hr:read], got {err.get('have')}")
        ok(f"denied required=['hr:write'] have=['hr:read']")

        step("3. hr:write + leave_request — happy path still works")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {write_tok}",
            },
            json={
                "query": "please submit a 1-day leave request for overrides happy",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        body = r.json()
        if body.get("intent") != "action":
            fail(f"expected intent=action, got {body.get('intent')}")
        ticket = ((body.get("action") or {}).get("result") or {}).get("ticket_id")
        if not ticket:
            fail(f"no ticket_id: {body.get('action')}")
        ok(f"intent=action ticket={ticket}")

        step("4. kill MCP + hr:read + leave_request — fallback convention → denied")
        _kill_mcp()
        await asyncio.sleep(2)
        try:
            await c.get(f"{MCP_BASE}/health", timeout=1.0)
        except httpx.HTTPError:
            pass
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {read_tok}",
            },
            json={
                "query": "please submit a 2-day leave request for overrides fallback",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        body = r.json()
        # When MCP is down the agent can't fetch the catalog. Falls back
        # to <ns>:write convention → hr:write required → hr:read denied.
        if body.get("intent") != "action_denied_scope":
            fail(
                f"expected fallback to still deny, got {body.get('intent')}  "
                f"action={body.get('action')}"
            )
        err = (body.get("action") or {}).get("error") or {}
        if err.get("required") != ["hr:write"]:
            fail(f"fallback didn't use convention: {err}")
        ok(f"fallback denial required={err['required']} (convention ':write')")

        step("5. restart MCP for subsequent drills")
        _spawn_mcp()
        if not await _healthy(c, MCP_BASE, tries=20):
            fail("MCP did not come back after restart")
        ok("MCP up")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 TOOL-SCOPE-OVERRIDE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
