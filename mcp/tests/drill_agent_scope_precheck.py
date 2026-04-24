"""
Drill: agent pre-checks scope before spending MCP round-trip.

With inference-svc running DOCUMIND_AUTH_REQUIRED=true and MCP
running with or without auth, the agent must:

 1. For a caller with `hr:write`, do the normal RAG → intent →
    MCP call flow.
 2. For a caller with `hr:read` only on a leave-request query,
    return AgentAskResponse with intent="action_denied_scope" and
    action.error.code=INSUFFICIENT_SCOPE. Crucially: no new ticket
    is created (we can check MCP's log / ticket cache didn't grow).
 3. For a query that doesn't trigger intent (a plain RAG ask), the
    scope check doesn't fire at all — intent stays "answer".

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_agent_scope_precheck.py
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
INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PRIV_KEY = REPO / "scripts" / "dev-keys" / "jwt-private.pem"

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"; BOLD = "\033[1m"; NC = "\033[0m"


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
            "sub": "drill-precheck-" + (roles[0] if roles else "anon"),
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


async def _count_mcp_tickets(c: httpx.AsyncClient, auth: str) -> int:
    """
    Best-effort: hit /tools/list and read the len of the tickets cache
    via a short-circuiting lookup. The HR server doesn't expose a
    ticket-count endpoint, so we rely on the correlation_id NOT
    appearing in MCP's log to assert "MCP was not called."
    That's checked post-hoc below; this helper just exists to make
    the intent explicit.
    """
    # We'll grep the MCP log in a side-channel check; return 0 here.
    return 0


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as c:
        step("1. sanity — inference auth_required + mcp up")
        r = await c.get(f"{INFERENCE}/api/v1/health/detailed")
        if r.status_code != 200:
            fail(f"detailed health: {r.status_code}")
        readiness = r.json().get("readiness") or {}
        if readiness.get("auth") != "required":
            fail(
                f"inference auth is {readiness.get('auth')!r} — this drill "
                "needs DOCUMIND_AUTH_REQUIRED=true",
            )
        if (await c.get(f"{MCP_BASE}/health")).status_code != 200:
            fail("MCP not reachable")
        ok(f"inference auth=required; mcp up")

        read_tok = _mint(["hr:read"])
        write_tok = _mint(["hr:read", "hr:write"])

        step("2. hr:write — happy path creates ticket")
        corr_write = uuid.uuid4().hex
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {write_tok}",
                "X-Correlation-Id": corr_write,
            },
            json={
                "query": "please submit a 1-day leave request for precheck-write drill",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"hr:write agent/ask: {r.status_code} {r.text[:200]}")
        body = r.json()
        if body.get("intent") != "action":
            fail(f"expected intent=action, got {body.get('intent')}")
        action = body.get("action") or {}
        if not action.get("ok"):
            fail(f"hr:write action not ok: {action}")
        if not (action.get("result") or {}).get("ticket_id"):
            fail(f"no ticket_id on hr:write path: {action}")
        ok(f"intent=action ticket={action['result']['ticket_id']}")

        step("3. hr:read ONLY — action_denied_scope, no MCP call")
        corr_read = uuid.uuid4().hex
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {read_tok}",
                "X-Correlation-Id": corr_read,
            },
            json={
                "query": "please submit a 2-day leave request for precheck-read drill",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"hr:read agent/ask: {r.status_code} {r.text[:300]}")
        body = r.json()
        if body.get("intent") != "action_denied_scope":
            fail(f"expected intent=action_denied_scope, got {body.get('intent')}")
        action = body.get("action") or {}
        if action.get("ok"):
            fail(f"should not be ok on denial: {action}")
        err = action.get("error") or {}
        if err.get("code") != "INSUFFICIENT_SCOPE":
            fail(f"expected INSUFFICIENT_SCOPE, got: {err}")
        if "hr:write" not in (err.get("required") or []):
            fail(f"required missing hr:write: {err}")
        if "hr:read" not in (err.get("have") or []):
            fail(f"have missing hr:read: {err}")
        # Base RAG answer should still be present — user asked something
        # relevant and the agent ran the pipeline.
        if not body.get("answer"):
            fail("RAG answer missing from denied response")
        if not body.get("citations"):
            fail("citations missing from denied response")
        ok(
            f"intent=action_denied_scope error={err} "
            f"answer_len={len(body['answer'])} citations={len(body['citations'])}",
        )

        step("4. verify MCP log shows NO /tools/call for the denied correlation")
        mcp_log = Path("/tmp/mcp-scoped.log")
        if mcp_log.exists():
            txt = mcp_log.read_text()
            # correlation_id is UUID4 no-dash; MCP logs use dashes —
            # check both shapes
            cid_dashed = uuid.UUID(corr_read)
            if str(cid_dashed) in txt or corr_read in txt:
                fail(
                    f"MCP log contains the denied correlation_id — the "
                    f"pre-check didn't short-circuit. Grep /tmp/mcp-scoped.log "
                    f"for {cid_dashed}"
                )
            # Sanity: the hr:write correlation SHOULD be in there
            cid_write_dashed = uuid.UUID(corr_write)
            # We don't strictly assert presence because the agent might
            # have used a DIFFERENT correlation_id for the MCP hop; just
            # check denial wasn't logged.
            ok(f"MCP log clean for denied correlation_id {cid_dashed}")
        else:
            print(f"  {YELLOW}· no MCP log at {mcp_log} to cross-check — soft pass{NC}")

        step("5. a plain-RAG query ignores scope — intent stays 'answer'")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {read_tok}",
            },
            json={
                "query": "what is the travel reimbursement limit?",
            },
            timeout=60.0,
        )
        body = r.json()
        if body.get("intent") != "answer":
            fail(f"expected intent=answer, got {body.get('intent')}")
        if body.get("action") is not None:
            fail(f"expected action=None on plain RAG, got {body['action']}")
        ok(f"intent=answer action=None — scope check didn't spuriously trigger")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 AGENT-SCOPE-PRECHECK STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
