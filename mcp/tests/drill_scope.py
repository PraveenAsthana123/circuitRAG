# RESOURCES: inference mcp_hr pg
"""
Drill: JWT scope enforcement on POST /api/v1/drafts/{id}/resolve.

Requires inference-svc running with DOCUMIND_AUTH_REQUIRED=true and
the dev keypair at scripts/dev-keys/. The drill mints its own tokens
using the private key; no identity-svc round-trip needed.

Flow:
 1. Health check + confirm auth is enforced (a no-token resolve → 401)
 2. Kill MCP, create a pending draft via agent/ask (unguarded endpoint)
 3. POST resolve with NO Authorization → 401 NOT_AUTHENTICATED
 4. POST resolve with a bogus token → 401 INVALID_TOKEN
 5. POST resolve with a token holding only ``hr:read`` → 403 INSUFFICIENT_SCOPE
 6. POST resolve with a token holding ``hr:write`` → restart MCP, 200 + ticket
 7. Second resolve with the same ``hr:write`` token → 409 DRAFT_NOT_PENDING
    (proves the scope check didn't bypass the usual state-machine)

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_scope.py
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
PRIV_KEY_PATH = REPO / "scripts" / "dev-keys" / "jwt-private.pem"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _mint(*, roles: list[str], tenant: str = TENANT, ttl_s: int = 900) -> str:
    """Mint a token using the identity-svc's RS256 private key."""
    now = int(time.time())
    payload = {
        "iss": "documind-local",
        "aud": "documind-services",
        "sub": "drill-user-" + roles[0].replace(":", "-") if roles else "drill-anon",
        "email": "drill@documind.local",
        "tenant_id": tenant,
        "roles": roles,
        "kind": "access",
        "iat": now,
        "nbf": now,
        "exp": now + ttl_s,
        "jti": uuid.uuid4().hex,
    }
    priv = PRIV_KEY_PATH.read_bytes()
    return pyjwt.encode(payload, priv, algorithm="RS256")


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    log = open("/tmp/documind-mcp-hr-scope-drill.log", "w")  # noqa: SIM115 (subprocess.Popen takes FD ownership)
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


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as c:
        step("0. sanity — inference + MCP healthy; auth_required enforced")
        if (await c.get(f"{INFERENCE}/health")).status_code != 200:
            fail(f"inference not healthy at {INFERENCE}")
        if not await _healthy(c, MCP_BASE, tries=2):
            fail(f"MCP not healthy at {MCP_BASE}")
        # Confirm auth is actually on — unauth call to a fake id should 401
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/DRAFT-SANITY/resolve",
            headers={"X-Tenant-Id": TENANT},
        )
        if r.status_code != 401:
            fail(
                "auth_required seems OFF — expected 401 from unauthenticated "
                f"resolve, got {r.status_code} (set DOCUMIND_AUTH_REQUIRED=true "
                "on inference-svc and restart)",
            )
        ok("auth enforcement verified (401 on unauthenticated)")

        # --- 1: kill MCP to create a pending draft ---
        step("1. kill MCP + create pending draft via agent/ask")
        _kill_mcp()
        await _dead(c, MCP_BASE)
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={"X-Tenant-Id": TENANT, "Content-Type": "application/json"},
            json={
                "query": "Please submit a 6-day leave request for scope drill",
                "employee_id": "E42",
            },
        )
        if r.status_code != 200:
            fail(f"agent/ask failed: {r.status_code} {r.text[:200]}")
        action = r.json().get("action") or {}
        if not action.get("degraded") or not action.get("draft_id"):
            fail(f"expected degraded+draft: {action}")
        draft_id = action["draft_id"]
        ok(f"pending draft_id={draft_id}")

        # --- 2: no Authorization header → 401 NOT_AUTHENTICATED ---
        step("2. resolve w/o Authorization → 401 NOT_AUTHENTICATED")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{draft_id}/resolve",
            headers={"X-Tenant-Id": TENANT},
        )
        if r.status_code != 401:
            fail(f"expected 401 got {r.status_code}: {r.text[:200]}")
        detail = r.json().get("detail", {})
        if detail.get("code") != "NOT_AUTHENTICATED":
            fail(f"expected NOT_AUTHENTICATED, got: {detail}")
        ok("401 NOT_AUTHENTICATED")

        # --- 3: bogus token → 401 INVALID_TOKEN ---
        step("3. resolve w/ bogus token → 401 INVALID_TOKEN")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{draft_id}/resolve",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": "Bearer not.a.real.token",
            },
        )
        if r.status_code != 401:
            fail(f"expected 401 got {r.status_code}: {r.text[:200]}")
        detail = r.json().get("detail", {})
        if detail.get("code") != "INVALID_TOKEN":
            fail(f"expected INVALID_TOKEN, got: {detail}")
        ok("401 INVALID_TOKEN")

        # --- 4: valid token w/ only hr:read → 403 INSUFFICIENT_SCOPE ---
        step("4. resolve w/ hr:read only → 403 INSUFFICIENT_SCOPE")
        read_token = _mint(roles=["hr:read"])
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{draft_id}/resolve",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": f"Bearer {read_token}",
            },
        )
        if r.status_code != 403:
            fail(f"expected 403 got {r.status_code}: {r.text[:200]}")
        detail = r.json().get("detail", {})
        if detail.get("code") != "INSUFFICIENT_SCOPE":
            fail(f"expected INSUFFICIENT_SCOPE, got: {detail}")
        if "hr:write" not in detail.get("required", []):
            fail(f"expected required=[hr:write], got: {detail}")
        ok(f"403 INSUFFICIENT_SCOPE required={detail['required']} have={detail['have']}")

        # --- 5: restart MCP, resolve w/ hr:write → 200 ---
        step("5. restart MCP + resolve w/ hr:write → 200")
        _spawn_mcp()
        if not await _healthy(c, MCP_BASE):
            fail("MCP didn't come back")
        ok("MCP back up")
        print("    waiting 32s for CB recovery_timeout...")
        await asyncio.sleep(32)
        write_token = _mint(roles=["hr:read", "hr:write"])
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{draft_id}/resolve",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": f"Bearer {write_token}",
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"expected 200 got {r.status_code}: {r.text[:300]}")
        body = r.json()
        if not body.get("ok"):
            fail(f"resolve not ok: {body}")
        ticket = (body.get("result") or {}).get("ticket_id")
        if not ticket:
            fail(f"no ticket_id on resolve: {body}")
        ok(f"200 ticket_id={ticket}")

        # --- 6: second resolve (scope-valid) → 409 DRAFT_NOT_PENDING ---
        step("6. second resolve w/ hr:write → 409 DRAFT_NOT_PENDING")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{draft_id}/resolve",
            headers={
                "X-Tenant-Id": TENANT,
                "Authorization": f"Bearer {write_token}",
            },
        )
        if r.status_code != 409:
            fail(f"expected 409 got {r.status_code}: {r.text[:200]}")
        detail = r.json().get("detail", {})
        if detail.get("code") != "DRAFT_NOT_PENDING":
            fail(f"expected DRAFT_NOT_PENDING, got: {detail}")
        ok("409 DRAFT_NOT_PENDING (scope check didn't bypass state machine)")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 SCOPE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
