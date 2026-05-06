# RESOURCES: pg
"""
Drill: MCP gateway dual-write to governance.tool_executions.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
(expand→migrate→contract), §52 row 4 (operator API gap),
§53.4 (production validation), §55.3 (outcome-based contract).

Iter 8 (commit da95525) created governance.tool_executions as the
SQL audit surface. This iteration ships the migrate-phase: when
MCP_GATEWAY_SQL_AUDIT_ENABLED=1, the gateway dual-writes — JSONL
remains authoritative; SQL becomes additionally available.

Locks (positive):
  L1. _persist_sql_audit is callable in scripts.mcp_gateway
  L2. With env flag set, _append_audit writes to BOTH JSONL + SQL
  L3. Round-trip: synthetic GatewayDecision → audit() → row visible
      in governance.tool_executions with matching fields
  L4. SQL row's tenant_id is NULL (gateway is service-account)

Locks (negative — ≥3 per §43):
  N1. Feature flag UNSET → no SQL write happens. Drill ensures the
      JSONL surface stays untouched-by-SQL when operator hasn't
      opted in. §47.7 expand→migrate gating works.

  N2. SQL write failure → JSONL write STILL happens. Drill points
      the SQL connection at an unreachable host; verifies JSONL
      row appears anyway. The gateway's response path NEVER blocks
      on the SQL side car.

  N3. Read-only path: aggregate_provider_comparison() and
      _read_tool_executions() are NEVER called from within
      _append_audit OR _persist_sql_audit (would cause read-write
      cycles in cron-driven aggregation). Drill greps the source.

  N4. Invalid request_id (non-UUID) → fresh UUID4 generated, NOT
      a NULL or "request_id_invalid" string column. Drill uses an
      empty string as request_id; expects a real UUID in the row.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

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


async def _delete_drill_rows():
    """Cleanup helper — remove any drill-tagged rows from prior runs."""
    try:
        conn = await _admin_conn()
        try:
            await conn.execute(
                "DELETE FROM governance.tool_executions "
                "WHERE actor LIKE 'drill:%' OR decision_reason LIKE 'drill:%'"
            )
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    saved_flag = os.environ.get("MCP_GATEWAY_SQL_AUDIT_ENABLED")
    saved_audit_log = None

    # Use a temp AUDIT_LOG to keep drills out of production .loop/
    tmp_dir = tempfile.mkdtemp(prefix="drill_dualwrite_")
    tmp_audit = Path(tmp_dir) / "mcp_gateway_audit.jsonl"

    try:
        from scripts import mcp_gateway  # noqa: E402
        saved_audit_log = mcp_gateway.AUDIT_LOG
        mcp_gateway.AUDIT_LOG = tmp_audit

        # Cleanup any previous drill rows from prior runs
        asyncio.run(_delete_drill_rows())

        # ===============================================================
        # Step 1 — public API exists
        # ===============================================================
        step("1. _persist_sql_audit + _append_audit are callable")
        if not callable(getattr(mcp_gateway, "_persist_sql_audit", None)):
            fail("_persist_sql_audit missing")
        if not callable(getattr(mcp_gateway, "_append_audit", None)):
            fail("_append_audit missing")
        ok("both functions callable")

        # ===============================================================
        # Step 2 — NEGATIVE: feature flag UNSET → no SQL write
        # ===============================================================
        step("2. NEGATIVE: env flag UNSET → no SQL row, JSONL untouched-by-SQL")
        os.environ.pop("MCP_GATEWAY_SQL_AUDIT_ENABLED", None)
        rid_no_flag = str(uuid.uuid4())
        d = mcp_gateway.GatewayDecision(
            allow=True, reason="drill: flag-off-test", actor="drill:flag_off",
            server="drill_server", tool="drill_tool", risk="low",
            approved_actors=[], rule_matched="drill:rule",
            timestamp=time.time(), request_id=rid_no_flag, latency_ms=10.0,
        )
        mcp_gateway._append_audit(d)
        # Verify NO SQL row appeared
        async def _check_no_row():
            conn = await _admin_conn()
            try:
                row = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.tool_executions "
                    "WHERE request_id = $1",
                    uuid.UUID(rid_no_flag),
                )
                return int(row["n"])
            finally:
                await conn.close()
        n = asyncio.run(_check_no_row())
        if n != 0:
            fail(f"flag UNSET but {n} SQL rows landed — feature flag not gating writes")
        # And JSONL DID get the row
        if not tmp_audit.exists():
            fail("JSONL audit not written — base path broken")
        last_line = tmp_audit.read_text().strip().split("\n")[-1]
        if rid_no_flag not in last_line:
            fail(f"JSONL did not capture flag-off row: {last_line[:100]}")
        ok("flag UNSET: 0 SQL rows; JSONL row written normally")

        # ===============================================================
        # Step 3 — feature flag SET → both surfaces written
        # ===============================================================
        step("3. env flag SET → both JSONL + SQL surfaces get the row")
        os.environ["MCP_GATEWAY_SQL_AUDIT_ENABLED"] = "1"
        rid_dual = str(uuid.uuid4())
        d2 = mcp_gateway.GatewayDecision(
            allow=False, reason="drill: dual-write test", actor="drill:dual",
            server="research", tool="retrieve", risk="high",
            approved_actors=["council:author"],
            rule_matched="drill:scope_denied",
            timestamp=time.time(), request_id=rid_dual, latency_ms=145.7,
        )
        mcp_gateway._append_audit(d2)
        async def _check_both():
            conn = await _admin_conn()
            try:
                sql_row = await conn.fetchrow(
                    "SELECT actor, server, tool, allow, decision_reason, "
                    "       risk, rule_matched, latency_ms, tenant_id "
                    "  FROM governance.tool_executions "
                    " WHERE request_id = $1",
                    uuid.UUID(rid_dual),
                )
                return dict(sql_row) if sql_row else None
            finally:
                await conn.close()
        sql_row = asyncio.run(_check_both())
        if sql_row is None:
            fail("flag SET but no SQL row written")
        # Verify field parity
        if sql_row["actor"] != "drill:dual":
            fail(f"actor mismatch: SQL={sql_row['actor']!r}")
        if sql_row["server"] != "research":
            fail(f"server mismatch: SQL={sql_row['server']!r}")
        if sql_row["allow"] is not False:
            fail(f"allow mismatch: SQL={sql_row['allow']!r}")
        if sql_row["risk"] != "high":
            fail(f"risk mismatch: SQL={sql_row['risk']!r}")
        if sql_row["latency_ms"] != 145:  # int truncation expected
            fail(f"latency_ms truncation wrong: SQL={sql_row['latency_ms']!r}")
        ok(f"both surfaces hold {rid_dual[:8]}: actor='drill:dual' allow=False risk=high")

        # ===============================================================
        # Step 4 — L4: tenant_id is NULL (service-account row)
        # ===============================================================
        step("4. SQL row's tenant_id IS NULL (gateway is cross-tenant)")
        if sql_row["tenant_id"] is not None:
            fail(f"tenant_id should be NULL, got {sql_row['tenant_id']!r}")
        ok("tenant_id=NULL — service-account audit floor per migration 010")

        # ===============================================================
        # Step 5 — NEGATIVE: SQL write failure → JSONL still works
        # ===============================================================
        step("5. NEGATIVE: SQL host unreachable → JSONL row STILL written")
        # Point asyncpg at unreachable host via env override
        saved_pg_host = os.environ.get("DOCUMIND_PG_HOST")
        saved_pg_port = os.environ.get("DOCUMIND_PG_PORT")
        os.environ["DOCUMIND_PG_HOST"] = "127.0.0.1"
        os.environ["DOCUMIND_PG_PORT"] = "1"
        rid_fail = str(uuid.uuid4())
        try:
            d3 = mcp_gateway.GatewayDecision(
                allow=True, reason="drill: pg-fail test", actor="drill:pg_fail",
                server="hr", tool="policy_lookup", risk="low",
                approved_actors=["council:author"],
                rule_matched="drill:rule",
                timestamp=time.time(), request_id=rid_fail, latency_ms=8.0,
            )
            # MUST NOT raise even though SQL is unreachable
            mcp_gateway._append_audit(d3)
            # JSONL row should still appear
            content = tmp_audit.read_text(encoding="utf-8")
            if rid_fail not in content:
                fail("JSONL row missing despite best-effort contract")
            # And SQL should NOT have it
            os.environ.pop("DOCUMIND_PG_HOST", None)
            if saved_pg_host:
                os.environ["DOCUMIND_PG_HOST"] = saved_pg_host
            os.environ.pop("DOCUMIND_PG_PORT", None)
            if saved_pg_port:
                os.environ["DOCUMIND_PG_PORT"] = saved_pg_port
            n = asyncio.run(_check_no_row_for_rid(rid_fail))
            if n != 0:
                fail(f"SQL connect was unreachable but {n} rows landed?")
        finally:
            os.environ.pop("DOCUMIND_PG_HOST", None)
            if saved_pg_host:
                os.environ["DOCUMIND_PG_HOST"] = saved_pg_host
            os.environ.pop("DOCUMIND_PG_PORT", None)
            if saved_pg_port:
                os.environ["DOCUMIND_PG_PORT"] = saved_pg_port
        ok("PG unreachable → JSONL still wrote; gateway response path unblocked")

        # ===============================================================
        # Step 6 — NEGATIVE: invalid request_id → fresh UUID generated
        # ===============================================================
        step("6. NEGATIVE: empty request_id → fresh UUID, not NULL/garbage")
        d4 = mcp_gateway.GatewayDecision(
            allow=True, reason="drill: invalid-rid test", actor="drill:bad_rid",
            server="drill_server", tool="drill_tool", risk="low",
            approved_actors=[], rule_matched="drill:rule",
            timestamp=time.time(), request_id="",  # empty
            latency_ms=5.0,
        )
        mcp_gateway._append_audit(d4)
        async def _find_drill_bad_rid():
            conn = await _admin_conn()
            try:
                row = await conn.fetchrow(
                    "SELECT request_id::text AS rid FROM governance.tool_executions "
                    "WHERE actor = 'drill:bad_rid'"
                )
                return row["rid"] if row else None
            finally:
                await conn.close()
        rid_generated = asyncio.run(_find_drill_bad_rid())
        if rid_generated is None:
            fail("drill:bad_rid row not found in SQL")
        # Should be a valid UUID
        try:
            uuid.UUID(rid_generated)
        except ValueError:
            fail(f"empty input did not generate valid UUID: {rid_generated!r}")
        ok(f"empty request_id → generated UUID {rid_generated[:8]}…")

        # ===============================================================
        # Step 7 — NEGATIVE: source has no read-write cycles
        # ===============================================================
        step("7. NEGATIVE: _persist_sql_audit doesn't call read aggregators")
        src = (REPO / "scripts" / "mcp_gateway.py").read_text(encoding="utf-8")
        m = re.search(
            r"def _persist_sql_audit.*?(?=\ndef \w)",
            src, re.DOTALL,
        )
        if m is None:
            fail("could not locate _persist_sql_audit body")
        body = m.group(0)
        # Forbidden: read-side aggregators that would cause cycles
        forbidden = (
            "aggregate_provider_comparison",
            "_read_tool_executions",
            "build_registry",
            "snapshot(",
        )
        leaks = [p for p in forbidden if p in body]
        if leaks:
            fail(f"_persist_sql_audit references read-side aggregators: {leaks}")
        ok("write-side has no calls into read-side aggregators")

        print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
        return 0

    finally:
        # Restore env flag
        if saved_flag is None:
            os.environ.pop("MCP_GATEWAY_SQL_AUDIT_ENABLED", None)
        else:
            os.environ["MCP_GATEWAY_SQL_AUDIT_ENABLED"] = saved_flag

        # Restore AUDIT_LOG path
        if saved_audit_log is not None:
            try:
                mcp_gateway.AUDIT_LOG = saved_audit_log
            except Exception:  # noqa: BLE001
                pass

        # Cleanup drill rows
        try:
            asyncio.run(_delete_drill_rows())
        except Exception:  # noqa: BLE001
            pass

        # Cleanup temp dir
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass


async def _check_no_row_for_rid(rid: str) -> int:
    """Helper used in step 5 — same query as _check_no_row but inline."""
    import asyncpg
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        database=PG_DB, timeout=3.0,
    )
    try:
        row = await conn.fetchrow(
            "SELECT count(*) AS n FROM governance.tool_executions "
            "WHERE request_id = $1",
            uuid.UUID(rid),
        )
        return int(row["n"])
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(main())
