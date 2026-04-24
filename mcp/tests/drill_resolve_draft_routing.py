"""
Drill: resolve_draft routes to the right MCP server by draft.tool namespace.

Bug it closes: admin API's POST /api/v1/drafts/{id}/resolve used to
always target the hr client (app.state.mcp_client). An itsm.* draft
would be replayed against the HR server, which has no such tool —
the replay failed with a spurious 404.

Flow:
 1. Clean slate: delete existing drafts for this tenant.
 2. Kill ITSM. Fire hr:write + incident-open agent/ask → ITSM draft
    persists (pending). Verify the draft's tool is itsm.incident_open.
 3. Kill HR too. Fire itsm:write + leave-request query → HR draft
    persists (pending). Verify tool is hr.leave_request.
 4. Restart both servers + wait for CB recovery.
 5. POST /api/v1/drafts/{itsm_draft_id}/resolve → routes to ITSM,
    incident_id returned, draft marked replayed.
 6. POST /api/v1/drafts/{hr_draft_id}/resolve → routes to HR,
    ticket_id returned, draft marked replayed.
 7. Sanity: GET /api/v1/drafts → no pending drafts remain for tenant.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_resolve_draft_routing.py
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
HR_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
ITSM_BASE = os.getenv("MCP_ITSM_URL", "http://127.0.0.1:8091")
HR_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
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
            "sub": "drill-resolve-routing",
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


def _kill(port: int) -> None:
    subprocess.run(["fuser", "-k", f"{port}/tcp"], check=False, capture_output=True)


def _spawn_hr() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(HR_PORT)
    env["MCP_AUTH_REQUIRED"] = "true"
    env["MCP_JWT_PUBLIC_KEY_PATH"] = str(REPO / "scripts" / "dev-keys" / "jwt-public.pem")
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    log = open("/tmp/documind-mcp-hr-resolve-routing-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_hr.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
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
    log = open("/tmp/documind-mcp-itsm-resolve-routing-drill.log", "w")
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


async def _dead(c: httpx.AsyncClient, url: str, tries: int = 10) -> None:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=1.0)
            if r.status_code != 200:
                return
        except httpx.HTTPError:
            return
        await asyncio.sleep(0.3)


async def main() -> None:
    step("0. clean slate — drop drafts for this tenant")
    subprocess.run(
        [
            "docker", "exec", "-e", "PGPASSWORD=documind",
            "documind-postgres", "psql", "-U", "documind", "-d", "documind",
            "-c", f"DELETE FROM governance.action_drafts WHERE tenant_id='{TENANT}'",
        ],
        check=True, capture_output=True,
    )
    ok("drafts cleared")

    write_both = _mint(["hr:write", "itsm:write"])
    hr_proc = None
    itsm_proc = None

    async with httpx.AsyncClient(timeout=60.0) as c:
        # === Phase A: create an ITSM draft ===
        step("1. kill ITSM, fire incident-open → ITSM draft pending")
        _kill(ITSM_PORT)
        await _dead(c, ITSM_BASE)
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {write_both}",
            },
            json={
                "query": "please open an incident for the routing-resolve drill",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        action = r.json().get("action") or {}
        if not action.get("degraded") or not action.get("draft_id"):
            fail(f"expected ITSM degraded draft, got: {action}")
        itsm_draft_id = action["draft_id"]
        if action.get("tool") != "itsm.incident_open":
            fail(f"wrong tool for ITSM draft: {action.get('tool')}")
        ok(f"itsm draft_id={itsm_draft_id} tool=itsm.incident_open")

        # === Phase B: create an HR draft ===
        step("2. kill HR, fire leave-request → HR draft pending")
        _kill(HR_PORT)
        await _dead(c, HR_BASE)
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {write_both}",
            },
            json={
                "query": "please submit a 1-day leave request for resolve-routing drill",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        action = r.json().get("action") or {}
        if not action.get("degraded") or not action.get("draft_id"):
            fail(f"expected HR degraded draft, got: {action}")
        hr_draft_id = action["draft_id"]
        if action.get("tool") != "hr.leave_request":
            fail(f"wrong tool for HR draft: {action.get('tool')}")
        ok(f"hr draft_id={hr_draft_id} tool=hr.leave_request")

        # === Phase C: restart both and wait CB ===
        step("3. restart both servers, wait 32s for CB recovery")
        hr_proc = _spawn_hr()
        itsm_proc = _spawn_itsm()
        if not await _healthy(c, HR_BASE):
            fail("HR didn't come back")
        if not await _healthy(c, ITSM_BASE):
            fail("ITSM didn't come back")
        print("    waiting 32s for both CBs to exit OPEN...")
        await asyncio.sleep(32)
        ok("both servers up, CBs ready to probe")

        # === Phase D: resolve each draft, verify correct routing ===
        step("4. resolve ITSM draft → routes to ITSM, incident_id returned")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{itsm_draft_id}/resolve",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": f"Bearer {write_both}",
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"ITSM resolve returned {r.status_code}: {r.text[:300]}")
        body = r.json()
        if not body.get("ok"):
            fail(f"ITSM resolve not ok: {body}")
        incident_id = (body.get("result") or {}).get("incident_id")
        if not incident_id or not incident_id.startswith("ITSM-"):
            fail(f"ITSM draft didn't resolve to ITSM ticket: {body}")
        ok(f"itsm draft → incident_id={incident_id}")

        step("5. resolve HR draft → routes to HR, ticket_id returned")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{hr_draft_id}/resolve",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": f"Bearer {write_both}",
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"HR resolve returned {r.status_code}: {r.text[:300]}")
        body = r.json()
        if not body.get("ok"):
            fail(f"HR resolve not ok: {body}")
        ticket_id = (body.get("result") or {}).get("ticket_id")
        if not ticket_id or not ticket_id.startswith("HR-"):
            fail(f"HR draft didn't resolve to HR ticket: {body}")
        ok(f"hr draft → ticket_id={ticket_id}")

        step("6. GET /drafts — no pending drafts remain for tenant")
        r = await c.get(
            f"{INFERENCE}/api/v1/drafts?status=pending",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": f"Bearer {write_both}",
            },
        )
        remaining = {d["draft_id"] for d in (r.json().get("drafts") or [])}
        if itsm_draft_id in remaining or hr_draft_id in remaining:
            fail(f"drafts still pending: {remaining}")
        ok(f"pending drafts post-resolve: {sorted(remaining)} — neither drill draft remains")

        step("7. re-resolve either → 409 DRAFT_NOT_PENDING (consistency)")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{itsm_draft_id}/resolve",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": f"Bearer {write_both}",
            },
        )
        if r.status_code != 409:
            fail(f"expected 409 on re-resolve, got {r.status_code}")
        detail = r.json().get("detail") or {}
        if detail.get("code") != "DRAFT_NOT_PENDING":
            fail(f"expected DRAFT_NOT_PENDING, got: {detail}")
        ok("re-resolve correctly returns 409 DRAFT_NOT_PENDING")

    if hr_proc and hr_proc.poll() is None:
        hr_proc.terminate()
    if itsm_proc and itsm_proc.poll() is None:
        itsm_proc.terminate()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 RESOLVE-ROUTING STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
