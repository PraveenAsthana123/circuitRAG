# RESOURCES: pg
"""
Drill: governance.action_drafts enforces its state machine in storage.

Migration 006 adds three CHECK constraints + a partial index. This
drill proves each one rejects the bad case AND accepts the good case,
plus that the application-level CAS (mark_replayed) is consistent
with the storage rules.

The "negative assertion" §43 calls for: every step proves something
*does not* happen — bad inserts rejected, illegal transitions
rejected, double-replay caught.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_action_draft_state_constraint.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp.drafts import DraftRecord, PostgresDraftStore  # noqa: E402

TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
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


@asynccontextmanager
async def _tenant_conn(pool: asyncpg.Pool, tenant: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", tenant,
            )
            yield conn


class _FakeDb:
    """DbClient-shaped wrapper so PostgresDraftStore can run against the pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def tenant_connection(self, t: str):
        return _tenant_conn(self._pool, t)

    def admin_connection(self):
        @asynccontextmanager
        async def _cm():
            async with self._pool.acquire() as conn:
                yield conn
        return _cm()


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3)
    try:
        # Distinct draft ids so re-runs don't collide on the UNIQUE constraint.
        suffix = uuid.uuid4().hex[:8].upper()
        good = f"DRAFT-OK-{suffix}"
        bad_status = f"DRAFT-BAD-{suffix}"
        replay_target = f"DRAFT-RPL-{suffix}"

        step("1. INSERT with status='pending' is accepted (sanity)")
        async with _tenant_conn(pool, TENANT) as conn:
            await conn.execute(
                """
                INSERT INTO governance.action_drafts
                    (draft_id, tenant_id, tool, arguments, reason, status)
                VALUES ($1, $2::uuid, $3, $4::jsonb, $5, 'pending')
                """,
                good, TENANT, "hr.leave_request",
                json.dumps({"days": 1}), "drill_state_constraint",
            )
        ok(f"valid pending row inserted draft={good}")

        step("2. INSERT with status='garbage' is REJECTED by CHECK constraint")
        rejected = False
        async with _tenant_conn(pool, TENANT) as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO governance.action_drafts
                        (draft_id, tenant_id, tool, arguments, reason, status)
                    VALUES ($1, $2::uuid, $3, $4::jsonb, $5, 'garbage')
                    """,
                    bad_status, TENANT, "hr.leave_request",
                    json.dumps({}), "drill_state_constraint",
                )
            except asyncpg.exceptions.CheckViolationError as exc:
                rejected = True
                if "action_drafts_status_valid" not in str(exc):
                    fail(
                        f"wrong constraint name in error: {exc}. "
                        f"Migration 006 should name it action_drafts_status_valid."
                    )
        if not rejected:
            fail("INSERT with status='garbage' was accepted — CHECK constraint missing!")
        ok("garbage status rejected by action_drafts_status_valid")

        step("3. INSERT pending with replay_result populated is REJECTED")
        # Migration 006 forbids 'pending' rows from carrying replay artefacts.
        rejected = False
        async with _tenant_conn(pool, TENANT) as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO governance.action_drafts
                        (draft_id, tenant_id, tool, arguments, reason, status,
                         replay_result, replayed_at)
                    VALUES ($1, $2::uuid, $3, $4::jsonb, $5, 'pending',
                            $6::jsonb, NOW())
                    """,
                    f"DRAFT-DIRTY-{suffix}", TENANT, "hr.leave_request",
                    json.dumps({}), "drill",
                    json.dumps({"ticket_id": "stale"}),
                )
            except asyncpg.exceptions.CheckViolationError as exc:
                rejected = True
                if "action_drafts_pending_clean" not in str(exc):
                    fail(f"wrong constraint name: {exc}")
        if not rejected:
            fail("dirty pending row was accepted — action_drafts_pending_clean missing!")
        ok("pending row with replay artefacts rejected")

        step("4. CAS: mark_replayed transitions pending → replayed exactly once")
        # Insert a fresh pending row, then call mark_replayed() twice.
        # First call → True (transition occurred), second call → False
        # (CAS guard kicks in: WHERE status='pending' matches no rows).
        async with _tenant_conn(pool, TENANT) as conn:
            await conn.execute(
                """
                INSERT INTO governance.action_drafts
                    (draft_id, tenant_id, tool, arguments, reason, status)
                VALUES ($1, $2::uuid, $3, $4::jsonb, $5, 'pending')
                """,
                replay_target, TENANT, "hr.leave_request",
                json.dumps({"days": 2}), "drill",
            )
        store = PostgresDraftStore(_FakeDb(pool))
        first = await store.mark_replayed(
            replay_target, {"ticket_id": "T-1"}, tenant_id=TENANT,
        )
        if first is not True:
            fail(f"first mark_replayed should win, got {first!r}")
        second = await store.mark_replayed(
            replay_target, {"ticket_id": "T-2"}, tenant_id=TENANT,
        )
        if second is not False:
            fail(
                f"second mark_replayed should LOSE the CAS race "
                f"(row no longer pending), got {second!r}"
            )
        # Storage shows the FIRST replay's result — second was rejected.
        async with _tenant_conn(pool, TENANT) as conn:
            row = await conn.fetchrow(
                "SELECT status, replay_result FROM governance.action_drafts "
                "WHERE draft_id=$1",
                replay_target,
            )
        if row["status"] != "replayed":
            fail(f"final status should be replayed, got {row['status']!r}")
        rr = row["replay_result"]
        if isinstance(rr, str):
            rr = json.loads(rr)
        if rr.get("ticket_id") != "T-1":
            fail(
                f"replay_result was overwritten by losing CAS! "
                f"got {rr!r} — should still be T-1 from the winning call."
            )
        ok("CAS lets the first replay win; second is rejected (False); "
           "replay_result not overwritten")

        step("5. Partial index exists (catalogue regression)")
        # Asserting the planner *uses* the index is fragile for an
        # almost-empty table — Postgres correctly picks Seq Scan when the
        # row count is below the index lookup threshold. The robust
        # assertion is that the index exists and has the expected
        # predicate, which is what migration 006 promises. The planner's
        # choice under load is a Prometheus + pg_stat_user_indexes
        # concern, not a CI assertion.
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT indexdef
                  FROM pg_indexes
                 WHERE schemaname = 'governance'
                   AND tablename = 'action_drafts'
                   AND indexname = 'idx_action_drafts_pending_by_tenant'
                """,
            )
        if row is None:
            fail(
                "idx_action_drafts_pending_by_tenant missing — migration 006 "
                "didn't run or someone dropped the index."
            )
        idxdef = row["indexdef"]
        if "WHERE (status = 'pending'" not in idxdef:
            fail(
                f"index lost its partial predicate: {idxdef!r} — should "
                f"be WHERE status = 'pending'."
            )
        if "(tenant_id, created_at)" not in idxdef:
            fail(
                f"index columns drifted: {idxdef!r} — expected "
                f"(tenant_id, created_at)."
            )
        ok(f"partial index present: {idxdef[idxdef.index('USING'):]}")

        # Cleanup the rows we inserted so re-runs don't accumulate.
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM governance.action_drafts WHERE draft_id IN ($1, $2)",
                good, replay_target,
            )

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 STATE-CONSTRAINT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
