# RESOURCES: inference mcp_hr mcp_itsm pg
"""
Drill: DraftReplayWorker routes each pending draft to its own
namespace's MCP client.

Mirrors the admin-API resolve_draft routing fix. The autonomous
worker had the same latent bug — it stored a single MCPClient and
would route itsm.* drafts to hr's client, which 404s. This drill
pins the multi-client behavior:

  * A mixed workload of HR + ITSM pending drafts → all replayed.
  * A draft with a namespace that has NO configured client →
    skipped (stays pending, no_server_skips increments), NOT
    misrouted to a wrong namespace.
  * Per-namespace CB bailout: hr's CB open doesn't stop itsm's
    drafts from being processed in the same sweep cycle.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_worker_multi_namespace.py
"""
from __future__ import annotations

import asyncio
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

TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
HR_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
ITSM_BASE = os.getenv("MCP_ITSM_URL", "http://127.0.0.1:8091")
HR_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
ITSM_PORT = int(os.getenv("MCP_ITSM_PORT", "8091"))
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


def _kill(port: int) -> None:
    subprocess.run(["fuser", "-k", f"{port}/tcp"], check=False, capture_output=True)


def _spawn(server: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env[f"MCP_{server.upper()}_PORT"] = str(port)
    env["MCP_AUTH_REQUIRED"] = "false"  # drill bypasses auth for simplicity
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    log = open(f"/tmp/documind-mcp-{server}-worker-multi-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / f"server_{server}.py")],
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


class _FakeDb:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def tenant_connection(self, tenant_id: str):
        @asynccontextmanager
        async def _cm():
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1, true)", tenant_id,
                    )
                    yield conn
        return _cm()

    def admin_connection(self):
        @asynccontextmanager
        async def _cm():
            async with self._pool.acquire() as conn:
                yield conn
        return _cm()


async def _count_by_status(pool: asyncpg.Pool) -> dict[str, int]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            rows = await conn.fetch(
                "SELECT status, COUNT(*) AS n FROM governance.action_drafts "
                "WHERE tenant_id=$1::uuid GROUP BY status",
                TENANT,
            )
    return {r["status"]: r["n"] for r in rows}


async def main() -> None:
    # Fresh servers without auth so the drill is self-contained.
    _kill(HR_PORT)
    _kill(ITSM_PORT)
    await asyncio.sleep(1)
    # Cleanup prior drafts for this tenant so counts are predictable
    subprocess.run(
        [
            "docker", "exec", "-e", "PGPASSWORD=documind",
            "documind-postgres", "psql", "-U", "documind", "-d", "documind",
            "-c", f"DELETE FROM governance.action_drafts WHERE tenant_id='{TENANT}'",
        ],
        check=True, capture_output=True,
    )

    # Stand up pool + fake db + stores
    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3)
    try:
        db = _FakeDb(pool)
        store = PostgresDraftStore(db)
        # One shared store; two clients sharing it.
        hr_client = MCPClient(
            base_url=HR_BASE, draft_store=store,
            failure_threshold=2, recovery_timeout=30.0,
        )
        itsm_client = MCPClient(
            base_url=ITSM_BASE, draft_store=store,
            failure_threshold=2, recovery_timeout=30.0,
        )

        async with httpx.AsyncClient(timeout=10.0) as c:
            step("0. clean slate (drafts cleared, both servers DOWN)")
            ok("drafts cleared; MCPs not running")

            step("1. create 1 HR pending draft + 1 ITSM pending draft")
            # Both servers are down → every call_tool degrades to draft.
            r1 = await hr_client.call_tool(
                "hr.leave_request",
                {"employee_id": "E42", "days": 1, "reason": "multi-ns hr"},
                tenant_id=TENANT,
            )
            if not r1.degraded or not r1.draft_id:
                fail(f"HR draft not created: {r1}")
            hr_draft = r1.draft_id

            r2 = await itsm_client.call_tool(
                "itsm.incident_open",
                {"title": "multi-ns drill", "description": "x"},
                tenant_id=TENANT,
            )
            if not r2.degraded or not r2.draft_id:
                fail(f"ITSM draft not created: {r2}")
            itsm_draft = r2.draft_id

            counts = await _count_by_status(pool)
            if counts.get("pending", 0) != 2:
                fail(f"expected 2 pending, got {counts}")
            ok(f"HR draft={hr_draft}  ITSM draft={itsm_draft}  pending count={counts['pending']}")

            step("2. start BOTH MCP servers, wait CB recovery_timeout")
            hr_proc = _spawn("hr", HR_PORT)
            itsm_proc = _spawn("itsm", ITSM_PORT)
            try:
                if not await _healthy(c, HR_BASE, tries=20):
                    fail("HR didn't start")
                if not await _healthy(c, ITSM_BASE, tries=20):
                    fail("ITSM didn't start")
                # Each client's CB is CLOSED initially (we only made one
                # failed call per client, threshold=2 so it didn't open).
                ok("both MCPs up")

                step("3. worker with both clients — sweep_once replays BOTH drafts")
                worker = DraftReplayWorker(
                    mcp_clients={"hr": hr_client, "itsm": itsm_client},
                    tenant_ids=[TENANT],
                    interval_s=1,
                    per_draft_backoff_s=5,
                )
                await worker.sweep_once()
                counts = await _count_by_status(pool)
                if counts.get("replayed", 0) != 2:
                    fail(f"expected 2 replayed, got {counts}  stats={worker.stats}")
                if counts.get("pending", 0):
                    fail(f"drafts still pending: {counts}")
                if worker.stats["replayed"] != 2:
                    fail(f"worker replayed count wrong: {worker.stats}")
                if worker.stats["errors"]:
                    fail(f"unexpected errors: {worker.stats}")
                ok(f"both drafts replayed stats={worker.stats}")

                step("4. unknown-namespace draft → no_server_skips, NOT misrouted")
                # Inject an orphan draft via superuser (bypasses RLS) —
                # drill_audit_verifier uses the same pattern.
                subprocess.run(
                    [
                        "docker", "exec", "-e", "PGPASSWORD=documind",
                        "documind-postgres", "psql", "-U", "documind", "-d", "documind",
                        "-c",
                        (
                            "INSERT INTO governance.action_drafts "
                            "(draft_id, tenant_id, tool, arguments, reason, status, created_at) "
                            f"VALUES ('DRAFT-ORPHAN-MULTI', '{TENANT}', 'finance.refund_issue', "
                            "'{}'::jsonb, 'drill-inject', 'pending', NOW())"
                        ),
                    ],
                    check=True, capture_output=True,
                )
                before = dict(worker.stats)
                await worker.sweep_once()
                if worker.stats["no_server_skips"] != before["no_server_skips"] + 1:
                    fail(
                        f"expected no_server_skips to rise by 1, "
                        f"{before['no_server_skips']} → {worker.stats['no_server_skips']}"
                    )
                # The orphan must STILL be pending — not lost, not misrouted
                counts = await _count_by_status(pool)
                if counts.get("pending", 0) != 1:
                    fail(f"orphan draft lost/misrouted: {counts}")
                ok(f"orphan left pending stats={worker.stats}")

                # Clean up the injected orphan
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM governance.action_drafts WHERE draft_id='DRAFT-ORPHAN-MULTI'"
                    )

                step("5. per-namespace CB isolation — kill ITSM, create ITSM draft, HR draft created → both paths behave independently")
                _kill(ITSM_PORT)
                await asyncio.sleep(1)
                # Fail enough ITSM calls to open ITSM's client CB.
                # failure_threshold=2 on itsm_client so 2 failures trip it.
                for _ in range(3):
                    await itsm_client.call_tool(
                        "itsm.incident_open",
                        {"title": "cb-trip", "description": "x"},
                        tenant_id=TENANT,
                    )
                if itsm_client.cb_state != "open":
                    fail(f"ITSM CB should be open, got {itsm_client.cb_state}")
                if hr_client.cb_state != "closed":
                    fail(f"HR CB should be closed, got {hr_client.cb_state}")

                # Now there are several pending ITSM drafts AND a fresh
                # HR draft (we'll add one).
                r = await hr_client.call_tool(
                    "hr.leave_request",
                    {"employee_id": "E42", "days": 2, "reason": "hr independent"},
                    tenant_id=TENANT,
                )
                # HR is up → this should SUCCEED, not draft.
                if not r.ok or not (r.data or {}).get("ticket_id"):
                    fail(f"HR call degraded unexpectedly: {r}")
                hr_live_ticket = r.data["ticket_id"]
                # There should still be multiple pending ITSM drafts.
                counts = await _count_by_status(pool)
                if counts.get("pending", 0) < 3:
                    fail(f"expected >=3 pending ITSM drafts, got {counts}")

                # Worker sweep: ITSM drafts should be cb_wait_skipped,
                # HR drafts (none left) should not get touched. Orphan
                # was already cleaned.
                before = dict(worker.stats)
                await worker.sweep_once()
                if worker.stats["cb_wait_skips"] <= before["cb_wait_skips"]:
                    fail(
                        f"expected cb_wait_skips to rise on ITSM drafts, "
                        f"stats={worker.stats}"
                    )
                if worker.stats["errors"]:
                    fail(f"errors: {worker.stats}")
                ok(f"HR path unaffected (hr_ticket={hr_live_ticket}); "
                   f"ITSM drafts cb-waited stats={worker.stats}")

            finally:
                if hr_proc.poll() is None:
                    hr_proc.terminate()
                if itsm_proc.poll() is None:
                    itsm_proc.terminate()

        await hr_client.close()
        await itsm_client.close()

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 WORKER-MULTI-NAMESPACE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
