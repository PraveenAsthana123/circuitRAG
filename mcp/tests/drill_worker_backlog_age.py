# RESOURCES: pg
"""
Drill: documind_draft_pending_age_seconds{namespace} gauge reflects
the oldest pending draft per namespace and resets to 0 when the
queue drains.

The catalog gap (cited in 3 separate gap-reviews — rag-data-layers,
scheduling-ontology, AIOps): the worker had a per-outcome counter
but no oldest-pending-draft gauge. Drafts hitting cb_wait or
skipped_backoff repeatedly never increment the consecutive-failure
counter (so they don't auto-reject) but also never replay — the
slow-leak case. Without this gauge an operator can't see the
queue ageing.

Each step is a negative-assertion §43-style:
 1. No drafts → gauge is 0 for both namespaces. NEGATIVE: empty
    queue must NOT report a stale max age from earlier runs.
 2. Plant one ``hr.*`` draft with created_at = NOW - 120s. Run
    sweep. Gauge for ``hr`` ≈ 120s; gauge for ``itsm`` stays 0.
    NEGATIVE: the wrong namespace must NOT get the age.
 3. Plant a SECOND ``hr.*`` draft, older (created_at = NOW - 600s).
    Sweep. Gauge for ``hr`` ≈ 600s (the MAX, not the average or
    most-recent). NEGATIVE: gauge must reflect the OLDEST, not
    a different aggregation.
 4. Mark all hr drafts replayed → queue is empty for hr; itsm still
    empty too. Sweep. Gauge for ``hr`` resets to 0. NEGATIVE: a
    stale value from step 3 must NOT linger.
 5. Plant an ``itsm.*`` draft → gauge for itsm > 0; hr stays at 0.
    NEGATIVE: independence — one namespace's queue does not
    leak into another's gauge.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_worker_backlog_age.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

from app.workers.draft_replay import (  # type: ignore  # noqa: E402
    DraftReplayWorker,
    _draft_pending_age_seconds,
)

TENANT = os.getenv("TENANT_ID") or str(uuid.uuid4())  # per-drill UUID tenant
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


def _gauge(namespace: str) -> float:
    if _draft_pending_age_seconds is None:
        return 0.0
    return _draft_pending_age_seconds.labels(namespace=namespace)._value.get()  # noqa: SLF001


class _NoopClient:
    """A stand-in client for namespaces the drill registers but
    doesn't drive. The worker only calls ``cb_state`` (we expose
    'closed') and never invokes a tool because we sweep against
    an empty queue OR plant drafts that the worker won't replay
    (we mark them done out-of-band)."""

    @property
    def cb_state(self) -> str:
        return "closed"

    async def list_pending_drafts(self, tenant_id: str) -> list:
        # Worker reads via the FIRST client only; we provide a real
        # PG-backed reader as the first, this is just for routing.
        return []

    async def resolve_draft(self, *args, **kwargs):
        raise RuntimeError("drill should not invoke resolve_draft")


async def _seed_draft(
    pool: asyncpg.Pool, *, draft_id: str, tool: str, age_seconds: float,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            await conn.execute(
                """
                INSERT INTO governance.action_drafts
                    (draft_id, tenant_id, tool, arguments, reason, status,
                     created_at)
                VALUES ($1, $2::uuid, $3, '{}'::jsonb, 'drill_backlog_age',
                        'pending', NOW() - make_interval(secs => $4))
                """,
                draft_id, TENANT, tool, age_seconds,
            )


async def _drain_pending(pool: asyncpg.Pool) -> None:
    """Drain ALL pending drafts in this drill's per-UUID tenant.

    Why ALL, not by prefix: when the worker invokes resolve_draft
    against an unreachable MCPClient (base_url 127.0.0.1:0), the
    client's degraded path persists a NEW draft with reason='ConnectError'.
    These auto-created drafts have UUID-prefixed IDs that don't
    match our planted DRAFT-AGE- prefix. Draining by prefix leaves
    them pending; the next sweep then computes their fresh age and
    the gauge gets a non-zero residual. Per-UUID tenant isolation
    makes "drain all pending" hermetic — we own this tenant.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            await conn.execute(
                """
                UPDATE governance.action_drafts
                   SET status = 'replayed',
                       replay_result = '{"drill":"cleanup"}'::jsonb,
                       replayed_at = NOW()
                 WHERE status = 'pending'
                """,
            )


async def _delete_drafts(pool: asyncpg.Pool, prefix: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM governance.action_drafts WHERE draft_id LIKE $1",
            f"{prefix}%",
        )


# Adapter so PostgresDraftStore can be used with our pool — same
# pattern as drill_audit_actor_type / drill_worker_metrics.
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


async def main() -> None:
    suffix = uuid.uuid4().hex[:8].upper()
    HR1 = f"DRAFT-AGE-HR1-{suffix}"
    HR2 = f"DRAFT-AGE-HR2-{suffix}"
    ITSM1 = f"DRAFT-AGE-ITSM1-{suffix}"

    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
    try:
        await _delete_drafts(pool, "DRAFT-AGE-")

        # The worker reads via its first client. We need a real
        # PostgresDraftStore-backed client as the reader so
        # list_pending_drafts works. Use a fresh MCPClient pointed
        # at no MCP server (we never call the tool).
        from mcp import MCPClient, PostgresDraftStore  # noqa: E402

        store = PostgresDraftStore(_FakeDb(pool))
        # The first client must be PG-backed so list_pending_drafts
        # actually queries the table. Both registered namespaces
        # share the store (the worker's reader is just the first
        # one; routing is per-draft by namespace).
        hr_client = MCPClient(
            base_url="http://127.0.0.1:0",  # never called
            draft_store=store,
            recovery_timeout=1.0,
        )
        itsm_client = MCPClient(
            base_url="http://127.0.0.1:0",
            draft_store=store,
            recovery_timeout=1.0,
        )
        worker = DraftReplayWorker(
            mcp_clients={"hr": hr_client, "itsm": itsm_client},
            tenant_ids=[TENANT],
            interval_s=1,
            per_draft_backoff_s=999,  # ensure no draft is touched this drill
        )

        step("1. Empty queue → gauge is 0 for both namespaces")
        await worker.sweep_once()
        if _gauge("hr") != 0.0:
            fail(f"hr gauge should be 0 on empty queue, got {_gauge('hr')}")
        if _gauge("itsm") != 0.0:
            fail(f"itsm gauge should be 0 on empty queue, got {_gauge('itsm')}")
        ok("hr=0 itsm=0 on empty queue")

        step("2. One hr draft @ 120s old → hr gauge ≈ 120; itsm stays 0")
        await _seed_draft(pool, draft_id=HR1, tool="hr.leave_request", age_seconds=120)
        await worker.sweep_once()
        hr_age = _gauge("hr")
        itsm_age = _gauge("itsm")
        if not (115 <= hr_age <= 135):  # tolerance for drill runtime + sweep latency
            fail(f"hr gauge should be ~120s, got {hr_age:.1f}")
        if itsm_age != 0.0:
            fail(f"itsm gauge should still be 0, got {itsm_age:.1f}")
        ok(f"hr={hr_age:.1f}s itsm={itsm_age:.1f}s (correct namespace targeted)")

        step("3. Add older hr draft @ 600s → gauge reports the MAX")
        await _seed_draft(pool, draft_id=HR2, tool="hr.leave_request", age_seconds=600)
        await worker.sweep_once()
        hr_age = _gauge("hr")
        if not (595 <= hr_age <= 615):
            fail(
                f"hr gauge should be ~600s (MAX of 120/600), got {hr_age:.1f}. "
                f"If got ~120, the gauge is using min/avg/most-recent — "
                f"oldest-pending semantics broken."
            )
        ok(f"hr={hr_age:.1f}s (max wins, not min/avg/most-recent)")

        step("4. Drain hr queue → hr gauge resets to 0")
        await _drain_pending(pool)
        await worker.sweep_once()
        if _gauge("hr") != 0.0:
            fail(
                f"hr gauge should reset to 0 when queue is empty, "
                f"got {_gauge('hr'):.1f}. A stale value lingering from "
                f"step 3 would trigger phantom alerts."
            )
        ok("hr=0 after drain (no stale value)")

        step("5. Plant itsm draft → itsm > 0; hr stays at 0 (independence)")
        await _seed_draft(pool, draft_id=ITSM1, tool="itsm.incident_open", age_seconds=300)
        await worker.sweep_once()
        hr_age = _gauge("hr")
        itsm_age = _gauge("itsm")
        if hr_age != 0.0:
            fail(f"hr gauge bled in from itsm: hr={hr_age:.1f}")
        if not (295 <= itsm_age <= 315):
            fail(f"itsm gauge should be ~300s, got {itsm_age:.1f}")
        ok(f"hr={hr_age:.1f}s itsm={itsm_age:.1f}s (per-namespace isolation)")

        # Cleanup
        await _delete_drafts(pool, "DRAFT-AGE-")
        await hr_client.close()
        await itsm_client.close()

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 BACKLOG-AGE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
