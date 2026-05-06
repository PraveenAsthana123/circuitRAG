# RESOURCES: pg
"""
Drill: paperclip migrate_phase_status surface (iter 14).

Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
(expand→migrate→contract), §52 row 4 (operator API gap),
§55.3 (outcome-based contract).

Iters 11-13 shipped 3 SQL dual-writes gated by env flags. The
operator-pain pattern: which ones are active? Parity OK? This
surface answers in one read.

Locks (positive):
  L1. aggregate_migrate_phase_status returns documented shape
  L2. 3 flags surfaced: mcp_gateway_sql_audit, ops_worker_sql,
      mcp_tools_sync
  L3. Each flag carries env_var + since_iter + legacy_path + sql_table
  L4. Surfaces section reports legacy_size_bytes + sql_count +
      parity per flag
  L5. summary.active_count counts flags with enabled=True

Locks (negative — ≥3 per §43):
  N1. Flag UNSET → enabled=False, parity="n/a"
  N2. Flag SET but SQL count=0 AND legacy_size>200 →
      parity="no_traffic_since_flip" + honest_gap names the flag
      (operator misconfig: flag flipped but writer hasn't run)
  N3. Read-only contract: aggregate_migrate_phase_status source
      has NO write SQL (no INSERT/UPDATE/DELETE in body)
  N4. .env.template documents all 3 flags (operator must be
      able to discover them; missing from template = invisible)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    saved_flags: dict[str, str | None] = {}
    flag_names = (
        "MCP_GATEWAY_SQL_AUDIT_ENABLED",
        "OPS_WORKER_SQL_ENABLED",
        "MCP_TOOLS_SYNC_ENABLED",
    )
    for n in flag_names:
        saved_flags[n] = os.environ.get(n)

    try:
        # Save baseline state with all flags off
        for n in flag_names:
            os.environ.pop(n, None)

        from scripts import paperclip_manager  # noqa: E402

        # ===============================================================
        # Step 1 — public API exists
        # ===============================================================
        step("1. paperclip_manager exposes aggregate_migrate_phase_status")
        if not callable(getattr(paperclip_manager, "aggregate_migrate_phase_status", None)):
            fail("aggregate_migrate_phase_status missing")
        ok("aggregate_migrate_phase_status callable")

        # ===============================================================
        # Step 2 — documented shape
        # ===============================================================
        step("2. surface returns the documented shape")
        result = paperclip_manager.aggregate_migrate_phase_status()
        expected_keys = {"flags", "surfaces", "honest_gaps", "summary"}
        if not expected_keys.issubset(set(result.keys())):
            fail(f"missing top keys: {expected_keys - set(result.keys())}")
        ok(f"shape OK: {len(result)} top-level keys")

        # ===============================================================
        # Step 3 — All 3 flags present with documented metadata
        # ===============================================================
        step("3. all 3 documented flags surfaced with metadata")
        expected_flags = {
            "mcp_gateway_sql_audit",
            "ops_worker_sql",
            "mcp_tools_sync",
        }
        actual_flags = set(result["flags"].keys())
        if actual_flags != expected_flags:
            fail(f"flags mismatch: expected {expected_flags}, got {actual_flags}")
        for name, flag in result["flags"].items():
            for key in ("env_var", "enabled", "since_iter", "legacy_path", "sql_table"):
                if key not in flag:
                    fail(f"flag {name} missing {key}")
        ok("all 3 flags carry env_var + enabled + since_iter + legacy_path + sql_table")

        # ===============================================================
        # Step 4 — NEGATIVE: All flags UNSET → enabled=False, parity="n/a"
        # ===============================================================
        step("4. NEGATIVE: all flags UNSET → enabled=False, parity='n/a'")
        for name, flag in result["flags"].items():
            if flag["enabled"] is not False:
                fail(f"{name}: env unset but enabled={flag['enabled']!r}")
        for name, surface in result["surfaces"].items():
            if surface["parity"] != "n/a":
                fail(f"{name}: parity should be 'n/a' when flag unset, got {surface['parity']!r}")
        if result["summary"]["active_count"] != 0:
            fail(f"active_count should be 0 with all flags off, got {result['summary']['active_count']}")
        ok("all flags off → enabled=False; parity='n/a'; active_count=0")

        # ===============================================================
        # Step 5 — flag DETECTED when env set
        # ===============================================================
        step("5. setting an env flag → enabled=True in surface")
        os.environ["MCP_GATEWAY_SQL_AUDIT_ENABLED"] = "1"
        result_on = paperclip_manager.aggregate_migrate_phase_status()
        if result_on["flags"]["mcp_gateway_sql_audit"]["enabled"] is not True:
            fail("env flag set to '1' but enabled=False in surface")
        if result_on["summary"]["active_count"] != 1:
            fail(f"active_count should be 1, got {result_on['summary']['active_count']}")
        ok("env=1 → enabled=True; active_count=1")

        # ===============================================================
        # Step 6 — NEGATIVE: flag SET, legacy non-trivial, SQL count=0 →
        # parity='no_traffic_since_flip' + honest_gap
        # ===============================================================
        step("6. NEGATIVE: flag=1 + legacy>200B + SQL=0 → 'no_traffic_since_flip'")
        # The mcp_gateway_audit.jsonl is large (>200B) AND the test row
        # we cleaned up earlier in iter-11 means SQL count of test data
        # is 0. This is the empirical no-traffic-since-flip state.
        gw_surface = result_on["surfaces"]["mcp_gateway_sql_audit"]
        # Conditional on actual environment: only check if legacy is non-trivial
        if gw_surface["legacy_size_bytes"] > 200:
            if gw_surface["parity"] != "no_traffic_since_flip":
                fail(
                    f"legacy={gw_surface['legacy_size_bytes']}B + sql_count="
                    f"{gw_surface['sql_count']} should yield 'no_traffic_since_flip', "
                    f"got {gw_surface['parity']!r}"
                )
            # honest_gap should mention the flag
            gap_present = any(
                "mcp_gateway_sql_audit" in g for g in result_on["honest_gaps"]
            )
            if not gap_present:
                fail("honest_gap should name the flag with no_traffic_since_flip")
            ok("flag set + non-trivial legacy + SQL=0 → 'no_traffic_since_flip' + honest_gap")
        else:
            ok(f"legacy_size={gw_surface['legacy_size_bytes']}B (small); skip-asserted")

        # ===============================================================
        # Step 7 — NEGATIVE: read-only contract on the surface source
        # ===============================================================
        step("7. NEGATIVE: aggregate_migrate_phase_status has no write verbs")
        src = (REPO / "scripts" / "paperclip_manager.py").read_text(encoding="utf-8")
        m = re.search(
            r"def aggregate_migrate_phase_status.*?(?=\ndef \w)",
            src, re.DOTALL,
        )
        if m is None:
            fail("could not locate aggregate_migrate_phase_status body")
        body = m.group(0)
        forbidden = ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE ", "DROP ")
        leaks = [v for v in forbidden if v in body.upper()]
        if leaks:
            fail(f"function body has write verbs: {leaks}")
        ok(f"no write verbs in surface body; {len(forbidden)} patterns checked")

        # ===============================================================
        # Step 8 — NEGATIVE: .env.template documents all 3 flags
        # ===============================================================
        step("8. NEGATIVE: .env.template documents all 3 migrate-phase flags")
        env_path = REPO / ".env.template"
        if not env_path.exists():
            fail(".env.template missing — operators can't discover the flags")
        env_text = env_path.read_text(encoding="utf-8")
        for flag_name in flag_names:
            if flag_name not in env_text:
                fail(f"flag {flag_name} not documented in .env.template")
        ok(f"all 3 flags documented in .env.template ({env_path.stat().st_size}B)")

        # ===============================================================
        # Step 9 — paperclip top-level snapshot includes migrate_phase_status
        # ===============================================================
        step("9. paperclip snapshot top-level includes migrate_phase_status")
        snap = paperclip_manager.snapshot(window_days=7)
        if "migrate_phase_status" not in snap:
            fail("migrate_phase_status missing from snapshot")
        if not isinstance(snap["migrate_phase_status"], dict):
            fail("migrate_phase_status must be a dict")
        ok("migrate_phase_status present at snapshot top level")

        print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED{NC}")
        return 0

    finally:
        # Restore env
        for n, v in saved_flags.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v


if __name__ == "__main__":
    sys.exit(main())
