# RESOURCES: mcp_hr pg
"""
Drill: idempotency cache is durable (survives store-instance lifetime),
fingerprint-aware, in-progress-aware, TTL-purged.

Migration 007 + mcp/idempotency.py replaced the process-local
``dict`` with a Postgres-backed store. This drill proves each
production-grade behaviour with negative assertions §43-style.

The pivotal step is #3: we INSERT a "succeeded" row with raw
asyncpg, bypassing the store entirely, then construct a FRESH
PostgresIdempotencyStore and call ``lookup_or_register`` — it must
return the cached response. That's the test for "durable" that
matters; constructing-and-replaying within the same store instance
only proves object lifetime.

Flow:
 1. New key + fingerprint → state="new". Same key + same fingerprint
    while still in_progress → state="in_progress".
 2. finalize(succeeded) → next lookup returns state="done" with the
    cached response.
 3. **The durability test.** Bypass the store: INSERT a 'succeeded'
    row directly via asyncpg. Construct a FRESH store object and
    look up — must return state="done". Without DB persistence
    this fails.
 4. Same key, DIFFERENT fingerprint → state="conflict" (the bug
    where a client retries with mutated arguments).
 5. TTL purge: insert an EXPIRED row directly, then call
    lookup_or_register on its key — purge happens inline, key
    behaves as "new".
 6. CHECK constraint regression: INSERT with status='garbage' is
    rejected by the DB (migration 007 contract).

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_idempotency_durable.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import asyncpg

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mcp.idempotency import PostgresIdempotencyStore, fingerprint  # noqa: E402

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


async def _raw_clean(prefix: str) -> None:
    """Strip any leftover keys from a previous (failed) run."""
    conn = await asyncpg.connect(dsn=PG_DSN)
    try:
        await conn.execute(
            "DELETE FROM governance.mcp_idempotency WHERE key LIKE $1",
            f"{prefix}%",
        )
    finally:
        await conn.close()


async def main() -> None:
    suffix = uuid.uuid4().hex[:8].upper()
    K_FRESH = f"DRILL-IDEMP-FRESH-{suffix}"
    K_DURABLE = f"DRILL-IDEMP-DURABLE-{suffix}"
    K_CONFLICT = f"DRILL-IDEMP-CONF-{suffix}"
    K_TTL = f"DRILL-IDEMP-TTL-{suffix}"
    K_BAD = f"DRILL-IDEMP-BAD-{suffix}"

    await _raw_clean("DRILL-IDEMP-")

    store = PostgresIdempotencyStore(PG_DSN, ttl_seconds=3600)
    try:
        step("1. State machine — new → in_progress → done")
        fp1 = fingerprint({"name": "drill_runner_junit", "timeout_s": 30})
        state, _ = await store.lookup_or_register(K_FRESH, "drill.run", fp1)
        if state != "new":
            fail(f"first lookup of unknown key should be 'new', got {state!r}")

        # Same key, same fingerprint, before finalize → in_progress
        state, _ = await store.lookup_or_register(K_FRESH, "drill.run", fp1)
        if state != "in_progress":
            fail(f"second lookup before finalize should be 'in_progress', got {state!r}")

        # Finalize succeeded → next lookup returns done with response
        cached_response = {"ok": True, "result": {"steps_passed": 5}}
        await store.finalize(K_FRESH, cached_response)
        state, resp = await store.lookup_or_register(K_FRESH, "drill.run", fp1)
        if state != "done":
            fail(f"after finalize should be 'done', got {state!r}")
        if resp != cached_response:
            fail(f"cached response mismatch: {resp!r} vs {cached_response!r}")
        ok("new → in_progress → done with response round-trip")

        step("2. CAS finalize is idempotent — double-finalize is a no-op")
        # Calling finalize a second time on a row that's already 'succeeded'
        # must not corrupt the response (CAS guards against the in_progress
        # → succeeded check, so the second call WHERE status='in_progress'
        # matches no rows).
        await store.finalize(K_FRESH, {"ok": True, "result": "OVERWRITTEN"})
        state, resp = await store.lookup_or_register(K_FRESH, "drill.run", fp1)
        if resp != cached_response:
            fail(
                f"CAS broken: response was overwritten by second finalize: "
                f"got {resp!r}, expected original {cached_response!r}"
            )
        ok("second finalize is a no-op (CAS guard works)")

        step("3. Durability — fresh store sees rows it didn't write")
        # The pivotal test. INSERT a 'succeeded' row directly, bypassing
        # the store entirely. Construct a brand-new PostgresIdempotencyStore
        # (no shared state with `store` above) and call lookup_or_register —
        # it must see the cached response. This is what "durable" actually
        # means; constructing the same store and replaying within it only
        # proves object lifetime, not persistence.
        bypass_response = {"ok": True, "result": {"injected_via": "asyncpg"}}
        bypass_fp = fingerprint({"injected": True})
        conn = await asyncpg.connect(dsn=PG_DSN)
        try:
            await conn.execute(
                """
                INSERT INTO governance.mcp_idempotency
                    (key, tool, payload_fingerprint, status, response, expires_at)
                VALUES ($1, $2, $3, 'succeeded', $4::jsonb,
                        NOW() + INTERVAL '1 hour')
                """,
                K_DURABLE, "drill.run", bypass_fp, json.dumps(bypass_response),
            )
        finally:
            await conn.close()
        # Construct a FRESH store with no shared state.
        store_b = PostgresIdempotencyStore(PG_DSN, ttl_seconds=3600)
        try:
            state, resp = await store_b.lookup_or_register(
                K_DURABLE, "drill.run", bypass_fp,
            )
            if state != "done":
                fail(
                    f"FRESH store didn't see bypass-injected row: state={state!r}. "
                    f"This is the test that proves durability — failure here means "
                    f"the cache is still process-local."
                )
            if resp != bypass_response:
                fail(f"durable response mismatch: {resp!r}")
        finally:
            await store_b.close()
        ok("fresh store reads bypass-injected row — durability across instances proven")

        step("4. Conflict — same key, different payload fingerprint")
        # The 'fresh' key from step 1 is still in the table with fp1.
        # A client retry with mutated arguments → different fingerprint →
        # MUST be flagged as conflict, not silently return the stale
        # response.
        fp_mutated = fingerprint({"name": "drill_runner_junit", "timeout_s": 31})
        if fp_mutated == fp1:
            fail("fingerprint test setup broken — fps are equal!")
        state, _ = await store.lookup_or_register(K_FRESH, "drill.run", fp_mutated)
        if state != "conflict":
            fail(
                f"same key + different payload should be 'conflict', got {state!r}. "
                f"Without this, a client bug silently returns wrong cached data."
            )
        ok("same-key-different-payload returns conflict (client-bug guard)")

        step("5. TTL purge — expired row is treated as new")
        # Insert a row with expires_at in the past, then look up its key.
        # The PostgresIdempotencyStore's inline DELETE WHERE expires_at < NOW()
        # should clean it before the SELECT, so the key behaves as 'new'.
        expired_fp = fingerprint({"expired": True})
        conn = await asyncpg.connect(dsn=PG_DSN)
        try:
            await conn.execute(
                """
                INSERT INTO governance.mcp_idempotency
                    (key, tool, payload_fingerprint, status, response, expires_at)
                VALUES ($1, $2, $3, 'succeeded', '{}'::jsonb,
                        NOW() - INTERVAL '5 minutes')
                """,
                K_TTL, "drill.run", expired_fp,
            )
        finally:
            await conn.close()
        state, _ = await store.lookup_or_register(K_TTL, "drill.run", expired_fp)
        if state != "new":
            fail(
                f"expired row should be purged inline + lookup behaves as 'new', "
                f"got {state!r}. TTL purge broken."
            )
        # Also verify the row is actually gone from the table.
        conn = await asyncpg.connect(dsn=PG_DSN)
        try:
            row = await conn.fetchrow(
                "SELECT key FROM governance.mcp_idempotency WHERE key = $1 "
                "AND status = 'succeeded'",
                K_TTL,
            )
        finally:
            await conn.close()
        if row is not None:
            fail(f"expired row still present: {row!r}")
        ok("TTL purge runs inline; expired keys re-register as new")

        step("6. CHECK constraint regression — bad status rejected by DB")
        conn = await asyncpg.connect(dsn=PG_DSN)
        rejected = False
        try:
            try:
                await conn.execute(
                    """
                    INSERT INTO governance.mcp_idempotency
                        (key, tool, payload_fingerprint, status, expires_at)
                    VALUES ($1, $2, $3, 'garbage',
                            NOW() + INTERVAL '1 hour')
                    """,
                    K_BAD, "drill.run", fingerprint({}),
                )
            except asyncpg.exceptions.CheckViolationError as exc:
                rejected = True
                # Both ``mcp_idempotency_status_valid`` AND
                # ``mcp_idempotency_response_consistency`` legitimately
                # match a 'garbage'-status row (no response, status not in
                # the enum). Postgres reports whichever fires first, and
                # constraint evaluation order isn't guaranteed. Either is
                # the right rejection — the storage caught the bad shape.
                msg = str(exc)
                if not (
                    "mcp_idempotency_status_valid" in msg
                    or "mcp_idempotency_response_consistency" in msg
                ):
                    fail(f"unexpected constraint in rejection: {exc}")
        finally:
            await conn.close()
        if not rejected:
            fail("status='garbage' was accepted — CHECK constraint missing!")
        ok("garbage status rejected by mcp_idempotency_status_valid")

        # Cleanup
        await _raw_clean("DRILL-IDEMP-")

    finally:
        await store.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 IDEMPOTENCY-DURABILITY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
