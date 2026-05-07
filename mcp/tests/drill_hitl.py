# RESOURCES: mcp_hr inference pg
"""
Drill: prove HITL persistence for MCP drafts.

End-to-end scenario:

 1. Start: MCP server up. PG pool opened. MCPClient wired with
    PostgresDraftStore.
 2. ``call_tool`` to create a real ticket — happy path (CB CLOSED, no
    draft).
 3. Kill MCP. Call again — connection refused → draft persisted to
    ``governance.action_drafts``.
 4. Query PG directly — row MUST exist with status='pending',
    tool='hr.leave_request', correct tenant_id.
 5. Restart MCP. Call ``resolve_draft(draft_id, tenant_id)`` — replay
    succeeds, ticket created, draft row updated to status='replayed'.
 6. Query PG — status='replayed', replay_result contains ticket_id,
    replayed_at not NULL.

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    cd /mnt/deepa/rag
    PYTHONPATH=. DOCUMIND_PG_USER=documind_app DOCUMIND_PG_PASSWORD=documind_app \\
      DOCUMIND_PG_HOST=localhost DOCUMIND_PG_PORT=55432 \\
      DOCUMIND_PG_DB=documind \\
      python mcp/tests/drill_hitl.py

Exit 0 on all green.
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import asyncpg
import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp import MCPClient, PostgresDraftStore  # noqa: E402

PG_DSN = (
    f"postgresql://{os.getenv('DOCUMIND_PG_USER', 'documind_app')}:"
    f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind_app')}@"
    f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
    f"{os.getenv('DOCUMIND_PG_PORT', '55432')}/"
    f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
)
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))


GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


class _FakeDb:
    """Thin DbClient shim exposing the two context managers the store needs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def tenant_connection(self, tenant_id: str):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1, true)",
                        tenant_id,
                    )
                    yield conn
        return _cm()

    def admin_connection(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            async with self._pool.acquire() as conn:
                yield conn
        return _cm()


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    log = open("/tmp/documind-mcp-hr-drill.log", "w")  # noqa: SIM115 (subprocess.Popen takes FD ownership)
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_hr.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )


async def _wait_healthy(url: str, tries: int = 30) -> bool:
    async with httpx.AsyncClient(timeout=2.0) as c:
        for _ in range(tries):
            try:
                r = await c.get(f"{url}/health")
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    return False


async def main() -> None:
    # ---- 1. Setup ----------------------------------------------------
    step("1. Bring up MCP + open PG pool")
    mcp_proc = _spawn_mcp()
    try:
        healthy = await _wait_healthy(MCP_BASE)
        if not healthy:
            fail(f"MCP did not come up at {MCP_BASE}")
        ok(f"MCP healthy at {MCP_BASE}")

        pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3)
        try:
            db = _FakeDb(pool)
            store = PostgresDraftStore(db)
            client = MCPClient(base_url=MCP_BASE, draft_store=store)
            ok("PG pool open + PostgresDraftStore wired")

            # ---- 2. Happy path -------------------------------------
            step("2. Happy path — ticket created (no draft)")
            r = await client.call_tool(
                "hr.leave_request",
                {"employee_id": "E99", "days": 1, "reason": "drill happy"},
                tenant_id=TENANT,
            )
            if not r.ok or not r.data or not r.data.get("ticket_id"):
                fail(f"happy path failed: {r}")
            ok(f"ticket_id={r.data['ticket_id']}")

            # ---- 3. Kill MCP, call again -> draft persisted --------
            step("3. Kill MCP → call fails → draft persisted")
            mcp_proc.send_signal(signal.SIGTERM)
            try:
                mcp_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mcp_proc.kill()
            await asyncio.sleep(1)

            r = await client.call_tool(
                "hr.leave_request",
                {"employee_id": "E99", "days": 2, "reason": "drill degraded"},
                tenant_id=TENANT,
            )
            if not (r.degraded and r.draft_id):
                fail(f"expected degraded+draft_id, got: {r}")
            draft_id = r.draft_id
            ok(f"degraded=True draft_id={draft_id}")

            # ---- 4. Verify PG row ---------------------------------
            step("4. Query PG — row exists, status='pending'")
            async with pool.acquire() as conn:
                # BYPASS tenant to verify — using admin (the pool user is
                # documind_app, so RLS applies; we set tenant here).
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, false)",
                    TENANT,
                )
                row = await conn.fetchrow(
                    "SELECT draft_id, tenant_id::text, tool, status, "
                    "arguments, reason FROM governance.action_drafts "
                    "WHERE draft_id = $1",
                    draft_id,
                )
                # reset the setting so we don't leak into other tests
                await conn.execute("SELECT set_config('app.current_tenant', '', false)")
            if row is None:
                fail(f"no PG row for draft_id={draft_id}")
            if row["status"] != "pending":
                fail(f"expected status=pending got={row['status']}")
            if row["tool"] != "hr.leave_request":
                fail(f"expected tool=hr.leave_request got={row['tool']}")
            if row["tenant_id"] != TENANT:
                fail(f"expected tenant_id={TENANT} got={row['tenant_id']}")
            args = row["arguments"]
            import json as _json
            if isinstance(args, str):
                args = _json.loads(args)
            if args.get("days") != 2:
                fail(f"expected days=2 got={args}")
            ok(f"row OK status=pending tool={row['tool']} tenant={row['tenant_id']} reason={row['reason']}")

            # ---- 5. Restart MCP, replay ---------------------------
            step("5. Restart MCP → resolve_draft → ticket created")
            mcp_proc = _spawn_mcp()
            healthy = await _wait_healthy(MCP_BASE)
            if not healthy:
                fail("MCP did not restart")
            ok("MCP back up")

            # The MCPClient's CB now has 1 failure but is still CLOSED
            # (threshold=3), so call_tool should go through directly.
            # resolve_draft uses draft_id as idempotency key so replays
            # are deterministic.
            replay = await client.resolve_draft(draft_id, tenant_id=TENANT)
            if not replay.ok or not replay.data or not replay.data.get("ticket_id"):
                fail(f"replay failed: {replay}")
            ok(f"replay ticket_id={replay.data['ticket_id']} idempotent_replay={replay.idempotent_replay}")

            # ---- 6. PG row now replayed ---------------------------
            step("6. PG row now status='replayed' with result")
            async with pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, false)",
                    TENANT,
                )
                row = await conn.fetchrow(
                    "SELECT status, replay_result, replayed_at "
                    "FROM governance.action_drafts WHERE draft_id = $1",
                    draft_id,
                )
                await conn.execute("SELECT set_config('app.current_tenant', '', false)")
            if row["status"] != "replayed":
                fail(f"expected status=replayed got={row['status']}")
            result_json = row["replay_result"]
            if isinstance(result_json, str):
                result_json = _json.loads(result_json)
            if not result_json.get("ticket_id"):
                fail(f"replay_result missing ticket_id: {result_json}")
            if row["replayed_at"] is None:
                fail("replayed_at should not be NULL")
            ok(f"status=replayed result.ticket_id={result_json['ticket_id']} replayed_at={row['replayed_at']}")

            # ---- 7. Idempotent second resolve returns NOT_PENDING --
            step("7. Second resolve_draft returns DRAFT_NOT_PENDING")
            second = await client.resolve_draft(draft_id, tenant_id=TENANT)
            if second.ok or not second.error or second.error.get("code") != "DRAFT_NOT_PENDING":
                fail(f"expected DRAFT_NOT_PENDING, got: {second}")
            ok(f"second replay rejected: {second.error}")

        finally:
            await pool.close()
    finally:
        if mcp_proc.poll() is None:
            mcp_proc.terminate()
            try:
                mcp_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mcp_proc.kill()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 HITL STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
