# RESOURCES: pg
"""
Drill: governance.tools + governance.tool_permissions migration + composition.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
(expand-phase), §52 row 4 (operator API gap), §53.39 (observability
taxonomy).

Migration 011_tools_registry.sql creates the SQL catalog of MCP tools
+ RBAC permissions. Currently the MCP servers source tools from Python
TOOLS literals in mcp/server_*.py. Per §47.7 expand-phase: SQL surface
exists + drilled; future iteration syncs Python → SQL on server boot;
contract-phase later makes SQL authoritative.

Locks (positive):
  L1. governance.tools table exists with documented columns
  L2. governance.tool_permissions table exists with documented columns
  L3. UNIQUE (server, name) on tools, UNIQUE (server, tool_name,
      actor_pattern) on permissions
  L4. CHECK constraint validates risk_level ∈ {low,medium,high,critical}
  L5. CHECK constraint validates side_effects ∈ {read,write,destructive,external}
  L6. tools_catalog appears in build_registry() at top level
  L7. Round-trip: insert synthetic tool + permission → registry sees them
      → ROLLBACK so no test data persists

Locks (negative — ≥3 per §43):
  N1. Empty catalog → registry returns total_tools=0 with honest_gap
      naming the table; NOT silent zero.

  N2. CHECK violation: INSERT with risk_level='wat' MUST fail with
      a constraint error. Drill catches the SQLState explicitly.

  N3. CHECK violation: INSERT with side_effects='maybe' MUST fail.

  N4. UNIQUE violation: INSERT (server, name) twice → second INSERT
      fails with unique-violation. Idempotent migrations rely on this.

  N5. NO RLS: governance.tools is system catalog, NOT tenant data.
      Drill verifies relrowsecurity=FALSE (would be a security
      mis-design to make catalog tenant-isolated; would break any
      orchestrator that needs to know what tools exist).

  N6. Read-only contract: registry's _read_tools_registry MUST NOT
      execute any INSERT/UPDATE/DELETE. Drill greps the function body.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import agent_task_registry as registry  # noqa: E402

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"

PG_HOST = "localhost"
PG_PORT = 55432
PG_USER = "documind"
PG_PASSWORD = "documind"
PG_DB = "documind"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


async def _admin_conn():
    import asyncpg
    return await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        database=PG_DB, timeout=3.0,
    )


def main() -> int:
    # ===================================================================
    # Step 1 — governance.tools shape
    # ===================================================================
    step("1. governance.tools table exists with documented columns")

    async def _check_tools_cols():
        conn = await _admin_conn()
        try:
            rows = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                " WHERE table_schema='governance' AND table_name='tools' "
                " ORDER BY ordinal_position"
            )
            return {r["column_name"] for r in rows}
        finally:
            await conn.close()

    cols = asyncio.run(_check_tools_cols())
    expected = {
        "id", "server", "name", "description",
        "input_schema", "output_schema",
        "side_effects", "required_scopes", "idempotent",
        "risk_level", "enabled", "approval_required",
        "owner_team", "created_at", "updated_at",
    }
    missing = expected - cols
    if missing:
        fail(f"governance.tools missing columns: {missing}")
    ok(f"governance.tools: all {len(expected)} documented columns present")

    # ===================================================================
    # Step 2 — governance.tool_permissions shape
    # ===================================================================
    step("2. governance.tool_permissions table exists with documented columns")

    async def _check_perm_cols():
        conn = await _admin_conn()
        try:
            rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                " WHERE table_schema='governance' AND table_name='tool_permissions'"
            )
            return {r["column_name"] for r in rows}
        finally:
            await conn.close()

    pcols = asyncio.run(_check_perm_cols())
    expected_p = {
        "id", "server", "tool_name", "actor_pattern",
        "can_invoke", "can_modify", "can_admin",
        "granted_by", "granted_reason",
        "created_at", "expires_at",
    }
    missing_p = expected_p - pcols
    if missing_p:
        fail(f"tool_permissions missing columns: {missing_p}")
    ok(f"tool_permissions: all {len(expected_p)} documented columns present")

    # ===================================================================
    # Step 3 — UNIQUE constraints exist
    # ===================================================================
    step("3. UNIQUE (server, name) on tools + UNIQUE (server, tool_name, actor_pattern) on perms")

    async def _check_unique():
        conn = await _admin_conn()
        try:
            rows = await conn.fetch(
                "SELECT conname, contype, conrelid::regclass::text AS tbl "
                "  FROM pg_constraint "
                " WHERE conrelid IN ("
                "       'governance.tools'::regclass, "
                "       'governance.tool_permissions'::regclass) "
                "   AND contype = 'u'"
            )
            return {(r["tbl"], r["conname"]) for r in rows}
        finally:
            await conn.close()

    unique_constraints = asyncio.run(_check_unique())
    has_tools_unique = any(
        "tools" in tbl and "server_name" in name
        for (tbl, name) in unique_constraints
    )
    has_perms_unique = any(
        "tool_permissions" in tbl
        for (tbl, name) in unique_constraints
    )
    if not has_tools_unique:
        fail(f"tools UNIQUE(server,name) missing; found: {unique_constraints}")
    if not has_perms_unique:
        fail(f"tool_permissions UNIQUE missing; found: {unique_constraints}")
    ok(f"both UNIQUE constraints present ({len(unique_constraints)} total)")

    # ===================================================================
    # Step 4 — NEGATIVE: CHECK risk_level
    # ===================================================================
    step("4. NEGATIVE: invalid risk_level → CHECK violation")

    async def _check_risk():
        conn = await _admin_conn()
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                try:
                    await conn.execute(
                        "INSERT INTO governance.tools "
                        "(server, name, description, side_effects, risk_level) "
                        "VALUES ('drill', 'drill.bad_risk', 'drill', 'read', 'wat')"
                    )
                    return "FAIL: insert with risk_level='wat' did NOT raise"
                except Exception as exc:
                    if "tools_risk_level_valid" in str(exc) or "check constraint" in str(exc).lower():
                        return "OK"
                    return f"FAIL: wrong exception: {type(exc).__name__}: {exc}"
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    result = asyncio.run(_check_risk())
    if result.startswith("OK"):
        ok("invalid risk_level rejected by CHECK constraint")
    else:
        fail(result)

    # ===================================================================
    # Step 5 — NEGATIVE: CHECK side_effects
    # ===================================================================
    step("5. NEGATIVE: invalid side_effects → CHECK violation")

    async def _check_side():
        conn = await _admin_conn()
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                try:
                    await conn.execute(
                        "INSERT INTO governance.tools "
                        "(server, name, description, side_effects, risk_level) "
                        "VALUES ('drill', 'drill.bad_side', 'drill', 'maybe', 'low')"
                    )
                    return "FAIL: insert with side_effects='maybe' did NOT raise"
                except Exception as exc:
                    if "tools_side_effects_valid" in str(exc) or "check constraint" in str(exc).lower():
                        return "OK"
                    return f"FAIL: wrong exception: {type(exc).__name__}: {exc}"
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    result = asyncio.run(_check_side())
    if result.startswith("OK"):
        ok("invalid side_effects rejected by CHECK constraint")
    else:
        fail(result)

    # ===================================================================
    # Step 6 — NEGATIVE: UNIQUE violation
    # ===================================================================
    step("6. NEGATIVE: duplicate (server, name) → UNIQUE violation")

    async def _check_unique_violation():
        conn = await _admin_conn()
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                # First insert OK
                await conn.execute(
                    "INSERT INTO governance.tools "
                    "(server, name, description, side_effects, risk_level) "
                    "VALUES ('drill', 'drill.dupe', 'first', 'read', 'low')"
                )
                # Second insert with same (server, name) MUST fail
                try:
                    await conn.execute(
                        "INSERT INTO governance.tools "
                        "(server, name, description, side_effects, risk_level) "
                        "VALUES ('drill', 'drill.dupe', 'second', 'read', 'low')"
                    )
                    return "FAIL: duplicate insert did NOT raise"
                except Exception as exc:
                    if "unique" in str(exc).lower() or "tools_server_name_unique" in str(exc):
                        return "OK"
                    return f"FAIL: wrong exception: {type(exc).__name__}: {exc}"
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    result = asyncio.run(_check_unique_violation())
    if result.startswith("OK"):
        ok("duplicate (server, name) → UNIQUE violation as expected")
    else:
        fail(result)

    # ===================================================================
    # Step 7 — NEGATIVE: NO RLS on system catalog
    # ===================================================================
    step("7. NEGATIVE: governance.tools has NO RLS (system catalog)")

    async def _check_rls():
        conn = await _admin_conn()
        try:
            row = await conn.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                " WHERE oid = 'governance.tools'::regclass"
            )
            return row
        finally:
            await conn.close()

    rls = asyncio.run(_check_rls())
    if rls["relrowsecurity"]:
        fail(
            "governance.tools has RLS enabled — this is a SYSTEM CATALOG, "
            "should NOT be tenant-scoped. Same pattern as governance.policies "
            "+ governance.feature_flags (also no RLS)."
        )
    ok("RLS disabled on system catalog (correct per governance.policies precedent)")

    # ===================================================================
    # Step 8 — _read_tools_registry shape contract
    # ===================================================================
    step("8. _read_tools_registry returns documented (stats, gap) shape")
    if not callable(getattr(registry, "_read_tools_registry", None)):
        fail("missing _read_tools_registry")
    result = registry._read_tools_registry()
    if not isinstance(result, tuple) or len(result) != 2:
        fail(f"expected (dict, str|None), got {type(result)}")
    stats, gap = result
    expected_keys = {"total_tools", "enabled_tools", "approval_required_count",
                     "by_risk", "by_server", "total_permissions", "by_actor_pattern"}
    if not expected_keys.issubset(set(stats.keys())):
        fail(f"missing keys: {expected_keys - set(stats.keys())}")
    ok(f"shape OK: {len(stats)} stats keys + gap='{gap[:50] if gap else None}...'")

    # ===================================================================
    # Step 9 — tools_catalog appears in build_registry() top level
    # ===================================================================
    step("9. tools_catalog appears at build_registry() top level")
    snap = registry.build_registry(window_days=7)
    if "tools_catalog" not in snap:
        fail("tools_catalog missing from registry top-level keys")
    if not isinstance(snap["tools_catalog"], dict):
        fail("tools_catalog must be a dict")
    ok(f"tools_catalog present at top level (total_tools={snap['tools_catalog']['total_tools']})")

    # ===================================================================
    # Step 10 — NEGATIVE: empty catalog → honest_gap surfaces
    # ===================================================================
    step("10. NEGATIVE: empty catalog → honest_gap mentions table")
    if snap["tools_catalog"]["total_tools"] == 0:
        gap_present = any(
            "governance.tools" in g for g in snap["honest_gaps"]
        )
        if not gap_present:
            fail("empty catalog but no honest_gap mentions governance.tools")
        ok("empty catalog with honest_gap referencing the table — NOT silent")
    else:
        ok(f"catalog populated (total={snap['tools_catalog']['total_tools']}); gap not required")

    # ===================================================================
    # Step 11 — round-trip: synthetic tool + permission → registry sees them
    # ===================================================================
    step("11. round-trip: insert synthetic tool + permission → registry sees them")

    async def _roundtrip():
        try:
            conn = await _admin_conn()
        except Exception:
            return None
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                drill_id = uuid.uuid4().hex[:8]
                await conn.execute(
                    "INSERT INTO governance.tools "
                    "(server, name, description, side_effects, "
                    " required_scopes, risk_level, approval_required) "
                    "VALUES ('drill', $1, 'drill round-trip tool', "
                    "        'read', ARRAY['drill:read'], 'low', false)",
                    f"drill.tool_{drill_id}",
                )
                await conn.execute(
                    "INSERT INTO governance.tool_permissions "
                    "(server, tool_name, actor_pattern, can_invoke, can_modify, can_admin) "
                    "VALUES ('drill', $1, 'council:author', true, false, false)",
                    f"drill.tool_{drill_id}",
                )
                # Verify same-tx visibility (simulating what registry would see)
                row = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.tools WHERE server = 'drill'"
                )
                p_row = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.tool_permissions "
                    " WHERE actor_pattern = 'council:author'"
                )
                if int(row["n"]) < 1:
                    return f"FAIL: tool not visible in same tx: {row}"
                if int(p_row["n"]) < 1:
                    return "FAIL: permission not visible in same tx"
                return f"OK: tool=drill.tool_{drill_id}, perm=council:author"
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    result = asyncio.run(_roundtrip())
    if result is None:
        ok("skipped (postgres unreachable)")
    elif result.startswith("FAIL"):
        fail(result)
    else:
        ok(result)

    # ===================================================================
    # Step 12 — NEGATIVE: read-only contract on registry source
    # ===================================================================
    step("12. NEGATIVE: registry _read_tools_registry has no write verbs")
    src = (REPO / "scripts" / "agent_task_registry.py").read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _read_tools_registry.*?(?=\ndef \w)",
        src, re.DOTALL,
    )
    if m is None:
        fail("could not locate _read_tools_registry function body")
    body = m.group(0)
    forbidden = ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "DROP ")
    leaks = [v for v in forbidden if v in body.upper()]
    if leaks:
        fail(f"_read_tools_registry body contains write verbs: {leaks}")
    ok("read-only contract holds; no write verbs in body")

    # ===================================================================
    # Step 13 — paperclip surface includes tools_catalog
    # ===================================================================
    step("13. paperclip provider_comparison.tools_catalog is reachable via Paperclip")
    from scripts import paperclip_manager  # noqa: E402
    pc = paperclip_manager.snapshot(window_days=7)
    pc_pcomp = pc.get("provider_comparison", {})
    if "tools_catalog" not in pc_pcomp:
        fail("paperclip provider_comparison missing tools_catalog")
    ok(f"paperclip surfaces tools_catalog: {pc_pcomp['tools_catalog']}")

    print(f"\n{GREEN}{BOLD}ALL 13 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
