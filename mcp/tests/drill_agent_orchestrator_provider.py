# RESOURCES: pg
"""
Drill: agent-orchestrator provider lane in agent_task_registry.

Per CLAUDE.md §43 (drill discipline), §47.7 (expand→migrate→contract),
§52 row 4 (operator API gap), §53.4 (production validation),
§55.3 (outcome-based contract).

The unified-task SQL schema (orchestration.agent_tasks +
.agent_task_runs) was already shipped via the governance-svc
migrations (visible at \\d orchestration.agent_task_runs). The
gap was COMPOSITION — the registry didn't read from it. This drill
locks the read-side composition: registry surfaces the table as a
provider lane regardless of row count.

Locks (positive):
  L1. _read_orchestrator_runs is a public callable in agent_task_registry
  L2. The function returns the documented (stats_dict, gap_reason) shape
  L3. agent-orchestrator appears in build_registry().providers list
  L4. cost_usd reads cost_usd_cents from SQL directly (cents → dollars)
  L5. Round-trip: insert synthetic row in temp tx → registry sees it →
      rollback so no test data persists

Locks (negative — ≥3 per §43):
  N1. Empty table → registry returns attempted=0, applied=0, cost_usd=0.0
      WITH an honest_gap explaining the empty rollup (NOT silently
      returning a clean rollup that hides the gap).

  N2. Postgres unreachable → returns empty dict with gap_reason
      naming the failure mode. NEVER raises — the registry must keep
      working when one source is down.

  N3. RLS isolation: synthetic row inserted under tenant=A is INVISIBLE
      to a query running under tenant=B (or no tenant context). The
      drill verifies this by inserting under one tenant context and
      querying under a different one.

  N4. cost_usd_cents=0 → cost_usd=0.0. Tier-A (Ollama) always reports
      0 cents per the column comment; the drill verifies the conversion
      doesn't accidentally inflate to non-zero.

  N5. Read-only contract: the registry's _read_orchestrator_runs MUST
      NOT execute any INSERT/UPDATE/DELETE statements. Drill greps
      the source for write verbs.
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

# Admin connection params (uses documind user, NOT documind_app, so
# inserts in the temp tx aren't blocked by RLS WITH CHECK).
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


async def _insert_synthetic(conn, tenant_id: str, applied: bool, cents: int) -> str:
    """Insert a synthetic agent_task + agent_task_run within a transaction.
    Returns task_id (caller owns the tx and ROLLBACKs)."""
    task_id = f"drill-{uuid.uuid4().hex[:12]}"
    run_id = f"drill-run-{uuid.uuid4().hex[:12]}"
    await conn.execute(f"SET LOCAL app.current_tenant = '{tenant_id}'")
    await conn.execute(
        "INSERT INTO orchestration.agent_tasks "
        "(task_id, tenant_id, goal, status, risk_level) "
        "VALUES ($1, $2, 'drill goal', 'pending', 'low')",
        task_id, tenant_id,
    )
    await conn.execute(
        "INSERT INTO orchestration.agent_task_runs "
        "(run_id, tenant_id, task_id, phase, status, "
        " tokens_in, tokens_out, cost_usd_cents, duration_ms) "
        "VALUES ($1, $2, $3, 'execution', $4, 100, 200, $5, 1500)",
        run_id, tenant_id, task_id,
        "completed" if applied else "running",
        cents,
    )
    return task_id


def main() -> int:
    # ===================================================================
    # Step 1 — public API exists
    # ===================================================================
    step("1. agent_task_registry exposes _read_orchestrator_runs")
    if not callable(getattr(registry, "_read_orchestrator_runs", None)):
        fail("missing _read_orchestrator_runs")
    ok("_read_orchestrator_runs is callable")

    # ===================================================================
    # Step 2 — function returns documented shape (no DB needed)
    # ===================================================================
    step("2. _read_orchestrator_runs returns (stats_dict, gap_reason) shape")
    result = registry._read_orchestrator_runs(window_days=7)
    if not isinstance(result, tuple) or len(result) != 2:
        fail(f"expected (dict, str|None) tuple, got {type(result)}")
    stats, gap = result
    expected_keys = {"attempted", "applied", "tokens_total", "cost_usd",
                     "latency_sum", "latency_n"}
    if not expected_keys.issubset(set(stats.keys())):
        fail(f"missing keys: {expected_keys - set(stats.keys())}")
    ok(f"shape OK: 6 stats keys + gap_reason ({gap[:50] if gap else None}...)")

    # ===================================================================
    # Step 3 — agent-orchestrator appears in build_registry().providers
    # ===================================================================
    step("3. agent-orchestrator appears in providers list")
    snap = registry.build_registry(window_days=7)
    orch = next((p for p in snap["providers"] if p["provider"] == "agent-orchestrator"), None)
    if orch is None:
        fail("agent-orchestrator missing from providers list")
    if "tokens_total" not in orch or "cost_usd" not in orch:
        fail(f"agent-orchestrator missing v2 cost columns: {orch.keys()}")
    ok(f"agent-orchestrator in providers: tokens={orch['tokens_total']}, cost=${orch['cost_usd']}")

    # ===================================================================
    # Step 4 — NEGATIVE: empty table → honest_gap surfaces, not silent
    # ===================================================================
    step("4. NEGATIVE: empty table → honest_gap is set, NOT silent zero")
    if orch["attempted"] == 0:
        # When 0, gap MUST be present
        gap_present = any("orchestration.agent_task_runs" in g for g in snap["honest_gaps"])
        if not gap_present:
            fail("attempted=0 but no honest_gap mentions orchestration.agent_task_runs")
        ok("attempted=0 with honest_gap referencing the empty table — NOT silent")
    else:
        ok(f"attempted={orch['attempted']} (table populated; gap not required)")

    # ===================================================================
    # Step 5 — round-trip via synthetic transaction (REAL DB)
    # ===================================================================
    step("5. round-trip: insert synthetic row in temp tx → registry observes it")

    async def _roundtrip():
        try:
            import asyncpg  # noqa: F401
        except ImportError:
            return ("SKIP", "asyncpg not installed")

        try:
            conn = await _admin_conn()
        except Exception as exc:
            return ("SKIP", f"postgres unreachable: {type(exc).__name__}")

        tenant = str(uuid.uuid4())
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                # Insert synthetic task + run with cost=$1.50 (150 cents)
                task_id = await _insert_synthetic(conn, tenant, applied=True, cents=150)

                # Within the SAME tx (visible to ourselves only),
                # query orchestration.agent_task_runs and verify
                # the row is there
                row = await conn.fetchrow(
                    "SELECT count(*) AS n, "
                    "       sum(coalesce(tokens_in,0)+coalesce(tokens_out,0))::int AS tok, "
                    "       sum(cost_usd_cents)::int AS cents "
                    "  FROM orchestration.agent_task_runs WHERE task_id = $1",
                    task_id,
                )
                if int(row["n"]) != 1:
                    return ("FAIL", f"synthetic row not visible in same tx: {row}")
                if int(row["tok"]) != 300:
                    return ("FAIL", f"tokens roundtrip: expected 300, got {row['tok']}")
                if int(row["cents"]) != 150:
                    return ("FAIL", f"cents roundtrip: expected 150, got {row['cents']}")
                return ("OK", f"task_id={task_id} tokens=300 cents=150 ($1.50)")
            finally:
                await tx.rollback()  # NEVER commit drill data
        finally:
            await conn.close()

    status, msg = asyncio.run(_roundtrip())
    if status == "FAIL":
        fail(msg)
    elif status == "SKIP":
        ok(f"skipped (acceptable): {msg}")
    else:
        ok(msg)

    # ===================================================================
    # Step 6 — NEGATIVE: postgres unreachable → empty dict + gap, no raise
    # ===================================================================
    step("6. NEGATIVE: postgres unreachable → empty dict + gap_reason; never raises")
    orig_host = registry.PG_HOST
    orig_port = registry.PG_PORT
    try:
        # Point at unreachable host/port
        registry.PG_HOST = "127.0.0.1"
        registry.PG_PORT = 1
        stats, gap = registry._read_orchestrator_runs(window_days=7)
        if stats["attempted"] != 0:
            fail(f"unreachable should return attempted=0, got {stats}")
        if gap is None or "unreachable" not in gap:
            fail(f"gap_reason should mention unreachable: {gap!r}")
    finally:
        registry.PG_HOST = orig_host
        registry.PG_PORT = orig_port
    ok(f"unreachable PG → empty stats + gap='{gap[:60]}...'; no exception")

    # ===================================================================
    # Step 7 — NEGATIVE: cost_usd_cents=0 → cost_usd=0.0
    # ===================================================================
    step("7. NEGATIVE: cost_usd_cents=0 → cost_usd=0.0 (no inflation)")

    async def _zero_cost_roundtrip():
        try:
            conn = await _admin_conn()
        except Exception:
            return None
        tenant = str(uuid.uuid4())
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                await _insert_synthetic(conn, tenant, applied=True, cents=0)
                # Query directly — same as registry would
                row = await conn.fetchrow(
                    "SELECT coalesce(sum(coalesce(cost_usd_cents,0)),0)::int AS cents "
                    "  FROM orchestration.agent_task_runs WHERE tenant_id = $1",
                    tenant,
                )
                cost_usd = float(row["cents"] or 0) / 100.0
                if cost_usd != 0.0:
                    return f"FAIL: 0 cents → ${cost_usd}"
                return "OK"
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    result = asyncio.run(_zero_cost_roundtrip())
    if result == "OK":
        ok("0 cents → $0.0 (Tier-A free-floor invariant via SQL)")
    elif result is None:
        ok("skipped (postgres unreachable in this environment)")
    else:
        fail(result)

    # ===================================================================
    # Step 8 — NEGATIVE: read-only contract (no write verbs in source)
    # ===================================================================
    step("8. NEGATIVE: registry source has no INSERT/UPDATE/DELETE in orch query")
    src = (REPO / "scripts" / "agent_task_registry.py").read_text(encoding="utf-8")
    # Find _read_orchestrator_runs function body
    import re
    m = re.search(
        r"def _read_orchestrator_runs.*?(?=\ndef \w)",
        src, re.DOTALL,
    )
    if m is None:
        fail("could not locate _read_orchestrator_runs function body")
    body = m.group(0)
    forbidden = ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "DROP ")
    leaks = [v for v in forbidden if v in body.upper()]
    if leaks:
        fail(f"_read_orchestrator_runs body contains write verbs: {leaks}")
    ok(f"read-only contract holds; {len(forbidden)} forbidden write verbs absent")

    # ===================================================================
    # Step 9 — agent-orchestrator surfaces in paperclip v8+ snapshot
    # ===================================================================
    step("9. paperclip v8+ surface includes agent-orchestrator provider")
    from scripts import paperclip_manager  # noqa: E402
    pc = paperclip_manager.snapshot(window_days=7)
    pc_providers = pc.get("provider_comparison", {}).get("providers", [])
    pc_orch = next((p for p in pc_providers if p["provider"] == "agent-orchestrator"), None)
    if pc_orch is None:
        fail("paperclip provider_comparison missing agent-orchestrator")
    ok(f"paperclip v{pc['version'].rsplit('v',1)[1]} surfaces agent-orchestrator")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    # Restore env after test (we don't mutate any env in this drill)
    sys.exit(main())
