# RESOURCES: mcp_hr inference pg
"""
Drill: operator can REJECT a pending draft + worker skips it forever.

Schema (migrations 003 + 006) allows ``status='rejected'`` but no
operator path existed. Result: a draft the worker can't replay
(bad arguments, expired tool target) sits as ``pending`` forever
while the worker burns retry cycles. This commit ships the missing
endpoint + state transition.

Negative-assertion catalog (every step proves something does NOT
happen):
 1. Pending draft via agent/ask + MCP-down → baseline.
 2. POST /api/v1/drafts/{id}/reject {reason} → 200 + status=rejected.
    Negative: the row's status DID NOT stay 'pending'.
 3. Restart MCP, run worker.sweep_once(). The rejected draft is NOT
    in ``list_pending``, so the worker does NOT pick it up. Stats:
    replayed=0 (or for unrelated drafts only).
 4. Reject the same draft again → 409 DRAFT_NOT_PENDING.
    Negative: a second operator clicking "reject" doesn't overwrite
    the first rejection's reason.
 5. Reject a non-existent draft → 404 DRAFT_NOT_FOUND.
 6. Audit row exists with action=mcp_draft.rejected, actor_type=operator,
    reason matches request body.
    Negative: actor_type is NOT 'service' / 'system'; reason is NOT
    NULL / empty.
 7. Reject without auth (auth_required=true) → 401.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_draft_reject.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

from mcp import MCPClient, PostgresDraftStore  # noqa: E402
from app.workers.draft_replay import DraftReplayWorker  # type: ignore  # noqa: E402

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PRIV_KEY = REPO / "scripts" / "dev-keys" / "jwt-private.pem"
PG_DSN = (
    f"postgresql://{os.getenv('DOCUMIND_PG_USER', 'documind_app')}:"
    f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind_app')}@"
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


def _mint(roles: list[str], sub: str) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": "documind-local",
            "aud": "documind-services",
            "sub": sub,
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
    subprocess.run(
        ["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True,
    )


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    env["MCP_AUTH_REQUIRED"] = "true"
    env["MCP_JWT_PUBLIC_KEY_PATH"] = str(REPO / "scripts" / "dev-keys" / "jwt-public.pem")
    log = open("/tmp/documind-mcp-reject-drill.log", "w")
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


async def _read_audit_row_for(pool: asyncpg.Pool, draft_id: str) -> dict | None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            row = await conn.fetchrow(
                """
                SELECT actor_type, actor_id::text AS actor_id,
                       action, details
                  FROM governance.audit_log
                 WHERE tenant_id = $1::uuid
                   AND action = 'mcp_draft.rejected'
                   AND details->>'draft_id' = $2
                 ORDER BY timestamp DESC, id DESC
                 LIMIT 1
                """,
                TENANT, draft_id,
            )
    if row is None:
        return None
    d = row["details"]
    if isinstance(d, str):
        d = json.loads(d)
    return {
        "actor_type": row["actor_type"],
        "actor_id": row["actor_id"],
        "action": row["action"],
        "details": d,
    }


async def _read_draft_status(pool: asyncpg.Pool, draft_id: str) -> str | None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            row = await conn.fetchrow(
                "SELECT status FROM governance.action_drafts WHERE draft_id=$1",
                draft_id,
            )
    return row["status"] if row else None


async def main() -> None:
    OPERATOR_SUB = "operator-bob@drill.local"
    write_tok = _mint(["hr:read", "hr:write"], sub=OPERATOR_SUB)

    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
    mcp_proc = None
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            step("1. kill MCP + agent/ask → pending draft")
            _kill_mcp()
            await _dead(c, MCP_BASE)
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_tok}",
                },
                json={
                    "query": "please submit a 3-day leave for reject-drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            draft_id = (r.json().get("action") or {}).get("draft_id")
            if not draft_id:
                fail(f"no draft_id: {r.json()}")
            ok(f"draft={draft_id}")

            step("2. POST /reject → 200 + status=rejected")
            REASON = "drill: this employee_id is not real, do not retry"
            r = await c.post(
                f"{INFERENCE}/api/v1/drafts/{draft_id}/reject",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Authorization": f"Bearer {write_tok}",
                    "Content-Type": "application/json",
                },
                json={"reason": REASON},
                timeout=10.0,
            )
            if r.status_code != 200:
                fail(f"reject returned {r.status_code}: {r.text[:300]}")
            body = r.json()
            if not body.get("ok"):
                fail(f"reject body not ok: {body}")
            if body.get("status") != "rejected":
                fail(f"expected status=rejected, got {body.get('status')!r}")
            # Verify the row is actually transitioned in the DB.
            db_status = await _read_draft_status(pool, draft_id)
            if db_status != "rejected":
                fail(
                    f"DB says status={db_status!r} but API said rejected — "
                    f"transition not persisted!"
                )
            ok(f"status=rejected (DB confirms; reason echoed: {body['reason'][:30]}...)")

            step("3. worker.sweep_once() does NOT pick up the rejected draft")
            mcp_proc = _spawn_mcp()
            if not await _healthy(c, MCP_BASE):
                fail("MCP didn't return")
            # Build a fresh worker client + DraftReplayWorker.
            pool2 = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)

            class _FakeDb:
                def __init__(self, p): self._pool = p
                def tenant_connection(self, t):
                    @asynccontextmanager
                    async def _cm():
                        async with self._pool.acquire() as conn:
                            async with conn.transaction():
                                await conn.execute(
                                    "SELECT set_config('app.current_tenant', $1, true)", t,
                                )
                                yield conn
                    return _cm()
                def admin_connection(self):
                    @asynccontextmanager
                    async def _cm():
                        async with self._pool.acquire() as conn:
                            yield conn
                    return _cm()

            db = _FakeDb(pool2)
            store = PostgresDraftStore(db)
            client = MCPClient(
                base_url=MCP_BASE, draft_store=store, recovery_timeout=1.0,
            )
            svc_tok = _mint(["hr:read", "hr:write"], sub="service:reject-drill-worker")
            worker = DraftReplayWorker(
                mcp_clients={"hr": client},
                tenant_ids=[TENANT],
                interval_s=1,
                per_draft_backoff_s=1,
                service_auth_token=svc_tok,
            )
            await worker.sweep_once()
            # The rejected draft's id should NOT have been touched. We verify
            # by re-reading status: must still be 'rejected', not 'replayed'.
            post_sweep_status = await _read_draft_status(pool, draft_id)
            if post_sweep_status != "rejected":
                fail(
                    f"worker mutated rejected draft! status={post_sweep_status!r}. "
                    f"list_pending must filter status='pending' — see drafts.py."
                )
            ok(
                f"worker.sweep_once() left rejected draft alone "
                f"(status still 'rejected'; replayed_count={worker.stats['replayed']})"
            )
            await client.close()
            await pool2.close()

            step("4. Re-reject same draft → 409 DRAFT_NOT_PENDING")
            r = await c.post(
                f"{INFERENCE}/api/v1/drafts/{draft_id}/reject",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Authorization": f"Bearer {write_tok}",
                    "Content-Type": "application/json",
                },
                json={"reason": "second-operator override attempt"},
                timeout=10.0,
            )
            if r.status_code != 409:
                fail(f"expected 409, got {r.status_code}: {r.text[:200]}")
            err = r.json().get("detail", {})
            if err.get("code") != "DRAFT_NOT_PENDING":
                fail(f"expected code=DRAFT_NOT_PENDING, got {err}")
            ok(f"second reject → 409 DRAFT_NOT_PENDING (CAS guard works)")

            step("5. Reject non-existent draft → 404 DRAFT_NOT_FOUND")
            r = await c.post(
                f"{INFERENCE}/api/v1/drafts/DRAFT-DOES-NOT-EXIST/reject",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Authorization": f"Bearer {write_tok}",
                    "Content-Type": "application/json",
                },
                json={"reason": "non-existent"},
                timeout=10.0,
            )
            if r.status_code != 404:
                fail(f"expected 404, got {r.status_code}: {r.text[:200]}")
            ok("non-existent draft → 404")

            step("6. Audit row exists with operator attribution + reason")
            audit_row = await _read_audit_row_for(pool, draft_id)
            if audit_row is None:
                fail(f"no audit row for action=mcp_draft.rejected draft_id={draft_id}")
            if audit_row["actor_type"] != "operator":
                fail(
                    f"actor_type={audit_row['actor_type']!r} — operator route MUST "
                    f"stamp 'operator' when JWT sub is present"
                )
            if audit_row["actor_id"] != OPERATOR_SUB:
                fail(
                    f"actor_id={audit_row['actor_id']!r} — should match JWT sub "
                    f"{OPERATOR_SUB!r}"
                )
            stored_reason = audit_row["details"].get("reason")
            if stored_reason != REASON:
                fail(
                    f"reason in audit row != request body: "
                    f"got {stored_reason!r}, want {REASON!r}"
                )
            ok(
                f"audit row: actor_type=operator actor_id={OPERATOR_SUB!r} "
                f"reason={stored_reason[:40]!r}"
            )

            step("7. Reject without Authorization → 401")
            # Fresh draft so we don't 409 on the rejected one.
            _kill_mcp()
            await _dead(c, MCP_BASE)
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_tok}",
                },
                json={
                    "query": "please submit a 1-day leave for reject-drill step 7",
                    "employee_id": "E99",
                },
                timeout=60.0,
            )
            unauth_draft = (r.json().get("action") or {}).get("draft_id")
            if not unauth_draft:
                fail(f"step 7 setup: no draft: {r.json()}")
            r = await c.post(
                f"{INFERENCE}/api/v1/drafts/{unauth_draft}/reject",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    # No Authorization header.
                },
                json={"reason": "should be rejected by auth, not by handler"},
                timeout=10.0,
            )
            if r.status_code != 401:
                fail(f"expected 401, got {r.status_code}: {r.text[:200]}")
            ok("unauthenticated reject → 401")

            # Bonus cleanup: reject the unauth_draft properly so it doesn't
            # litter pending state for future runs.
            await c.post(
                f"{INFERENCE}/api/v1/drafts/{unauth_draft}/reject",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Authorization": f"Bearer {write_tok}",
                    "Content-Type": "application/json",
                },
                json={"reason": "drill cleanup"},
                timeout=10.0,
            )

    finally:
        if mcp_proc is not None and mcp_proc.poll() is None:
            mcp_proc.terminate()
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 DRAFT-REJECT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
