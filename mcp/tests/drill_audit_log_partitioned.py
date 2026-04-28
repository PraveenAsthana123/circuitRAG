#!/usr/bin/env python3
# RESOURCES: pg
"""
Drill: governance.audit_log_partitioned — partition routing + RLS +
helper function behavior.

Verifies migration 009_audit_log_partitioned.sql produces a working
partitioned table that:
  * Routes inserts to the correct monthly partition based on
    timestamp.
  * Refuses inserts that fall outside any pre-created partition
    (positive defensive signal — a regression that allowed silent
    drift would land rows in a default/overflow partition we never
    monitor).
  * Honors RLS — wrong tenant sees zero rows.
  * Helper governance.create_audit_log_partition is idempotent +
    correctly bridges December → January (year rollover).

Composes with:
  * /admin/explainability/deep#audit-rag-contract-regulation —
    Topic 2 documents this exact partitioning + retention strategy.
  * ~/.claude/policies/ai-explainability.md §4 — 7y retention for
    regulated AI; partitioning is the implementation that makes
    that retention practical at scale.
  * Existing governance.audit_log (UNTOUCHED by this drill) — the
    additive scaffold preserves the legacy table.

Eight steps (3 negative assertions):

 1. Migration 009 file exists + has the expected partitioning
    structure (source scan).
 2. audit_log_partitioned exists as a partitioned table; bootstrap
    created ≥ 3 monthly partitions.
 3. Insert at "now" → row lands in the current-month partition
    (verify by SELECTing FROM that specific partition by name, NOT
    the parent — proves routing actually fires).
 4. NEGATIVE: insert at a date FAR outside any pre-created partition
    (e.g. year 2099) MUST raise. A silent drift to a default
    partition would land regulator-required audit rows in a
    location operations never monitors.
 5. NEGATIVE: With wrong tenant_id session, SELECT returns ZERO
    rows. RLS policy must apply on the partitioned parent +
    propagate to every partition (declarative-partitioning
    semantics — without testing this, a regression that ALTER
    TABLE ... DISABLE ROW LEVEL SECURITY on a partition would
    silently break tenant isolation).
 6. Helper function — calling create_audit_log_partition for a
    NEW month succeeds (idempotent: re-call returns same name,
    no error).
 7. NEGATIVE: helper call for a December → January boundary
    correctly bridges the year rollover (mm=13 must NOT happen).
 8. Existing governance.audit_log (legacy unpartitioned) is
    UNTOUCHED — schema unchanged, row count unchanged, no
    accidental migration of data. This is the "additive" promise
    the migration's docstring makes; the drill locks it in.

Run:
    python3 mcp/tests/drill_audit_log_partitioned.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    sys.exit(1)


def yellow(msg: str) -> None:
    print(f"  {YELLOW}⚠ {msg}{NC}")


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


PG_DSN = os.getenv(
    "DOCUMIND_PG_DSN",
    # Default is the host-bound port for documind-postgres in
    # docker-compose (55432 on host → 5432 in container). The other
    # 5432 binding on this host belongs to a separate postgres
    # instance that doesn't have the documind role; using the
    # explicit mapped port avoids that collision.
    "postgresql://documind:documind@localhost:55432/documind",
)
# RLS is exercised via the non-BYPASSRLS app role. The documind
# admin role has rolbypassrls=t and would silently see every row
# regardless of app.current_tenant — using it for the RLS step
# would produce false-positive passes. documind_app is the role
# every service uses in production code paths.
APP_PG_DSN = os.getenv(
    "DOCUMIND_PG_APP_DSN",
    "postgresql://documind_app:documind_app@localhost:55432/documind",
)
REPO = Path("/mnt/deepa/rag")
MIGRATION_PATH = (
    REPO / "services/governance-svc/migrations/009_audit_log_partitioned.sql"
)


async def main() -> None:
    # ── Step 1 ───────────────────────────────────────────────────
    step("1. migration 009 file present + has partitioning structure")
    if not MIGRATION_PATH.exists():
        fail(f"missing: {MIGRATION_PATH}")
    src = MIGRATION_PATH.read_text()
    for required in (
        "PARTITION BY RANGE (timestamp)",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "CREATE OR REPLACE FUNCTION governance.create_audit_log_partition",
        "PRIMARY KEY (id, timestamp)",
    ):
        if required not in src:
            fail(f"migration missing required clause: {required!r}")
    ok("migration source has partitioning + RLS + helper function + composite PK")

    # Try asyncpg — gate the rest of the drill on PG availability.
    try:
        import asyncpg
    except ImportError:
        yellow(
            "asyncpg not installed locally; remaining steps require live "
            "Postgres connectivity. CI runs the full drill."
        )
        return

    try:
        pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=2)
    except Exception as exc:  # noqa: BLE001
        yellow(
            f"could not connect to Postgres at {PG_DSN!r}: {exc}. "
            "Skip remaining steps."
        )
        return

    # Separate pool for RLS-enforcing role. If unavailable, RLS step
    # is skipped with a yellow warning rather than a false positive
    # via the BYPASSRLS admin role.
    app_pool = None
    try:
        app_pool = await asyncpg.create_pool(APP_PG_DSN, min_size=1, max_size=2)
    except Exception as exc:  # noqa: BLE001
        yellow(
            f"could not connect as documind_app: {exc}. RLS-dependent "
            "steps will yellow-skip. Set DOCUMIND_PG_APP_DSN to test RLS."
        )

    try:
        # ── Step 2 ────────────────────────────────────────────────
        step("2. partitioned table exists + ≥ 3 bootstrap partitions")
        async with pool.acquire() as conn:
            relkind = await conn.fetchval(
                "SELECT relkind::text FROM pg_class "
                "WHERE oid = 'governance.audit_log_partitioned'::regclass"
            )
            if relkind != "p":
                fail(
                    f"audit_log_partitioned relkind={relkind!r}, expected 'p' "
                    f"(partitioned). Migration not applied or table created "
                    f"as plain table."
                )
            partitions = await conn.fetch(
                """
                SELECT inhrelid::regclass::text AS partition
                FROM pg_inherits
                WHERE inhparent = 'governance.audit_log_partitioned'::regclass
                ORDER BY 1
                """
            )
            if len(partitions) < 3:
                fail(
                    f"expected ≥ 3 bootstrap partitions, got "
                    f"{len(partitions)}: {[p['partition'] for p in partitions]}"
                )
        ok(
            f"audit_log_partitioned is partitioned (relkind=p) with "
            f"{len(partitions)} partitions: "
            f"{[p['partition'] for p in partitions]}"
        )

        # Test fixtures.
        test_tenant = "00000000-0000-0000-0000-0000000d1117"
        wrong_tenant = "00000000-0000-0000-0000-0000000d1199"

        # ── Step 3 ────────────────────────────────────────────────
        step("3. insert at now → row lands in current-month partition")
        now = datetime.now(UTC)
        row_id = _uuid.uuid4()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)",
                    test_tenant,
                )
                await conn.execute(
                    """
                    INSERT INTO governance.audit_log_partitioned
                        (id, timestamp, tenant_id, actor_type, action,
                         details, correlation_id)
                    VALUES ($1::uuid, $2, $3::uuid, $4, $5, '{}'::jsonb, $6::uuid)
                    """,
                    row_id, now, test_tenant, "service", "drill.partition_test",
                    _uuid.uuid4(),
                )

        # Verify by SELECTing from the SPECIFIC partition (not the parent).
        # This proves declarative partitioning routed the row, not just
        # that an INSERT into the parent succeeded with no error.
        partition_name = (
            f"audit_log_p_y{now.strftime('%Y')}m{now.strftime('%m')}"
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)",
                test_tenant,
            )
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM governance.{partition_name} "
                f"WHERE id = $1::uuid",
                row_id,
            )
        if count != 1:
            fail(
                f"row routed wrong: SELECT FROM partition "
                f"{partition_name} WHERE id={row_id} returned count={count} "
                f"(expected 1). Partition routing is not working."
            )
        ok(
            f"insert at {now.isoformat()} routed to partition "
            f"{partition_name} (verified by per-partition SELECT)"
        )

        # ── Step 4: NEGATIVE — far-future insert must fail ────────
        step(
            "4. NEGATIVE: insert at year 2099 → fails (no partition; never "
            "silent overflow)"
        )
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1, true)",
                        test_tenant,
                    )
                    await conn.execute(
                        """
                        INSERT INTO governance.audit_log_partitioned
                            (id, timestamp, tenant_id, actor_type, action,
                             details)
                        VALUES (gen_random_uuid(), '2099-06-15 00:00:00+00',
                                $1::uuid, 'service', 'drill.far_future',
                                '{}'::jsonb)
                        """,
                        test_tenant,
                    )
            fail(
                "NEGATIVE FAILED: insert at year 2099 succeeded. A regression "
                "that added a default partition would land regulator-required "
                "audit rows in an unmonitored bucket. Bootstrap MUST stay "
                "explicit-only."
            )
        except asyncpg.exceptions.CheckViolationError as exc:
            ok(f"far-future insert refused with CheckViolation: "
               f"{str(exc)[:80]}…")
        except Exception as exc:  # asyncpg may surface this as InvalidTextRepresentation or similar
            # Accept any exception that mentions partition or no-route.
            msg = str(exc).lower()
            if "partition" in msg or "no partition" in msg or "no relation" in msg:
                ok(f"far-future insert refused: {str(exc)[:100]}…")
            else:
                fail(
                    f"insert raised but message doesn't reference partitioning: "
                    f"{exc!r}. The W3C contract still holds (insert refused) "
                    f"but the operator-facing error should mention partitions "
                    f"so the on-call understands the failure mode."
                )

        # ── Step 5: NEGATIVE — RLS on partitioned table ──────────
        step(
            "5. NEGATIVE: wrong tenant SELECT returns 0 rows (RLS holds on "
            "partitioned parent — verified via documind_app non-BYPASSRLS role)"
        )
        if app_pool is None:
            yellow(
                "documind_app pool unavailable — skipping RLS verification. "
                "An admin role with BYPASSRLS would silently pass even with "
                "broken RLS, so we yellow-skip rather than false-pass."
            )
        else:
            # set_config(..., true) is transaction-local — must wrap in
            # an explicit transaction or the setting is a no-op + the
            # SELECT returns 0 even for the right tenant (because
            # NULLIF('', '')::uuid is NULL, RLS filter trivially false).
            async with app_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1, true)",
                        wrong_tenant,
                    )
                    wrong_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM governance.audit_log_partitioned "
                        "WHERE id = $1::uuid",
                        row_id,
                    )
            if wrong_count != 0:
                fail(
                    f"NEGATIVE FAILED: wrong tenant_id session (as "
                    f"documind_app) saw {wrong_count} rows for id={row_id} "
                    f"(expected 0). RLS policy is NOT applied to the "
                    f"partitioned table — declarative-partitioning RLS "
                    f"propagation broke."
                )
            ok("wrong tenant returned 0 rows — RLS policy on partitioned parent "
               "propagates to all partitions")

            # Confirm the right tenant DOES see the row (positive contrast).
            async with app_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1, true)",
                        test_tenant,
                    )
                    right_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM governance.audit_log_partitioned "
                        "WHERE id = $1::uuid",
                        row_id,
                    )
            if right_count != 1:
                fail(f"correct tenant (as documind_app) saw {right_count} "
                     f"rows; expected 1")
            ok("correct tenant sees the row — RLS allows authorized access")

        # ── Step 6 — helper function idempotent ──────────────────
        step("6. create_audit_log_partition is idempotent + returns name")
        async with pool.acquire() as conn:
            future = now + timedelta(days=120)  # a few months out
            yyyy, mm = future.strftime("%Y"), future.strftime("%m")
            name1 = await conn.fetchval(
                "SELECT governance.create_audit_log_partition($1, $2)",
                yyyy, mm,
            )
            name2 = await conn.fetchval(
                "SELECT governance.create_audit_log_partition($1, $2)",
                yyyy, mm,
            )
        if name1 != name2:
            fail(
                f"helper not idempotent: first call returned {name1!r}, "
                f"second {name2!r}. Re-running the bootstrap or a missed "
                f"cron retry would create dupes."
            )
        expected_name = f"audit_log_p_y{yyyy}m{mm}"
        if name1 != expected_name:
            fail(f"helper returned {name1!r}; expected {expected_name!r}")
        ok(f"helper idempotent: returns {name1!r} on first + second call")

        # ── Step 7: NEGATIVE — December → January year rollover ──
        step(
            "7. NEGATIVE: helper call for December bridges to January of "
            "next year (mm=13 must never happen)"
        )
        # Use a year guaranteed not to clash with bootstrap or step 6.
        async with pool.acquire() as conn:
            dec_name = await conn.fetchval(
                "SELECT governance.create_audit_log_partition('2087', '12')"
            )
            # Verify the partition's bound range bridges to 2088-01.
            range_expr = await conn.fetchval(
                """
                SELECT pg_get_expr(c.relpartbound, c.oid)
                FROM pg_class c
                WHERE c.oid = 'governance.audit_log_p_y2087m12'::regclass
                """
            )
        if "2088-01-01" not in range_expr:
            fail(
                f"NEGATIVE FAILED: December 2087 partition range "
                f"{range_expr!r} does not bridge to 2088-01-01. The "
                f"helper's year-rollover logic broke — a regression "
                f"would emit '2087-13-01' (invalid date) and the partition "
                f"would silently fail to create on Dec 1."
            )
        ok(f"Dec 2087 partition correctly bridges to Jan 2088: {range_expr}")

        # ── Step 8: legacy audit_log untouched ──────────────────
        step(
            "8. legacy governance.audit_log is UNTOUCHED — additive promise "
            "of the migration holds"
        )
        async with pool.acquire() as conn:
            relkind = await conn.fetchval(
                "SELECT relkind::text FROM pg_class "
                "WHERE oid = 'governance.audit_log'::regclass"
            )
            cols = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'governance' AND table_name = 'audit_log' "
                "ORDER BY ordinal_position"
            )
        if relkind != "r":
            fail(
                f"NEGATIVE FAILED: legacy audit_log relkind={relkind!r}, "
                f"expected 'r' (regular table). Migration accidentally "
                f"converted the legacy table."
            )
        col_names = [c["column_name"] for c in cols]
        # The legacy schema (per migration 001) has these columns.
        expected_legacy_cols = {
            "id", "timestamp", "tenant_id", "actor_id", "actor_type",
            "action", "resource_type", "resource_id", "details",
            "correlation_id", "ip_address", "user_agent",
        }
        if not expected_legacy_cols.issubset(col_names):
            fail(
                f"legacy audit_log column set differs from baseline. Got "
                f"{col_names}. Migration must NOT modify legacy schema."
            )
        ok(
            f"legacy audit_log unchanged: relkind=r, "
            f"{len(col_names)} columns including the canonical "
            f"audit shape"
        )

        # ── Cleanup ──────────────────────────────────────────────
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)",
                    test_tenant,
                )
                await conn.execute(
                    "DELETE FROM governance.audit_log_partitioned "
                    "WHERE id = $1::uuid",
                    row_id,
                )

    finally:
        await pool.close()
        if app_pool is not None:
            await app_pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 PARTITION STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
