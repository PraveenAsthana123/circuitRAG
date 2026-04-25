# RESOURCES: mcp_hr inference pg
"""
Drill: documind_draft_replay_total{namespace, outcome} counts what
the autonomous worker does — exposed for dashboards + alerting.

The worker had a per-instance ``self.stats`` dict (process-local
introspection) but no graphable signal. Production operators
needed:
  * "How many drafts is the worker actually closing?"
  * "Is one namespace's CB stuck blocking the worker?"
  * "Is the worker hitting systematic errors?"

This drill exercises three distinct outcome paths and verifies
each increments the right Counter label exactly once. Each step
is a negative assertion — proves a SPECIFIC label moved AND
unrelated labels did NOT.

Flow:
 1. Baseline: read /metrics, snapshot the documind_draft_replay_total
    series for hr.
 2. Trigger ``replayed`` outcome — pending draft + worker.sweep_once()
    against healthy MCP. Counter for {namespace="hr", outcome="replayed"}
    must be exactly +1.
 3. Trigger ``no_server`` outcome — submit a draft for a namespace
    with no client (e.g. tool="UNKNOWN.ghost"). Counter for
    {namespace="UNKNOWN", outcome="no_server"} must be +1, replayed
    counter unchanged.
 4. Trigger ``cb_wait`` outcome — open the worker's CB by recording
    failures, then sweep with a pending draft. Counter for
    {namespace="hr", outcome="cb_wait"} must be +1.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_worker_metrics.py
"""
from __future__ import annotations

import asyncio
import os
import re
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
from mcp.drafts import DraftRecord  # noqa: E402
from app.workers.draft_replay import (  # type: ignore  # noqa: E402
    DraftReplayWorker,
    _draft_replay_total,
)

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
METRICS = os.getenv("METRICS_URL", "http://127.0.0.1:9466/metrics")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
# Per-drill UUID tenant. The shared TENANT used by other drills
# accumulates pending drafts across runs — a worker sweep would
# touch ALL of them and inflate per-outcome counters (12 leftover
# drafts under an open CB → +12 cb_wait, not +1). A fresh tenant
# guarantees the universe of pending drafts is exactly what THIS
# drill seeded.
TENANT = os.getenv("TENANT_ID") or str(uuid.uuid4())
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


def _read_local_counter(namespace: str, outcome: str) -> float:
    """In-process counter snapshot — used because the drill runs the
    worker in-process and exercises the same Counter the inference-svc
    /metrics scrapes from. Keeps the test fast + deterministic; we
    don't need to round-trip through inference-svc to scrape."""
    if _draft_replay_total is None:
        return 0.0
    sample = _draft_replay_total.labels(namespace=namespace, outcome=outcome)
    return sample._value.get()  # noqa: SLF001 — internal but stable


class _FakeDb:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def tenant_connection(self, t: str):
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


async def _seed_pending_draft(
    pool: asyncpg.Pool, *, tool: str, draft_id: str,
) -> None:
    """Insert a synthetic pending draft directly so we don't depend on
    agent/ask routing — the metrics drill cares about the worker's
    behaviour given a pending draft, not how the draft got there."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            await conn.execute(
                """
                INSERT INTO governance.action_drafts
                    (draft_id, tenant_id, tool, arguments, reason, status)
                VALUES ($1, $2::uuid, $3, $4::jsonb, $5, 'pending')
                """,
                draft_id, TENANT, tool,
                '{"employee_id": "E42", "days": 1, "reason": "drill-metrics"}',
                "drill_worker_metrics",
            )


async def _delete_drafts(pool: asyncpg.Pool, prefix: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM governance.action_drafts WHERE draft_id LIKE $1",
            f"{prefix}%",
        )


async def main() -> None:
    suffix = uuid.uuid4().hex[:8].upper()
    D_REPLAYED = f"DRAFT-METR-OK-{suffix}"
    D_NOSERVER = f"DRAFT-METR-NS-{suffix}"
    D_CBWAIT = f"DRAFT-METR-CB-{suffix}"
    SVC_TOK = _mint(["hr:read", "hr:write"], sub="service:metrics-drill")

    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3)
    try:
        await _delete_drafts(pool, "DRAFT-METR-")

        step("1. Baseline counter snapshot")
        b_replayed = _read_local_counter("hr", "replayed")
        b_no_server = _read_local_counter("UNKNOWN", "no_server")
        b_cb_wait = _read_local_counter("hr", "cb_wait")
        ok(
            f"baseline replayed={b_replayed} no_server[UNKNOWN]={b_no_server} "
            f"cb_wait[hr]={b_cb_wait}"
        )

        step("2. ``replayed`` outcome — counter +1 for {hr, replayed}")
        # Confirm MCP is reachable for the success case.
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{MCP_BASE}/health")
            if r.status_code != 200:
                fail("MCP must be healthy for step 2 — start mcp/server_hr.py")
        await _seed_pending_draft(pool, tool="hr.leave_request", draft_id=D_REPLAYED)
        client = MCPClient(
            base_url=MCP_BASE,
            draft_store=PostgresDraftStore(_FakeDb(pool)),
            recovery_timeout=1.0,
        )
        worker = DraftReplayWorker(
            mcp_clients={"hr": client},
            tenant_ids=[TENANT],
            interval_s=1, per_draft_backoff_s=1,
            service_auth_token=SVC_TOK,
        )
        await worker.sweep_once()
        if _read_local_counter("hr", "replayed") - b_replayed != 1:
            fail(
                f"hr/replayed counter delta != 1: "
                f"got {_read_local_counter('hr', 'replayed') - b_replayed}"
            )
        # Negative: cb_wait did NOT move on a healthy-CB success.
        if _read_local_counter("hr", "cb_wait") - b_cb_wait != 0:
            fail("cb_wait moved on a successful replay — wrong label")
        await client.close()
        ok(f"hr/replayed +1; hr/cb_wait unchanged (label isolation)")

        step("3. ``no_server`` outcome — counter +1 for {UNKNOWN, no_server}")
        # Insert a draft for an unknown tool namespace. The worker's
        # _client_for() returns None for "UNKNOWN" → no_server bump.
        await _seed_pending_draft(pool, tool="UNKNOWN.ghost", draft_id=D_NOSERVER)
        client2 = MCPClient(
            base_url=MCP_BASE,
            draft_store=PostgresDraftStore(_FakeDb(pool)),
            recovery_timeout=1.0,
        )
        worker2 = DraftReplayWorker(
            mcp_clients={"hr": client2},  # NO "UNKNOWN" client — that's the test
            tenant_ids=[TENANT],
            interval_s=1, per_draft_backoff_s=1,
            service_auth_token=SVC_TOK,
        )
        # The previous draft from step 2 is now status='replayed' so
        # list_pending only returns the new ghost-draft.
        await worker2.sweep_once()
        if _read_local_counter("UNKNOWN", "no_server") - b_no_server != 1:
            fail(
                f"UNKNOWN/no_server delta != 1: "
                f"got {_read_local_counter('UNKNOWN', 'no_server') - b_no_server}"
            )
        # Negative: hr/replayed did NOT increment (we shouldn't have
        # routed an UNKNOWN tool to hr).
        if _read_local_counter("hr", "replayed") - b_replayed != 1:
            fail(
                "hr/replayed moved on UNKNOWN draft — namespace routing broken!"
            )
        await client2.close()
        ok("UNKNOWN/no_server +1; hr/replayed unchanged (no cross-routing)")

        step("4. ``cb_wait`` outcome — counter +1 for {hr, cb_wait}")
        # Pre-trip the CB by directly recording failures. Then sweep —
        # worker should fast-skip with cb_wait label (not call MCP).
        await _seed_pending_draft(pool, tool="hr.leave_request", draft_id=D_CBWAIT)
        client3 = MCPClient(
            base_url=MCP_BASE,
            draft_store=PostgresDraftStore(_FakeDb(pool)),
            recovery_timeout=300.0,  # don't let it auto-close mid-test
            failure_threshold=1,
        )
        client3._breaker.record_failure()
        if client3.cb_state != "open":
            fail(f"failed to trip CB; state={client3.cb_state}")
        worker3 = DraftReplayWorker(
            mcp_clients={"hr": client3},
            tenant_ids=[TENANT],
            interval_s=1, per_draft_backoff_s=1,
            service_auth_token=SVC_TOK,
        )
        await worker3.sweep_once()
        if _read_local_counter("hr", "cb_wait") - b_cb_wait != 1:
            fail(
                f"hr/cb_wait delta != 1: "
                f"got {_read_local_counter('hr', 'cb_wait') - b_cb_wait}"
            )
        # Negative: replayed did NOT increment (CB blocked the call).
        if _read_local_counter("hr", "replayed") - b_replayed != 1:
            fail("hr/replayed moved on a CB-blocked draft — fast-skip broken!")
        await client3.close()
        ok("hr/cb_wait +1; hr/replayed unchanged (CB blocked the call)")

        # Cleanup
        await _delete_drafts(pool, "DRAFT-METR-")

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 WORKER-METRICS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
