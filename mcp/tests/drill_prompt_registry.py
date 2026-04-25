# RESOURCES: pg
"""
Drill: governance.prompts status enum is enforced in storage AND
DbBackedPromptBuilder only surfaces 'active' rows.

The convergence-shortlist "prompt registry" item is mostly built —
table + repo + 30s-refresh builder all exist. The remaining gaps:
no CHECK constraint on status (silent-typo risk per ADR-005's
pattern), and no drill verifying lifecycle behavior end-to-end.
This commit closes both.

Negative-assertion §43-style:
 1. INSERT with status='active' on a fresh row is accepted.
    NEGATIVE: this is the positive control — without it, step 2
    might silently pass on a connection error.
 2. INSERT with status='actve' (silent typo) is REJECTED by the
    new CHECK constraint. NEGATIVE: a typo'd status must NOT
    silently land — that's the bug the constraint exists for.
 3. Name + version uniqueness — the existing
    ``prompts_name_version_key`` UNIQUE rejects duplicates.
    NEGATIVE: two rows with same name/version must NOT coexist.
 4. PromptRepo.list_active returns 'active' rows only.
    NEGATIVE: 'draft' / 'archived' / 'deprecated' rows must NOT
    appear in list_active output (proves the WHERE filter).
 5. Status enum allows the four lifecycle states + rejects
    everything else. NEGATIVE: a future code change that adds a
    state via INSERT (not migration) hits the constraint.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_prompt_registry.py
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

from app.services.prompt_repo import PromptRepo  # type: ignore  # noqa: E402

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


class _FakeDb:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @asynccontextmanager
    async def admin_connection(self):
        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def tenant_connection(self, t: str):
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", t,
                )
                yield conn


async def _delete(pool: asyncpg.Pool, name_prefix: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM governance.prompts WHERE name LIKE $1",
            f"{name_prefix}%",
        )


async def _insert(
    pool: asyncpg.Pool,
    *, name: str, version: str, template: str = "system\n---USER---\nask: {q}",
    status: str = "active",
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO governance.prompts (name, version, template, status)
            VALUES ($1, $2, $3, $4)
            """,
            name, version, template, status,
        )


async def main() -> None:
    suffix = uuid.uuid4().hex[:8].upper()
    NAME = f"drill_prompt_{suffix}"
    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
    try:
        await _delete(pool, "drill_prompt_")

        step("1. INSERT with status='active' on a fresh row is accepted (sanity)")
        await _insert(pool, name=NAME, version="v1", status="active")
        async with pool.acquire() as conn:
            cnt = await conn.fetchval(
                "SELECT count(*) FROM governance.prompts WHERE name=$1", NAME,
            )
        if cnt != 1:
            fail(f"expected 1 row, got {cnt}")
        ok(f"row {NAME}/v1 inserted with status=active")

        step("2. INSERT with status='actve' is REJECTED by CHECK constraint")
        rejected = False
        try:
            await _insert(pool, name=NAME, version="v_typo", status="actve")
        except asyncpg.exceptions.CheckViolationError as exc:
            rejected = True
            if "prompts_status_valid" not in str(exc):
                fail(f"wrong constraint name: {exc}")
        if not rejected:
            fail(
                "INSERT status='actve' was accepted — silent-typo "
                "vulnerability is the exact bug this constraint prevents"
            )
        ok("typo'd status rejected by prompts_status_valid")

        step("3. Name + version uniqueness — second INSERT with same key rejected")
        rejected = False
        try:
            await _insert(pool, name=NAME, version="v1", status="draft")
        except asyncpg.exceptions.UniqueViolationError as exc:
            rejected = True
            if "prompts_name_version_key" not in str(exc):
                fail(f"wrong constraint name in error: {exc}")
        if not rejected:
            fail(
                "duplicate name+version was accepted — registry would "
                "have two rows for the same prompt identity"
            )
        ok("duplicate (name, version) rejected by prompts_name_version_key")

        step("4. PromptRepo.list_active returns 'active' rows ONLY")
        # Insert one of each status to verify the filter.
        await _insert(pool, name=NAME, version="v2_draft",      status="draft")
        await _insert(pool, name=NAME, version="v3_archived",   status="archived")
        await _insert(pool, name=NAME, version="v4_deprecated", status="deprecated")
        repo = PromptRepo(_FakeDb(pool))
        rows = await repo.list_active()
        ours = [r for r in rows if r["name"] == NAME]
        statuses = {r["status"] for r in ours}
        if statuses != {"active"}:
            fail(
                f"list_active returned non-active statuses: {statuses}. "
                f"WHERE status='active' filter is broken — operators "
                f"would see 'draft' and 'deprecated' prompts in the "
                f"registry view."
            )
        if len(ours) != 1:
            fail(f"expected 1 active row, got {len(ours)}: {[r['version'] for r in ours]}")
        if ours[0]["version"] != "v1":
            fail(f"wrong active row returned: {ours[0]['version']}")
        ok(f"only the v1/active row surfaced (3 non-active rows filtered)")

        step("5. All four lifecycle states accepted; one synthetic state rejected")
        # The 4 states accepted in step 4 already proved themselves on
        # INSERT. Now a synthetic future state to confirm the
        # constraint blocks unknown values too.
        rejected = False
        try:
            await _insert(pool, name=NAME, version="v5_future", status="experimental")
        except asyncpg.exceptions.CheckViolationError:
            rejected = True
        if not rejected:
            fail(
                "status='experimental' was accepted — a future state "
                "must land via migration (ALTER constraint), not via "
                "a sneaked-in INSERT"
            )
        ok("4 states {draft,active,archived,deprecated} accepted; unknown states rejected")

        # Cleanup
        await _delete(pool, "drill_prompt_")

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 PROMPT-REGISTRY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
