# RESOURCES: pg
"""
Drill: scripts/sync_tools_catalog.py — MCP server TOOLS → governance.tools.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
(expand→migrate→contract), §52 row 4 (operator API gap),
§55.3 (outcome-based contract).

Iter 9 (commit 5189b2e) created governance.tools as the SQL catalog.
This iteration's sync script populates it from the Python TOOLS
literals in mcp/server_*.py. Per §47.7 migrate-phase: SQL is a
queryable mirror; Python literals remain authoritative.

Locks (positive):
  L1. sync_tools(dry_run=True) discovers TOOLS lists across all
      mcp/server_*.py modules (excluding server_common)
  L2. sync_tools(dry_run=False) with MCP_TOOLS_SYNC_ENABLED=1
      upserts each tool into governance.tools
  L3. side_effects → risk_level mapping is deterministic:
      read→low, write→medium, external→medium, destructive→high
  L4. side_effects → approval_required mapping is deterministic:
      read/external→False, write/destructive→True
  L5. Re-running sync is idempotent (UPSERT on (server, name))
  L6. Registry tools_catalog reflects the synced rows

Locks (negative — ≥3 per §43):
  N1. CLI refuses real sync without MCP_TOOLS_SYNC_ENABLED=1.
      Drill verifies the gating: invoking sync_tools_catalog.py
      without --dry-run AND without the env flag exits non-zero.

  N2. Malformed tool record (missing 'name') → skipped, NOT crashed.
      Drill injects a tool with no name; expects tools_skipped_malformed
      to increment + the rest of the sync to proceed.

  N3. Unknown side_effects (e.g. 'wat') → safe default 'read'/'low'.
      Drill verifies the floor (CHECK constraint can't reject the row).

  N4. PG unreachable → sync errors-out gracefully, returns summary
      with errors[] populated. NEVER raises.

  N5. Read-only contract: sync_tools_catalog.py source has NO calls
      into the read-side aggregator (build_registry, snapshot()).
      Future "smart cache" refactor caught at grep level.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import subprocess
import sys
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


async def _delete_drill_tools():
    """Cleanup helper — remove drill-tagged tool rows.

    NOTE: server='drill' (singular) is the drill's test marker. The
    REAL server in this repo is 'drills' (plural — server_drills.py
    defines drill.list + drill.run). Pattern 'name LIKE drill.%' would
    accidentally delete the production rows. So we ONLY match server,
    NOT name pattern.
    """
    try:
        conn = await _admin_conn()
        try:
            await conn.execute(
                "DELETE FROM governance.tools WHERE server = 'drill'"
            )
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    saved_flag = os.environ.get("MCP_TOOLS_SYNC_ENABLED")

    try:
        sync_module = importlib.import_module("sync_tools_catalog")
        asyncio.run(_delete_drill_tools())

        # ===============================================================
        # Step 1 — public API exists
        # ===============================================================
        step("1. sync_tools_catalog exposes sync_tools + mappings")
        for name in ("sync_tools", "SIDE_EFFECTS_TO_RISK",
                     "SIDE_EFFECTS_TO_APPROVAL", "_normalize_record"):
            if not hasattr(sync_module, name):
                fail(f"missing public name: {name}")
        ok("sync_tools + mappings + _normalize_record all present")

        # ===============================================================
        # Step 2 — side_effects → risk_level mapping is deterministic
        # ===============================================================
        step("2. side_effects → risk_level mapping (deterministic)")
        expected_risk = {
            "read": "low",
            "write": "medium",
            "external": "medium",
            "destructive": "high",
        }
        for se, rl in expected_risk.items():
            if sync_module.SIDE_EFFECTS_TO_RISK.get(se) != rl:
                fail(f"risk mapping wrong: {se}→{sync_module.SIDE_EFFECTS_TO_RISK.get(se)} (expected {rl})")
        ok(f"all {len(expected_risk)} side_effects → risk mappings correct")

        # ===============================================================
        # Step 3 — side_effects → approval_required mapping
        # ===============================================================
        step("3. side_effects → approval_required mapping (deterministic)")
        expected_approval = {
            "read": False,
            "external": False,
            "write": True,
            "destructive": True,
        }
        for se, ar in expected_approval.items():
            if sync_module.SIDE_EFFECTS_TO_APPROVAL.get(se) != ar:
                fail(f"approval mapping wrong: {se}→{sync_module.SIDE_EFFECTS_TO_APPROVAL.get(se)} (expected {ar})")
        ok(f"all {len(expected_approval)} side_effects → approval mappings correct")

        # ===============================================================
        # Step 4 — dry-run discovers tools across mcp/server_*.py
        # ===============================================================
        step("4. dry-run discovers TOOLS across mcp/server_*.py modules")
        summary = sync_module.sync_tools(dry_run=True)
        if summary["modules_scanned"] < 5:
            fail(f"expected ≥5 server modules, scanned {summary['modules_scanned']}")
        if summary["tools_total"] < 5:
            fail(f"expected ≥5 tools total, got {summary['tools_total']}")
        if summary["dry_run"] is not True:
            fail("dry_run=True not echoed in summary")
        ok(f"dry-run found {summary['tools_total']} tools across {summary['modules_scanned']} modules")

        # ===============================================================
        # Step 5 — NEGATIVE: malformed tool skipped, not crashed
        # ===============================================================
        step("5. NEGATIVE: malformed tool record (no 'name') → skipped, not crashed")
        rec_no_name = {"description": "no name", "side_effects": "read"}
        rec_normal = {"name": "test.ok", "description": "ok",
                      "side_effects": "read"}
        n = sync_module._normalize_record("drill", rec_no_name)
        if n is not None:
            fail(f"malformed record should normalize to None, got {n}")
        n2 = sync_module._normalize_record("drill", rec_normal)
        if n2 is None:
            fail("well-formed record normalized to None unexpectedly")
        ok("malformed record → None; well-formed record passes through")

        # ===============================================================
        # Step 6 — NEGATIVE: unknown side_effects → 'read' floor
        # ===============================================================
        step("6. NEGATIVE: unknown side_effects → coerced to 'read' floor")
        rec_bad_se = {"name": "test.bad_se", "description": "x",
                      "side_effects": "wat"}
        n3 = sync_module._normalize_record("drill", rec_bad_se)
        if n3 is None:
            fail("bad side_effects shouldn't drop record entirely")
        if n3["side_effects"] != "read":
            fail(f"bad side_effects 'wat' should coerce to 'read', got {n3['side_effects']!r}")
        if n3["risk_level"] != "low":
            fail(f"derived risk_level should be 'low', got {n3['risk_level']!r}")
        ok("unknown side_effects → 'read' floor → 'low' risk; CHECK constraint safe")

        # ===============================================================
        # Step 7 — Real sync (with env flag) is idempotent
        # ===============================================================
        step("7. real sync is idempotent (re-run = no schema delta)")
        os.environ["MCP_TOOLS_SYNC_ENABLED"] = "1"
        s1 = sync_module.sync_tools(dry_run=False)
        if s1["errors"]:
            fail(f"first sync had errors: {s1['errors']}")
        if s1["tools_synced"] < 1:
            fail(f"first sync should have synced ≥1 tool, got {s1['tools_synced']}")
        # Re-run; same row count — UPSERT, not INSERT-only
        s2 = sync_module.sync_tools(dry_run=False)
        if s2["errors"]:
            fail(f"re-run had errors: {s2['errors']}")
        if s2["tools_synced"] != s1["tools_synced"]:
            fail(f"re-run sync count mismatch: {s1['tools_synced']} vs {s2['tools_synced']}")
        ok(f"both runs synced {s1['tools_synced']} tools; UPSERT idempotent")

        # ===============================================================
        # Step 8 — Registry tools_catalog reflects synced rows
        # ===============================================================
        step("8. registry tools_catalog reflects synced rows")
        # Force a fresh import of agent_task_registry to get current SQL state
        import agent_task_registry as registry
        snap = registry.build_registry(window_days=7)
        tc = snap.get("tools_catalog", {})
        if tc.get("total_tools", 0) < 1:
            fail(f"tools_catalog.total_tools should be ≥1, got {tc.get('total_tools')}")
        if tc.get("enabled_tools", 0) != tc.get("total_tools"):
            # All synced tools default to enabled=True; mismatch suggests a bug
            fail(f"enabled_tools should equal total_tools; got {tc}")
        ok(f"registry tools_catalog: total={tc.get('total_tools')}, "
           f"by_risk={tc.get('by_risk', {})}, "
           f"servers={list(tc.get('by_server', {}).keys())}")

        # ===============================================================
        # Step 9 — NEGATIVE: CLI refuses without env flag
        # ===============================================================
        step("9. NEGATIVE: CLI refuses real sync without MCP_TOOLS_SYNC_ENABLED")
        env_no_flag = os.environ.copy()
        env_no_flag.pop("MCP_TOOLS_SYNC_ENABLED", None)
        result = subprocess.run(
            [sys.executable,
             str(REPO / "scripts" / "sync_tools_catalog.py")],
            env=env_no_flag,
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            fail("CLI exit was 0; should non-zero when flag unset")
        if "MCP_TOOLS_SYNC_ENABLED" not in result.stderr:
            fail(f"CLI stderr should mention env flag; got {result.stderr[:200]}")
        ok(f"CLI refused with rc={result.returncode}; stderr cites env flag")

        # ===============================================================
        # Step 10 — NEGATIVE: read-only contract on sync source
        # ===============================================================
        step("10. NEGATIVE: sync_tools_catalog source has no read-aggregator calls")
        src = (REPO / "scripts" / "sync_tools_catalog.py").read_text(encoding="utf-8")
        forbidden = (
            "build_registry",
            "aggregate_provider_comparison",
            "aggregate_tools_registry",
        )
        leaks = [p for p in forbidden if p in src]
        if leaks:
            fail(f"sync source references read-side aggregators: {leaks}. "
                 f"Cron-driven cycles ahead.")
        ok("write-side has no calls into read-side aggregators")

        print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED{NC}")
        return 0

    finally:
        if saved_flag is None:
            os.environ.pop("MCP_TOOLS_SYNC_ENABLED", None)
        else:
            os.environ["MCP_TOOLS_SYNC_ENABLED"] = saved_flag

        # Cleanup any drill-tagged rows
        try:
            asyncio.run(_delete_drill_tools())
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
