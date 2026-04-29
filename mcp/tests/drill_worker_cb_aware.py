# RESOURCES: inference mcp_hr pg
"""
Drill: DraftReplayWorker skips cycles when the MCP CB is OPEN.

Companion to drill_worker.py. Tight focus: prove that with
skip_when_cb_open=True (default), a sweep whose MCP client reports
cb_state='open' bails out BEFORE touching Postgres.

Flow:
 1. Clean slate + wire MCPClient with failure_threshold=2 so it
    opens on 2 degrades, and skip_when_cb_open=True on the worker.
 2. MCP is already dead on drill entry; call_tool twice to persist
    two drafts AND trip the CB (failures=2 → OPEN).
 3. Confirm client.cb_state == 'open'.
 4. worker.sweep_once() — expect stats.cb_wait_skips++ and
    stats.replayed stays 0. Crucially, NO list_pending_drafts call
    happens (PG isn't read) — we assert by wrapping the store's
    list_pending in a counter.
 5. Flip skip_when_cb_open=False on a second worker; sweep_once()
    this time proceeds (list_pending IS called) but the resolve
    call degrades, incrementing degraded_bailouts.

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_worker_cb_aware.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

from mcp import MCPClient, PostgresDraftStore  # noqa: E402
from app.workers.draft_replay import DraftReplayWorker  # type: ignore  # noqa: E402

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

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


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


class _CountingStore:
    """Wraps a PostgresDraftStore and counts list_pending calls."""

    def __init__(self, inner: PostgresDraftStore) -> None:
        self._inner = inner
        self.list_pending_calls = 0

    async def save(self, draft):
        await self._inner.save(draft)

    async def get(self, draft_id, tenant_id=None):
        return await self._inner.get(draft_id, tenant_id)

    async def list_pending(self, tenant_id=None):
        self.list_pending_calls += 1
        return await self._inner.list_pending(tenant_id)

    async def mark_replayed(self, draft_id, result, tenant_id=None):
        await self._inner.mark_replayed(draft_id, result, tenant_id)


async def main() -> None:
    step("0. clean slate")
    subprocess.run(
        [
            "docker", "exec", "-e", "PGPASSWORD=documind",
            "documind-postgres", "psql", "-U", "documind", "-d", "documind",
            "-c", f"DELETE FROM governance.action_drafts WHERE tenant_id='{TENANT}'",
        ],
        check=True, capture_output=True,
    )
    _kill_mcp()
    await asyncio.sleep(1)
    ok("drafts cleared + MCP dead")

    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3)
    try:
        db = _FakeDb(pool)
        inner_store = PostgresDraftStore(db)
        counting = _CountingStore(inner_store)

        step("1. wire MCPClient(threshold=2) + CB-aware worker")
        # Low threshold so 2 connect errors trip the CB immediately.
        client = MCPClient(
            base_url=MCP_BASE,
            draft_store=counting,
            failure_threshold=2,
            recovery_timeout=60.0,   # stay OPEN long enough for the drill
        )
        worker = DraftReplayWorker(
            mcp_client=client,
            tenant_ids=[TENANT],
            interval_s=1,
            per_draft_backoff_s=5,
            skip_when_cb_open=True,
        )
        ok("client + store + worker wired (skip_when_cb_open=True)")

        step("2. 2 calls while MCP is dead → trip the CB")
        for i in (1, 2):
            r = await client.call_tool(
                "hr.leave_request",
                {"employee_id": "E42", "days": i, "reason": f"cb-aware drill {i}"},
                tenant_id=TENANT,
            )
            if not r.degraded:
                fail(f"call {i} did not degrade")
        if client.cb_state != "open":
            fail(f"CB should be OPEN after 2 failures, got {client.cb_state}")
        ok(f"cb_state={client.cb_state}")

        step("3. worker.sweep_once() — CB OPEN → skip, list_pending NOT called")
        list_before = counting.list_pending_calls
        await worker.sweep_once()
        list_after = counting.list_pending_calls
        if list_after != list_before:
            fail(
                f"expected list_pending NOT called, but calls went "
                f"{list_before} → {list_after}",
            )
        if worker.stats["cb_wait_skips"] != 1:
            fail(f"expected cb_wait_skips=1 got {worker.stats}")
        if worker.stats["replayed"] != 0:
            fail(f"expected replayed=0 got {worker.stats}")
        ok(f"list_pending untouched (still {list_after}) stats={worker.stats}")

        step("4. second worker with skip_when_cb_open=False — list IS called, degraded_bailout fires")
        worker2 = DraftReplayWorker(
            mcp_client=client,
            tenant_ids=[TENANT],
            interval_s=1,
            per_draft_backoff_s=5,
            skip_when_cb_open=False,
        )
        list_before = counting.list_pending_calls
        await worker2.sweep_once()
        list_after = counting.list_pending_calls
        if list_after <= list_before:
            fail(
                f"expected list_pending to be called; went "
                f"{list_before} → {list_after}",
            )
        if worker2.stats["degraded_bailouts"] != 1:
            fail(f"expected 1 degraded_bailout got {worker2.stats}")
        if worker2.stats["cb_wait_skips"] != 0:
            fail(f"skip_when_cb_open=False should never cb-wait: {worker2.stats}")
        ok(f"list_pending called ({list_before} → {list_after}) stats={worker2.stats}")

        await client.close()
    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 CB-AWARE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
