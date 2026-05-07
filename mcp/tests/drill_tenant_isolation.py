#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for C3 — RLS coverage audit across all migrations (Phase C3).

Walks every migration file in services/agent-orchestrator-svc/migrations/,
parses out CREATE TABLE statements, and verifies each table is either:
  - tenant-scoped: declares ENABLE ROW LEVEL SECURITY + FORCE RLS +
    a tenant-isolation policy, OR
  - explicitly listed in 015_rls_audit.sql as GLOBAL_TABLES.

A new migration that adds a tenant-scoped table without RLS — or worse,
without including itself in the global list — fails this drill at
review-time, before the cross-tenant data leak ships.

Negative assertions (the structural locks):
  1. Every CREATE TABLE in a migration MUST be either RLS-protected
     or explicitly enumerated as global. No silent third state.
  2. Every RLS-protected table MUST also have FORCE ROW LEVEL SECURITY
     (otherwise BYPASSRLS roles skip the policy).
  3. Every tenant policy MUST reference current_setting('app.current_tenant')
     — the convention for how the service injects per-request tenant
     context into the connection.
  4. The GLOBAL list in 015_rls_audit.sql MUST match what the audit
     drill's enforcement loop expects (no drift between drill and
     migration documentation).

Resource tag = readonly. Pure source-level scan; no DB.

Why this drill: §41.3 + §45 ("don't BYPASSRLS to make admin endpoints
work — relax-RLS hides forgot-tenant_connection bugs"). RLS is your
last line of defence against cross-tenant leaks; a missing policy
is invisible until you ship it.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO / "services" / "agent-orchestrator-svc" / "migrations"

# Source of truth — these tables are intentionally cross-tenant.
# Match the GLOBAL_TABLES list in 015_rls_audit.sql; drift = drill fails.
KNOWN_GLOBAL_TABLES = {
    "orchestration.agent_policies",
}


def _create_tables(sql: str) -> list[str]:
    """Extract fully-qualified table names from CREATE TABLE statements."""
    return re.findall(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\.]+)",
        sql,
        flags=re.IGNORECASE,
    )


def _has_rls(sql: str, table: str) -> bool:
    return bool(re.search(
        rf"ALTER\s+TABLE\s+{re.escape(table)}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql, flags=re.IGNORECASE,
    ))


def _has_force_rls(sql: str, table: str) -> bool:
    return bool(re.search(
        rf"ALTER\s+TABLE\s+{re.escape(table)}\s+FORCE\s+ROW\s+LEVEL\s+SECURITY",
        sql, flags=re.IGNORECASE,
    ))


def _has_tenant_policy(sql: str, table: str) -> bool:
    # Look for CREATE POLICY ... ON <table> ... USING (tenant_id = current_setting...)
    pattern = (
        rf"CREATE\s+POLICY\s+\S+\s+ON\s+{re.escape(table)}.*?"
        rf"current_setting\(\s*'app\.current_tenant'"
    )
    return bool(re.search(pattern, sql, flags=re.IGNORECASE | re.DOTALL))


def main() -> int:
    print("-- 1. POSITIVE: migrations directory present --")
    assert MIGRATIONS_DIR.is_dir(), f"missing {MIGRATIONS_DIR}"
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert len(sql_files) >= 9, f"expected ≥9 migrations (incl. 015), got {len(sql_files)}"
    print(f"  ok: {len(sql_files)} migration files")

    print("-- 2. POSITIVE: 015_rls_audit.sql exists with both lists --")
    audit_file = MIGRATIONS_DIR / "015_rls_audit.sql"
    assert audit_file.exists(), f"missing {audit_file}"
    audit = audit_file.read_text(encoding="utf-8")
    assert "TENANT_SCOPED" in audit, "audit must enumerate tenant-scoped tables"
    assert "GLOBAL_TABLES" in audit, "audit must enumerate global tables"
    print("  ok: 015_rls_audit.sql declares both inventories")

    print("-- 3. POSITIVE: discover all CREATE TABLE statements across migrations --")
    all_tables: list[tuple[str, str]] = []  # (file, table)
    full_sql = ""
    for f in sql_files:
        s = f.read_text(encoding="utf-8")
        full_sql += "\n" + s
        for tbl in _create_tables(s):
            # Only consider tables in orchestration.* schema.
            if tbl.startswith("orchestration."):
                all_tables.append((f.name, tbl))
    table_set = {t for _, t in all_tables}
    print(f"  ok: discovered {len(table_set)} unique orchestration.* tables")
    for f_name, tbl in all_tables:
        print(f"    - {tbl} (declared in {f_name})")

    print("-- 4. NEGATIVE: every CREATE TABLE is RLS-protected OR in GLOBAL list --")
    leaks: list[str] = []
    for tbl in table_set:
        if tbl in KNOWN_GLOBAL_TABLES:
            continue
        if not _has_rls(full_sql, tbl):
            leaks.append(tbl)
    assert not leaks, (
        f"RLS LEAK: tenant-scoped tables without ENABLE ROW LEVEL SECURITY: {leaks}"
    )
    print("  ok: no tenant-scoped table is missing ENABLE ROW LEVEL SECURITY")

    print("-- 5. NEGATIVE: every RLS-protected table also FORCEs RLS --")
    weak_rls: list[str] = []
    for tbl in table_set:
        if tbl in KNOWN_GLOBAL_TABLES:
            continue
        if _has_rls(full_sql, tbl) and not _has_force_rls(full_sql, tbl):
            weak_rls.append(tbl)
    assert not weak_rls, (
        f"WEAK RLS: tables with ENABLE but no FORCE — BYPASSRLS roles skip "
        f"the policy: {weak_rls}"
    )
    print("  ok: every RLS table also FORCEs RLS (BYPASSRLS roles still gated)")

    print("-- 6. NEGATIVE: every tenant table has tenant_isolation policy --")
    no_policy: list[str] = []
    for tbl in table_set:
        if tbl in KNOWN_GLOBAL_TABLES:
            continue
        if not _has_tenant_policy(full_sql, tbl):
            no_policy.append(tbl)
    assert not no_policy, (
        f"MISSING POLICY: tables with RLS enabled but no tenant_isolation "
        f"policy referencing app.current_tenant: {no_policy}"
    )
    print("  ok: every tenant table has a current_setting('app.current_tenant') policy")

    print("-- 7. NEGATIVE: GLOBAL_TABLES list in drill matches 015 source --")
    # Use a specific anchor (the section header line) so we don't pick up
    # the doc-comment mention earlier in the file.
    anchor = "-- GLOBAL_TABLES (intentionally"
    parts = audit.split(anchor, 1)
    assert len(parts) == 2, f"expected anchor {anchor!r} in 015 file"
    global_block = parts[1].split("DO $$", 1)[0]
    declared_globals = set(re.findall(r"orchestration\.\w+", global_block))
    drift = KNOWN_GLOBAL_TABLES.symmetric_difference(declared_globals)
    assert not drift, (
        f"DRIFT: drill's KNOWN_GLOBAL_TABLES ≠ 015 documentation. "
        f"Symmetric diff: {drift}"
    )
    print(f"  ok: drill ↔ 015 documentation in sync ({len(declared_globals)} global tables)")

    print("-- 8. POSITIVE: 015 enforcement DO block lists all tenant-scoped tables --")
    do_block = audit.split("DO $$", 1)[1] if "DO $$" in audit else ""
    enforced = set(re.findall(r"'(\w+)'", do_block))
    expected_short = {t.split(".", 1)[1] for t in table_set if t not in KNOWN_GLOBAL_TABLES}
    missing_from_enforcement = expected_short - enforced
    assert not missing_from_enforcement, (
        f"015 DO block missing tables: {missing_from_enforcement}"
    )
    print(f"  ok: 015's runtime check covers all {len(enforced)} tenant tables")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
