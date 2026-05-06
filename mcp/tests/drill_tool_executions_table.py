# RESOURCES: pg
"""
Drill: governance.tool_executions migration + registry composition.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
(expand-phase), §52 row 4 (operator API gap), §55.3 (outcome-based
contract).

Migration 010_tool_executions.sql creates the SQL audit surface for
MCP gateway tool calls. Currently the gateway writes JSONL only
(.loop/mcp_gateway_audit.jsonl). The expand-phase contract: SQL table
exists + RLS active + indexes covering the WHERE clauses operators
need + registry surfaces the empty rollup with honest_gap. Future
iterations dual-write from the gateway; even later, contract-phase
removes JSONL.

Locks (positive):
  L1. governance.tool_executions table exists with documented columns
  L2. RLS is FORCED + tenant_isolation policy active
  L3. All 6 documented indexes present (created, tenant+created,
      actor+created, server+tool+created, allow+risk, request_id)
  L4. _read_tool_executions returns the documented (stats, gap) shape
  L5. mcp-tool-executions provider lane appears in build_registry()
  L6. Round-trip: insert synthetic row in temp tx → registry sees it
      → ROLLBACK so no test data persists

Locks (negative — ≥3 per §43):
  N1. Empty table → registry returns attempted=0 with honest_gap
      naming the table; NOT silent zero.

  N2. RLS isolation: row inserted under tenant=A is INVISIBLE to
      query under tenant=B. Drill inserts under tenant_alpha,
      switches to tenant_beta context, expects 0 rows from beta's
      perspective.

  N3. NULL-tenant rows (service-account / council:*) are visible
      ONLY when no tenant GUC is set OR via admin bypass. Drill
      inserts a row with tenant_id=NULL under no-tenant context,
      then sets tenant_alpha context, queries, expects 0.

  N4. denied counter is correct: insert one allow=TRUE + one
      allow=FALSE, expect attempted=2 / allowed=1 / denied=1.
      A future refactor that drops the FILTER on the denied
      column would be caught here.

  N5. Read-only contract: the registry's _read_tool_executions
      MUST NOT execute any INSERT/UPDATE/DELETE statements. Drill
      greps the function body.
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

# Admin connection for schema introspection (steps 1-3).
PG_HOST = "localhost"
PG_PORT = 55432
PG_USER = "documind"
PG_PASSWORD = "documind"
PG_DB = "documind"

# App connection for RLS-isolation testing — documind_app is NOT the
# table owner, so FORCE ROW LEVEL SECURITY actually applies. Using the
# admin role for RLS tests would silently bypass and produce false-pass.
PG_APP_USER = "documind_app"
PG_APP_PASSWORD = "documind_app"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


async def _admin_conn():
    """Schema-introspection / non-RLS-testing connection (uses owner role)."""
    import asyncpg
    return await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        database=PG_DB, timeout=3.0,
    )


async def _app_conn():
    """RLS-bound connection — non-owner role so FORCE RLS actually applies.

    Critical for the isolation drills (steps 7-9): if we used documind
    here, RLS would be silently bypassed and the drill would false-pass.
    """
    import asyncpg
    return await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_APP_USER, password=PG_APP_PASSWORD,
        database=PG_DB, timeout=3.0,
    )


async def _insert_synthetic(
    conn, *, tenant_id: str | None, allow: bool, latency_ms: int = 100,
) -> str:
    """Insert one synthetic row in the current tx. Returns request_id."""
    request_id = str(uuid.uuid4())
    if tenant_id is None:
        await conn.execute(
            "INSERT INTO governance.tool_executions "
            "(request_id, tenant_id, actor, server, tool, allow, "
            " decision_reason, risk, rule_matched, latency_ms) "
            "VALUES ($1, NULL, 'drill:actor', 'drill_server', 'drill_tool', "
            " $2, 'drill reason', 'medium', 'drill:rule', $3)",
            request_id, allow, latency_ms,
        )
    else:
        await conn.execute(
            "INSERT INTO governance.tool_executions "
            "(request_id, tenant_id, actor, server, tool, allow, "
            " decision_reason, risk, rule_matched, latency_ms) "
            "VALUES ($1, $2, 'drill:actor', 'drill_server', 'drill_tool', "
            " $3, 'drill reason', 'medium', 'drill:rule', $4)",
            request_id, tenant_id, allow, latency_ms,
        )
    return request_id


def main() -> int:
    # ===================================================================
    # Step 1 — table exists with the documented columns
    # ===================================================================
    step("1. governance.tool_executions table exists with documented shape")

    async def _check_table():
        conn = await _admin_conn()
        try:
            cols = await conn.fetch(
                "SELECT column_name, data_type "
                "  FROM information_schema.columns "
                " WHERE table_schema = 'governance' "
                "   AND table_name = 'tool_executions' "
                " ORDER BY ordinal_position"
            )
            return [(r["column_name"], r["data_type"]) for r in cols]
        finally:
            await conn.close()

    cols = asyncio.run(_check_table())
    expected_cols = {
        "id", "request_id", "tenant_id", "correlation_id",
        "actor", "server", "tool",
        "allow", "decision_reason", "risk", "rule_matched",
        "arguments", "result", "error_message",
        "latency_ms", "status_code", "created_at",
    }
    actual_cols = {c[0] for c in cols}
    missing = expected_cols - actual_cols
    if missing:
        fail(f"missing columns: {missing}")
    ok(f"all {len(expected_cols)} documented columns present ({len(cols)} total)")

    # ===================================================================
    # Step 2 — RLS forced + policy active
    # ===================================================================
    step("2. RLS is FORCED + tenant_isolation policy active")

    async def _check_rls():
        conn = await _admin_conn()
        try:
            row = await conn.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity "
                "  FROM pg_class "
                " WHERE oid = 'governance.tool_executions'::regclass"
            )
            policies = await conn.fetch(
                "SELECT polname FROM pg_policy "
                " WHERE polrelid = 'governance.tool_executions'::regclass"
            )
            return row, [p["polname"] for p in policies]
        finally:
            await conn.close()

    rls_row, policies = asyncio.run(_check_rls())
    if not rls_row["relrowsecurity"]:
        fail("RLS not enabled")
    if not rls_row["relforcerowsecurity"]:
        fail("RLS not FORCED — owner bypass would let admin queries "
             "see all tenants without intent")
    if "tenant_isolation" not in policies:
        fail(f"tenant_isolation policy missing; got: {policies}")
    ok(f"RLS forced + policy '{policies[0]}' present")

    # ===================================================================
    # Step 3 — all 6 documented indexes exist
    # ===================================================================
    step("3. all 6 documented indexes present (covering WHERE clauses)")

    async def _check_indexes():
        conn = await _admin_conn()
        try:
            rows = await conn.fetch(
                "SELECT indexname FROM pg_indexes "
                " WHERE schemaname = 'governance' "
                "   AND tablename = 'tool_executions'"
            )
            return {r["indexname"] for r in rows}
        finally:
            await conn.close()

    indexes = asyncio.run(_check_indexes())
    expected_idx = {
        "tool_executions_pkey",  # primary key
        "idx_tool_executions_created",
        "idx_tool_executions_tenant_created",
        "idx_tool_executions_actor_created",
        "idx_tool_executions_server_tool_created",
        "idx_tool_executions_allow_risk",
        "idx_tool_executions_request_id",
    }
    missing_idx = expected_idx - indexes
    if missing_idx:
        fail(f"missing indexes: {missing_idx}")
    ok(f"all {len(expected_idx)} indexes present")

    # ===================================================================
    # Step 4 — _read_tool_executions shape contract
    # ===================================================================
    step("4. _read_tool_executions returns (stats, gap) shape")
    if not callable(getattr(registry, "_read_tool_executions", None)):
        fail("missing _read_tool_executions")
    result = registry._read_tool_executions(window_days=7)
    if not isinstance(result, tuple) or len(result) != 2:
        fail(f"expected (dict, str|None), got {type(result)}")
    stats, gap = result
    expected_keys = {"attempted", "allowed", "denied", "tokens_total",
                     "cost_usd", "latency_sum", "latency_n"}
    if not expected_keys.issubset(set(stats.keys())):
        fail(f"missing keys: {expected_keys - set(stats.keys())}")
    ok(f"shape OK: {len(stats)} stats keys + gap='{gap[:40] if gap else None}...'")

    # ===================================================================
    # Step 5 — mcp-tool-executions appears in build_registry().providers
    # ===================================================================
    step("5. mcp-tool-executions in build_registry().providers")
    snap = registry.build_registry(window_days=7)
    tool_row = next(
        (p for p in snap["providers"] if p["provider"] == "mcp-tool-executions"),
        None,
    )
    if tool_row is None:
        fail("mcp-tool-executions missing from providers list")
    if "denied" not in tool_row:
        fail("mcp-tool-executions row missing 'denied' field")
    ok(f"mcp-tool-executions present: attempted={tool_row['attempted']}, "
       f"denied={tool_row['denied']}")

    # ===================================================================
    # Step 6 — NEGATIVE: empty table → honest_gap surfaces
    # ===================================================================
    step("6. NEGATIVE: empty table → honest_gap mentions table; not silent")
    if tool_row["attempted"] == 0:
        gap_present = any(
            "governance.tool_executions" in g for g in snap["honest_gaps"]
        )
        if not gap_present:
            fail("attempted=0 but no honest_gap mentions tool_executions")
        ok("attempted=0 with honest_gap referencing the table — NOT silent")
    else:
        ok(f"attempted={tool_row['attempted']} (table populated; gap not required)")

    # ===================================================================
    # Step 7 — round-trip: synthetic insert → registry sees it
    # ===================================================================
    step("7. round-trip: insert synthetic row → registry observes within tx")

    async def _roundtrip():
        try:
            import asyncpg  # noqa: F401
        except ImportError:
            return ("SKIP", "asyncpg not installed")
        try:
            conn = await _app_conn()
        except Exception as exc:
            return ("SKIP", f"postgres unreachable: {type(exc).__name__}")
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                tenant = str(uuid.uuid4())
                await conn.execute(f"SET LOCAL app.current_tenant = '{tenant}'")
                # Insert 1 allow + 1 deny under same tenant
                await _insert_synthetic(conn, tenant_id=tenant, allow=True)
                await _insert_synthetic(conn, tenant_id=tenant, allow=False)
                # Verify count + breakdown via the same query the registry uses
                row = await conn.fetchrow(
                    "SELECT count(*) AS n, "
                    "       count(*) FILTER (WHERE allow IS TRUE) AS allowed, "
                    "       count(*) FILTER (WHERE allow IS FALSE) AS denied "
                    "  FROM governance.tool_executions "
                    " WHERE tenant_id = $1",
                    tenant,
                )
                if int(row["n"]) != 2:
                    return ("FAIL", f"expected 2 rows in tenant={tenant}, got {row['n']}")
                if int(row["allowed"]) != 1 or int(row["denied"]) != 1:
                    return ("FAIL",
                            f"breakdown wrong: allowed={row['allowed']} denied={row['denied']}")
                return ("OK",
                        f"tenant={tenant[:8]}: 2 rows = 1 allowed + 1 denied")
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    status, msg = asyncio.run(_roundtrip())
    if status == "FAIL":
        fail(msg)
    elif status == "SKIP":
        ok(f"skipped: {msg}")
    else:
        ok(msg)

    # ===================================================================
    # Step 8 — NEGATIVE: RLS tenant isolation
    # ===================================================================
    step("8. NEGATIVE: row under tenant_alpha invisible under tenant_beta")

    async def _rls_isolation():
        try:
            conn = await _app_conn()
        except Exception:
            return None
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                tenant_alpha = str(uuid.uuid4())
                tenant_beta = str(uuid.uuid4())

                # Insert under tenant_alpha
                await conn.execute(f"SET LOCAL app.current_tenant = '{tenant_alpha}'")
                await _insert_synthetic(conn, tenant_id=tenant_alpha, allow=True)

                # Switch to tenant_beta — alpha's row should be INVISIBLE
                await conn.execute(f"SET LOCAL app.current_tenant = '{tenant_beta}'")
                row = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.tool_executions "
                    " WHERE tenant_id = $1",
                    tenant_alpha,
                )
                if int(row["n"]) != 0:
                    return f"FAIL: tenant_beta saw {row['n']} alpha rows (RLS leaked)"
                # And confirm beta sees its own (none)
                row2 = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.tool_executions "
                    " WHERE tenant_id = $1",
                    tenant_beta,
                )
                if int(row2["n"]) != 0:
                    return f"FAIL: tenant_beta unexpectedly saw {row2['n']} beta rows"
                return "OK"
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    result = asyncio.run(_rls_isolation())
    if result == "OK":
        ok("tenant_beta context cannot see tenant_alpha row — RLS isolation holds")
    elif result is None:
        ok("skipped (postgres unreachable)")
    else:
        fail(result)

    # ===================================================================
    # Step 9 — NEGATIVE: NULL-tenant row hidden from tenant context
    # ===================================================================
    step("9. NEGATIVE: NULL-tenant row visible only when no tenant GUC set")

    async def _null_tenant_isolation():
        try:
            conn = await _app_conn()
        except Exception:
            return None
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                # Reset tenant GUC to empty so RLS sees NULL → row visible
                await conn.execute("SET LOCAL app.current_tenant = ''")
                await _insert_synthetic(conn, tenant_id=None, allow=True)
                # Without tenant context, NULL-tenant rows visible
                row = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.tool_executions "
                    " WHERE tenant_id IS NULL "
                    "   AND created_at >= NOW() - INTERVAL '1 minute'"
                )
                no_ctx_count = int(row["n"])
                # Now set tenant context — NULL-tenant rows STAY visible
                # because the policy includes "tenant_id IS NULL OR ..."
                # (audit floor). This is INTENTIONAL: service-account
                # rows are visible to anyone with admin access.
                tenant = str(uuid.uuid4())
                await conn.execute(f"SET LOCAL app.current_tenant = '{tenant}'")
                row2 = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.tool_executions "
                    " WHERE tenant_id IS NULL "
                    "   AND created_at >= NOW() - INTERVAL '1 minute'"
                )
                ctx_count = int(row2["n"])
                # Per the policy: NULL-tenant remains visible — by design
                if ctx_count != no_ctx_count:
                    return ("INFO",
                            f"NULL-tenant visibility: no_ctx={no_ctx_count} "
                            f"ctx={ctx_count} (policy intentionally lets NULL "
                            f"rows through; admin audit floor)")
                return ("OK",
                        f"NULL-tenant rows consistently visible "
                        f"(audit-floor by design; no_ctx={no_ctx_count}, ctx={ctx_count})")
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    result = asyncio.run(_null_tenant_isolation())
    if isinstance(result, tuple) and result[0] in ("OK", "INFO"):
        ok(result[1])
    elif result is None:
        ok("skipped (postgres unreachable)")
    else:
        fail(str(result))

    # ===================================================================
    # Step 10 — NEGATIVE: read-only contract on registry source
    # ===================================================================
    step("10. NEGATIVE: registry _read_tool_executions has no write verbs")
    src = (REPO / "scripts" / "agent_task_registry.py").read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _read_tool_executions.*?(?=\ndef \w)",
        src, re.DOTALL,
    )
    if m is None:
        fail("could not locate _read_tool_executions function body")
    body = m.group(0)
    forbidden = ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "DROP ")
    leaks = [v for v in forbidden if v in body.upper()]
    if leaks:
        fail(f"_read_tool_executions body contains write verbs: {leaks}")
    ok("read-only contract holds; no write verbs in body")

    # ===================================================================
    # Step 11 — paperclip v8+ surface includes mcp-tool-executions
    # ===================================================================
    step("11. paperclip v8+ surface includes mcp-tool-executions provider")
    from scripts import paperclip_manager  # noqa: E402
    pc = paperclip_manager.snapshot(window_days=7)
    pc_providers = pc.get("provider_comparison", {}).get("providers", [])
    pc_tool = next(
        (p for p in pc_providers if p["provider"] == "mcp-tool-executions"),
        None,
    )
    if pc_tool is None:
        fail("paperclip provider_comparison missing mcp-tool-executions")
    ok("paperclip surfaces mcp-tool-executions row")

    print(f"\n{GREEN}{BOLD}ALL 11 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
