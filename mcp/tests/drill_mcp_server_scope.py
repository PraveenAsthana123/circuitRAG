# RESOURCES: mcp_hr
"""
Drill: MCP server enforces per-tool scopes defence-in-depth.

Hits `http://127.0.0.1:8090/tools/call` directly (bypassing
inference-svc) to prove that an attacker with network access to the
MCP server cannot execute tools without a scoped JWT — closing the
gap where inference-svc's /api/v1/drafts/{id}/resolve was the only
scope gate.

Flow:
 1. Sanity — MCP server running with MCP_AUTH_REQUIRED=true.
 2. Direct /tools/call without Authorization → 401 NOT_AUTHENTICATED.
 3. Direct /tools/call with bogus token → 401 INVALID_TOKEN.
 4. Direct hr.leave_request with hr:read only → 403 INSUFFICIENT_SCOPE
    + detail lists required=[hr:write] have=[hr:read].
 5. Direct hr.leave_request with hr:write → 200 + ticket_id.
 6. Direct hr.policy_lookup (a read tool) with hr:read → 200.
 7. Idempotent replay from step 5 with hr:write again → same ticket
    (scope re-enforced; scope doesn't bypass state machine).
 8. Idempotent replay attempt with hr:read ONLY — still 403. The
    scope check runs BEFORE the idempotency cache lookup, so a
    leaked idempotency_key isn't a replay primitive.

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_mcp_server_scope.py

Prerequisite: MCP server must be running with
    MCP_AUTH_REQUIRED=true
    MCP_JWT_PUBLIC_KEY_PATH=/mnt/deepa/rag/scripts/dev-keys/jwt-public.pem
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
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
            "sub": "drill-" + (roles[0].replace(":", "-") if roles else "anon"),
            "email": "drill@documind.local",
            "tenant_id": TENANT,
            "roles": roles,
            "kind": "access",
            "iat": now,
            "nbf": now,
            "exp": now + 900,
            "jti": uuid.uuid4().hex,
        },
        PRIV_KEY.read_bytes(),
        algorithm="RS256",
    )


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as c:
        step("1. sanity — /health OK without auth (public)")
        r = await c.get(f"{MCP_BASE}/health")
        if r.status_code != 200:
            fail(f"/health returned {r.status_code}")
        ok("mcp-server-hr is up")

        # Quickly verify auth is actually ON by sending a call without
        # any Authorization header — 401 means enforcement is live.
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            json={
                "name": "hr.leave_request",
                "arguments": {"employee_id": "E1", "days": 1, "reason": "sanity"},
                "tenant_id": TENANT,
            },
        )
        if r.status_code != 401:
            fail(
                f"auth is OFF — expected 401 for unauthenticated call, got "
                f"{r.status_code}. Start MCP with MCP_AUTH_REQUIRED=true.",
            )
        ok("MCP_AUTH_REQUIRED enforcement confirmed")

        step("2. /tools/call no Authorization → 401 NOT_AUTHENTICATED")
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            json={
                "name": "hr.leave_request",
                "arguments": {"employee_id": "E1", "days": 1, "reason": "x"},
                "tenant_id": TENANT,
            },
        )
        d = r.json().get("detail") or {}
        if r.status_code != 401 or d.get("code") != "NOT_AUTHENTICATED":
            fail(f"expected 401 NOT_AUTHENTICATED, got {r.status_code}: {d}")
        ok("401 NOT_AUTHENTICATED")

        step("3. bogus token → 401 INVALID_TOKEN")
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            headers={"Authorization": "Bearer not.a.real.jwt"},
            json={
                "name": "hr.leave_request",
                "arguments": {"employee_id": "E1", "days": 1, "reason": "x"},
                "tenant_id": TENANT,
            },
        )
        d = r.json().get("detail") or {}
        if r.status_code != 401 or d.get("code") != "INVALID_TOKEN":
            fail(f"expected 401 INVALID_TOKEN, got {r.status_code}: {d}")
        ok("401 INVALID_TOKEN")

        read_tok = _mint(["hr:read"])
        write_tok = _mint(["hr:read", "hr:write"])

        step("4. hr.leave_request w/ hr:read only → 403 INSUFFICIENT_SCOPE")
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            headers={"Authorization": f"Bearer {read_tok}"},
            json={
                "name": "hr.leave_request",
                "arguments": {"employee_id": "E1", "days": 1, "reason": "x"},
                "tenant_id": TENANT,
            },
        )
        d = r.json().get("detail") or {}
        if r.status_code != 403 or d.get("code") != "INSUFFICIENT_SCOPE":
            fail(f"expected 403 INSUFFICIENT_SCOPE, got {r.status_code}: {d}")
        if "hr:write" not in d.get("required", []):
            fail(f"expected required=[hr:write], got: {d}")
        if "hr:read" not in d.get("have", []):
            fail(f"expected have to include hr:read, got: {d}")
        ok(
            f"403 INSUFFICIENT_SCOPE tool={d['tool']} "
            f"required={d['required']} have={d['have']}"
        )

        step("5. hr.leave_request w/ hr:write → 200 + ticket")
        idem_key = uuid.uuid4().hex
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            headers={
                "Authorization": f"Bearer {write_tok}",
                "Idempotency-Key": idem_key,
            },
            json={
                "name": "hr.leave_request",
                "arguments": {"employee_id": "E1", "days": 2, "reason": "server-scope-drill"},
                "tenant_id": TENANT,
                "correlation_id": str(uuid.uuid4()),
            },
        )
        body = r.json()
        if r.status_code != 200 or not body.get("ok"):
            fail(f"expected 200 ok, got {r.status_code}: {body}")
        ticket = (body.get("result") or {}).get("ticket_id")
        if not ticket:
            fail(f"no ticket_id: {body}")
        ok(f"200 ticket_id={ticket}")

        step("6. hr.policy_lookup (read tool) w/ hr:read → 200")
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            headers={"Authorization": f"Bearer {read_tok}"},
            json={
                "name": "hr.policy_lookup",
                "arguments": {"policy_name": "leave"},
                "tenant_id": TENANT,
            },
        )
        body = r.json()
        if r.status_code != 200 or not body.get("ok"):
            fail(f"expected 200 ok for policy_lookup w/ hr:read, got {r.status_code}: {body}")
        ok(f"200 policy_lookup text='{body['result']['text'][:40]}...'")

        step("7. idempotent replay w/ hr:write again → same ticket")
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            headers={
                "Authorization": f"Bearer {write_tok}",
                "Idempotency-Key": idem_key,
            },
            json={
                "name": "hr.leave_request",
                "arguments": {"employee_id": "E1", "days": 2, "reason": "server-scope-drill"},
                "tenant_id": TENANT,
            },
        )
        body = r.json()
        if r.status_code != 200 or not body.get("ok"):
            fail(f"replay failed: {body}")
        if (body.get("result") or {}).get("ticket_id") != ticket:
            fail(f"replay ticket mismatch: {body}")
        if not body.get("idempotent_replay"):
            fail(f"expected idempotent_replay=True: {body}")
        ok(f"replay returned SAME ticket={ticket} idempotent_replay=True")

        step("8. replay attempt w/ hr:read only → 403 (scope check before cache)")
        r = await c.post(
            f"{MCP_BASE}/tools/call",
            headers={
                "Authorization": f"Bearer {read_tok}",
                "Idempotency-Key": idem_key,  # same key — scope must still gate
            },
            json={
                "name": "hr.leave_request",
                "arguments": {"employee_id": "E1", "days": 2, "reason": "server-scope-drill"},
                "tenant_id": TENANT,
            },
        )
        d = r.json().get("detail") or {}
        if r.status_code != 403 or d.get("code") != "INSUFFICIENT_SCOPE":
            fail(
                f"idempotent-key + insufficient scope should STILL 403 "
                f"(else a leaked key is a replay primitive); got "
                f"{r.status_code}: {d}"
            )
        ok("403 INSUFFICIENT_SCOPE on replay — idempotency cache does NOT bypass scope")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 MCP-SERVER-SCOPE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
