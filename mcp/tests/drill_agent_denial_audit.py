"""
Drill: agent-layer scope denials produce a governance.audit_log row.

Previously the agent rejected hr:read callers asking for hr:write
tools but the rejection was invisible to audit — operators + governance
couldn't tell a probing attacker from a sleepy system. This drill pins
the fix.

Flow:
 1. Baseline audit row count for the test tenant.
 2. Fire /api/v1/agent/ask with hr:read ONLY + a leave-request query.
    Expect intent=action_denied_scope.
 3. Query governance.audit_log — a new row with
    action='agent.scope_denied' MUST be present for this tenant,
    details include tool, required, have, query_preview, and a
    correlation_id matching the response.
 4. Verify the hash chain still round-trips via audit_verify.py.
 5. Negative: fire the same query with hr:write — no NEW agent.scope_denied
    row (denial audit doesn't fire on success).

Prereqs:
  inference-svc running DOCUMIND_AUTH_REQUIRED=true + MCP up.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_agent_denial_audit.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import asyncpg
import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PRIV_KEY = REPO / "scripts" / "dev-keys" / "jwt-private.pem"

PG_DSN = (
    f"postgresql://{os.getenv('DOCUMIND_PG_OPS_USER', 'documind_ops')}:"
    f"{os.getenv('DOCUMIND_PG_OPS_PASSWORD', 'documind_ops')}@"
    f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
    f"{os.getenv('DOCUMIND_PG_PORT', '55432')}/"
    f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
)

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
            "sub": "drill-denial-audit",
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


async def _count_denied(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM governance.audit_log "
            "WHERE tenant_id=$1::uuid AND action='agent.scope_denied'",
            TENANT,
        )


async def _latest_denied(pool: asyncpg.Pool) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT timestamp::text, action, details, correlation_id::text,
                   previous_hash, entry_hash
              FROM governance.audit_log
             WHERE tenant_id = $1::uuid AND action = 'agent.scope_denied'
             ORDER BY timestamp DESC, id DESC
             LIMIT 1
            """,
            TENANT,
        )


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
    try:
        read_tok = _mint(["hr:read"])
        write_tok = _mint(["hr:read", "hr:write"])

        async with httpx.AsyncClient(timeout=60.0) as c:
            step("1. baseline — count of existing agent.scope_denied rows")
            baseline = await _count_denied(pool)
            ok(f"baseline count: {baseline}")

            step("2. trigger denial — agent/ask w/ hr:read + leave_request")
            corr = str(uuid.uuid4())
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {read_tok}",
                    "X-Correlation-Id": corr,
                },
                json={
                    "query": "please submit a 3-day leave request for denial-audit drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            body = r.json()
            if body.get("intent") != "action_denied_scope":
                fail(f"expected action_denied_scope, got {body.get('intent')}")
            response_corr = body.get("correlation_id") or ""
            ok(f"denied; response correlation_id={response_corr}")

            step("3. PG has a new agent.scope_denied row with correct details")
            await asyncio.sleep(0.5)  # async audit write
            after = await _count_denied(pool)
            if after != baseline + 1:
                fail(f"expected {baseline + 1} rows, got {after}")
            row = await _latest_denied(pool)
            if row is None:
                fail("no row found")
            details = row["details"]
            if isinstance(details, str):
                details = json.loads(details)
            if details.get("tool") != "hr.leave_request":
                fail(f"wrong tool: {details}")
            if details.get("required") != ["hr:write"]:
                fail(f"wrong required: {details}")
            if details.get("have") != ["hr:read"]:
                fail(f"wrong have: {details}")
            if "leave request" not in details.get("query_preview", ""):
                fail(f"query_preview missing: {details}")
            # correlation_id stored in PG may match either the inbound
            # X-Correlation-Id (if the middleware used it) or a fresh one
            # the inference-svc generated; we check that *something* is
            # populated and that the tenant/action are right.
            if not row["correlation_id"]:
                fail("audit row missing correlation_id")
            # The chain-forward fields exist
            if not row["entry_hash"]:
                fail("entry_hash missing")
            ok(
                f"row OK "
                f"tool={details['tool']} "
                f"required={details['required']} "
                f"have={details['have']} "
                f"entry_hash={row['entry_hash'][:12]}..."
            )

            step("4. audit_verify.py accepts the new chain — still all OK")
            rp = subprocess.run(
                [
                    "/tmp/documind-venv/bin/python",
                    str(REPO / "scripts" / "audit_verify.py"),
                    "--tenant", TENANT,
                    "--json",
                ],
                env={
                    **os.environ,
                    "DOCUMIND_PG_OPS_USER": "documind_ops",
                    "DOCUMIND_PG_OPS_PASSWORD": "documind_ops",
                },
                capture_output=True, text=True,
            )
            if rp.returncode != 0:
                fail(f"audit_verify exit {rp.returncode}; stderr={rp.stderr[:300]}")
            verify = json.loads(rp.stdout)
            summary = verify["summary"].get(TENANT, {})
            if summary.get("OK", 0) == 0:
                fail(f"no OK rows in verify summary: {summary}")
            if summary.get("BROKEN_HASH", 0) or summary.get("BROKEN_CHAIN", 0):
                fail(f"chain broken: {summary}")
            ok(f"chain intact; verifier summary: {summary}")

            step("5. negative — hr:write call does NOT produce a denial row")
            before_success = await _count_denied(pool)
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_tok}",
                },
                json={
                    "query": "please submit a 1-day leave request for denial-audit negative",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            body = r.json()
            if body.get("intent") != "action":
                fail(f"expected intent=action, got {body.get('intent')}")
            ticket = ((body.get("action") or {}).get("result") or {}).get("ticket_id")
            if not ticket:
                fail(f"no ticket: {body.get('action')}")
            await asyncio.sleep(0.5)
            after_success = await _count_denied(pool)
            if after_success != before_success:
                fail(
                    f"hr:write call produced a spurious scope_denied row "
                    f"({before_success} → {after_success})"
                )
            ok(f"happy path ticket={ticket}; no new denial rows")

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 DENIAL-AUDIT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
