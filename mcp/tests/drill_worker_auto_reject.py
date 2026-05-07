# RESOURCES: mcp_hr pg
"""
Drill: worker auto-rejects drafts after N consecutive failures.

The bug this commit closes: a draft with malformed arguments
(missing employee_id, expired tool target, schema-violating payload)
gets ``ok=false, error.code=internal_error`` from MCP on EVERY
sweep. Pre-this-commit, the worker just logged and kept retrying
every backoff window. Forever. The audit log filled with
mcp_draft.created and the same error every minute.

Now: the worker tracks a per-draft consecutive-failure counter.
After ``auto_reject_threshold`` failures, the draft auto-transitions
to 'rejected' with actor_type="worker", actor_id=<service sub>, and
a reason that names the threshold and last error.

Each step is a negative assertion §43-style:
 1. Seed a malformed draft (no employee_id) + sweep once →
    {hr,failed} +1; draft STAYS pending; counter=1, NOT auto-rejected.
 2. Sweep N-1 more times → counter reaches threshold; draft STILL
    pending until the threshold-hit cycle.
 3. Sweep one more → auto-reject fires; {hr,auto_rejected} +1;
    draft transitions to 'rejected'; audit row emitted with
    actor_type='worker' and reason mentioning threshold.
 4. Subsequent sweep → worker does NOT pick up the rejected draft
    ({hr,failed} unchanged; the row is now invisible to list_pending).
 5. Threshold=0 disables auto-reject (would-be auto-rejected draft
    stays pending forever).

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_worker_auto_reject.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

from app.workers.draft_replay import (  # type: ignore  # noqa: E402
    DraftReplayWorker,
    _draft_replay_total,
)
from documind_core.audit import AuditWriter  # noqa: E402

from mcp import MCPClient, PostgresDraftStore  # noqa: E402

MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
TENANT = os.getenv("TENANT_ID") or str(uuid.uuid4())  # per-drill isolation
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


SVC_SUB = "service:auto-reject-drill"


def _mint(roles: list[str], sub: str = SVC_SUB) -> str:
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
    if _draft_replay_total is None:
        return 0.0
    return _draft_replay_total.labels(
        namespace=namespace, outcome=outcome,
    )._value.get()  # noqa: SLF001


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


async def _seed_malformed_draft(pool: asyncpg.Pool, draft_id: str) -> None:
    """Insert a draft whose arguments will trigger MCP's KeyError on
    employee_id — a stand-in for any permanent-failure-mode payload."""
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
                draft_id, TENANT, "hr.leave_request",
                # Note: NO employee_id. MCP's hr.leave_request handler
                # does ``req.arguments["employee_id"]`` → KeyError →
                # 200 with ok=False, code=internal_error.
                json.dumps({"days": 1, "reason": "drill: malformed"}),
                "drill_auto_reject",
            )


async def _draft_status(pool: asyncpg.Pool, draft_id: str) -> str | None:
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


async def _audit_for(
    pool: asyncpg.Pool, draft_id: str, action: str,
) -> dict | None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            row = await conn.fetchrow(
                """
                SELECT actor_type, actor_id, action, details
                  FROM governance.audit_log
                 WHERE tenant_id = $1::uuid
                   AND action = $2
                   AND details->>'draft_id' = $3
                 ORDER BY timestamp DESC, id DESC
                 LIMIT 1
                """,
                TENANT, action, draft_id,
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


def _new_worker(client, *, threshold: int) -> DraftReplayWorker:
    return DraftReplayWorker(
        mcp_clients={"hr": client},
        tenant_ids=[TENANT],
        interval_s=1,
        # Worker enforces max(1, per_draft_backoff_s), so the floor is
        # 1s. Tight sweep_once loops in this drill must sleep at least
        # 1.1s between calls or the per-draft backoff filter swallows
        # them. Alternative: clear ``_last_attempt`` between sweeps;
        # we sleep for clarity.
        per_draft_backoff_s=1,
        service_auth_token=_mint(["hr:read", "hr:write"]),
        service_actor_id=SVC_SUB,
        auto_reject_threshold=threshold,
    )


async def _sweep_n(worker: DraftReplayWorker, n: int) -> None:
    """Sweep ``n`` times honouring the worker's per-draft backoff."""
    for i in range(n):
        if i > 0:
            await asyncio.sleep(1.1)  # one tick past the backoff floor
        await worker.sweep_once()


async def main() -> None:
    suffix = uuid.uuid4().hex[:8].upper()
    DRAFT = f"DRAFT-AUTOREJ-{suffix}"
    DRAFT_DISABLED = f"DRAFT-AUTOREJ-DIS-{suffix}"
    THRESHOLD = 3  # use a small N so the drill is fast

    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3)
    try:
        # Cleanup leftovers from prior runs (per-drill UUID tenant should
        # already be isolated, but defensive).
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM governance.action_drafts WHERE draft_id LIKE $1",
                "DRAFT-AUTOREJ-%",
            )

        b_failed = _read_local_counter("hr", "failed")
        b_autorej = _read_local_counter("hr", "auto_rejected")

        step("1. Seed malformed draft + first sweep → failed +1, still pending")
        await _seed_malformed_draft(pool, DRAFT)
        client = MCPClient(
            base_url=MCP_BASE,
            draft_store=PostgresDraftStore(_FakeDb(pool)),
            audit_log=AuditWriter(db_client=_FakeDb(pool), service="auto-reject-drill"),
            recovery_timeout=1.0,
        )
        worker = _new_worker(client, threshold=THRESHOLD)
        await worker.sweep_once()
        if _read_local_counter("hr", "failed") - b_failed != 1:
            fail(
                f"first sweep should bump failed by 1; got delta="
                f"{_read_local_counter('hr', 'failed') - b_failed}"
            )
        if _read_local_counter("hr", "auto_rejected") - b_autorej != 0:
            fail("auto_rejected fired before threshold!")
        if await _draft_status(pool, DRAFT) != "pending":
            fail("draft should still be pending after first failure")
        if worker._consecutive_failures.get(DRAFT) != 1:  # noqa: SLF001
            fail(
                f"per-draft counter should be 1, got "
                f"{worker._consecutive_failures.get(DRAFT)!r}"
            )
        ok(f"first sweep: failed +1, draft pending, counter=1 (under threshold {THRESHOLD})")

        step(f"2. Sweep {THRESHOLD - 2} more times → counter approaches threshold but does NOT trip yet")
        # Honour the 1s per-draft backoff floor between sweeps.
        for i in range(THRESHOLD - 2):
            await asyncio.sleep(1.1)
            await worker.sweep_once()
        # We've now done THRESHOLD-1 total sweeps (1 from step 1, plus this loop).
        if worker._consecutive_failures.get(DRAFT) != THRESHOLD - 1:  # noqa: SLF001
            fail(
                f"expected counter={THRESHOLD - 1}, got "
                f"{worker._consecutive_failures.get(DRAFT)!r}"
            )
        if _read_local_counter("hr", "auto_rejected") - b_autorej != 0:
            fail("auto_rejected fired before threshold reached!")
        if await _draft_status(pool, DRAFT) != "pending":
            fail("draft should still be pending below threshold")
        ok(f"counter={THRESHOLD - 1} of {THRESHOLD}; draft still pending; auto-reject NOT yet triggered")

        step(f"3. {THRESHOLD}-th sweep → auto-reject fires, draft → 'rejected', audit row written")
        await asyncio.sleep(1.1)
        await worker.sweep_once()
        # Threshold reached on this sweep; auto-reject should have run.
        if _read_local_counter("hr", "auto_rejected") - b_autorej != 1:
            fail(
                f"auto_rejected delta != 1: got "
                f"{_read_local_counter('hr', 'auto_rejected') - b_autorej}"
            )
        post_status = await _draft_status(pool, DRAFT)
        if post_status != "rejected":
            fail(f"expected status=rejected, got {post_status!r}")
        # Audit row check — actor_type=worker, actor_id=SVC_SUB, reason
        # mentions threshold.
        audit = await _audit_for(pool, DRAFT, "mcp_draft.rejected")
        if audit is None:
            fail("no mcp_draft.rejected audit row written for auto-reject")
        if audit["actor_type"] != "worker":
            fail(
                f"actor_type should be 'worker' for auto-reject, got "
                f"{audit['actor_type']!r}"
            )
        if audit["actor_id"] != SVC_SUB:
            fail(
                f"actor_id should be service sub {SVC_SUB!r}, got "
                f"{audit['actor_id']!r}"
            )
        reason = audit["details"].get("reason") or ""
        if "auto-rejected" not in reason or "consecutive failures" not in reason:
            fail(f"reason missing auto-reject markers: {reason!r}")
        # Per-draft counter should be cleaned up.
        if DRAFT in worker._consecutive_failures:  # noqa: SLF001
            fail(
                f"_consecutive_failures still carries {DRAFT} after auto-reject — "
                f"unbounded growth risk"
            )
        ok("auto_rejected +1; status=rejected; audit actor_type=worker reason mentions threshold")

        step("4. Subsequent sweep does NOT pick up the rejected draft")
        f_before = _read_local_counter("hr", "failed")
        await asyncio.sleep(1.1)
        await worker.sweep_once()
        if _read_local_counter("hr", "failed") - f_before != 0:
            fail(
                f"worker re-touched a rejected draft (failed delta = "
                f"{_read_local_counter('hr', 'failed') - f_before}). "
                f"list_pending must filter status='pending'."
            )
        ok("rejected draft is invisible to next sweep (list_pending filter intact)")

        step("5. threshold=0 disables auto-reject — failed sweeps don't auto-reject")
        await _seed_malformed_draft(pool, DRAFT_DISABLED)
        f_before = _read_local_counter("hr", "failed")
        a_before = _read_local_counter("hr", "auto_rejected")
        worker_disabled = _new_worker(client, threshold=0)
        # Sweep many more than the previous threshold — should NEVER auto-reject.
        # Honour backoff between sweeps.
        for i in range(THRESHOLD + 2):
            if i > 0:
                await asyncio.sleep(1.1)
            await worker_disabled.sweep_once()
        if _read_local_counter("hr", "auto_rejected") - a_before != 0:
            fail(
                "threshold=0 should disable auto-reject, but auto_rejected counter moved!"
            )
        if await _draft_status(pool, DRAFT_DISABLED) != "pending":
            fail("draft auto-rejected despite threshold=0")
        # And we did emit failed for each attempt.
        if _read_local_counter("hr", "failed") - f_before != THRESHOLD + 2:
            fail(
                f"expected {THRESHOLD + 2} failed bumps, got "
                f"{_read_local_counter('hr', 'failed') - f_before}"
            )
        ok(f"threshold=0: {THRESHOLD + 2} failed bumps, 0 auto_rejects, draft still pending")

        await client.close()

        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM governance.action_drafts WHERE draft_id LIKE $1",
                "DRAFT-AUTOREJ-%",
            )

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 AUTO-REJECT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
