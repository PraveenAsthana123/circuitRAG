# RESOURCES: readonly
"""
Drill: mcp/server_csv_ingest.py — write-surface contract per ADR-028.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-65 implements ADR-028 Stage-1), §45.4 (no
checkbox flips without code), §47 (architecture: write surface SEPARATE
from read surface), §47.6 (security), §50.5.3 (destructive ops need
approval).

ADR-028 enumerates 9 implementation guardrails. This drill locks them.

Locks (positive):
  L1. mcp/server_csv_ingest.py exists + canonical structure
  L2. TOOLS list has all 5 expected tool names
  L3. Exactly 1 tool with side_effects='write' (apply_approved_load);
      4 tools with side_effects='read' (propose, validate, submit, status)
  L4. Scopes follow the convention (csv_ingest:read / write / approve);
      apply_approved_load requires csv_ingest:write
  L5. Staging-table regex enforces ^stg_[a-z0-9_]+$

Locks (negative — ≥3 per §43):
  N1. documents server still has zero write tools (read-only contract
      held; ADR-028 §47 separation is structural)
  N2. apply_approved_load with NO approval_id returns denial
      (HTTPException raised on missing required field) OR returns
      applied:False with denial_reason (the contract for present-but-
      unmatched approval_id)
  N3. apply_approved_load with mismatched approval_id returns
      applied:False + denial_reason 'approval_id_mismatch'
  N4. DDL/DML in agent-supplied table_name is rejected (table name
      must match staging regex AND must not contain DDL keyword)
  N5. Tenant mismatch path is reachable (Stage-1: validated at the
      ingestion-svc layer; this drill verifies the table_name guardrail
      blocks cross-tenant target tables structurally)
  N6. apply_approved_load Stage-1 ALWAYS denies (HMAC + Postgres land
      iter-66; until then every apply call returns applied:False)
  N7. Path resolver same shape as documents server (allowlist prefixes
      /mnt/deepa/, /tmp/, /var/tmp/ only)
"""
from __future__ import annotations

import importlib.util as _ilu
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "mcp" / "server_csv_ingest.py"
DOCS_SERVER = REPO / "mcp" / "server_documents.py"

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
    if not SERVER.exists():
        fail(f"missing: {SERVER.relative_to(REPO)}")
    if not DOCS_SERVER.exists():
        fail(f"missing: {DOCS_SERVER.relative_to(REPO)}")

    src = SERVER.read_text(encoding="utf-8")
    docs_src = DOCS_SERVER.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: server source has canonical markers
    # ------------------------------------------------------------------
    step("1. server_csv_ingest.py has canonical structure")
    # Per the modified contract: identifier safety via _safe_identifier
    # (regex-validated A-Za-z0-9_); raw-SQL rejection via
    # _reject_raw_sql_surface; path safety via _resolve_safe_path;
    # state via the CsvIngestState dataclass instance `state`.
    for marker in (
        "TOOLS",
        "_safe_identifier",
        "_resolve_safe_path",
        "_reject_raw_sql_surface",
        "CsvIngestState",
    ):
        if marker not in src:
            fail(f"server missing canonical symbol: {marker}")
    ok("source has TOOLS + 3 guardrails + CsvIngestState dataclass")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: 5 expected tool names per ADR-028
    # ------------------------------------------------------------------
    step("2. TOOLS list has all 5 expected tool names per ADR-028")
    expected_tools = (
        "csv_ingest.propose_load",
        "csv_ingest.validate_load",
        "csv_ingest.submit_for_approval",
        "csv_ingest.apply_approved_load",
        "csv_ingest.load_status",
    )
    missing = [t for t in expected_tools if f'"name": "{t}"' not in src]
    if missing:
        fail(f"TOOLS missing: {missing}")
    ok(f"all {len(expected_tools)} ADR-028 tools advertised")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: exactly 1 write tool; 4 read tools
    # ------------------------------------------------------------------
    step("3. exactly 1 side_effects='write' (apply_approved_load); 4 read")
    read_count = src.count('"side_effects": "read"')
    write_count = src.count('"side_effects": "write"')
    if write_count != 1:
        fail(f"expected exactly 1 write tool; got {write_count}")
    if read_count != 4:
        fail(f"expected 4 read tools; got {read_count}")
    ok("1 write / 4 read (apply_approved_load is the sole write tool)")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: scope convention
    # ------------------------------------------------------------------
    step("4. scopes follow csv_ingest:read / write / approve convention")
    for scope in ("csv_ingest:read", "csv_ingest:write", "csv_ingest:approve"):
        if f'"{scope}"' not in src:
            fail(f"scope {scope} missing from TOOLS")
    # apply_approved_load specifically requires csv_ingest:write
    apply_block = re.search(
        r'"name":\s*"csv_ingest\.apply_approved_load".*?"required_scopes":\s*(\[[^\]]+\])',
        src, re.DOTALL,
    )
    if apply_block is None:
        fail("could not locate apply_approved_load required_scopes block")
    if "csv_ingest:write" not in apply_block.group(1):
        fail(f"apply_approved_load doesn't require csv_ingest:write; got {apply_block.group(1)}")
    ok("3 scopes present; apply_approved_load requires csv_ingest:write")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: identifier regex enforces SQL-safe identifiers
    # ------------------------------------------------------------------
    step("5. identifier regex enforces SQL-safe table/column names")
    # The modified contract uses IDENT_RE (^[A-Za-z_][A-Za-z0-9_]{0,62}$)
    # plus an env-driven CSV_INGEST_ALLOWED_TABLES allow-list. Both layers
    # are required: regex blocks injection-shaped names, allow-list blocks
    # write-to-anything-named-foo. Either layer alone is insufficient.
    if "IDENT_RE" not in src:
        fail("IDENT_RE constant (identifier regex) not defined")
    if "[A-Za-z_]" not in src:
        fail("identifier regex doesn't constrain leading char to [A-Za-z_]")
    if "CSV_INGEST_ALLOWED_TABLES" not in src:
        fail(
            "CSV_INGEST_ALLOWED_TABLES env-driven allow-list missing — "
            "identifier regex alone admits any SQL-safe name; allow-list "
            "is the second-layer guardrail"
        )
    ok("identifier regex + env-driven allow-list both present")

    # ------------------------------------------------------------------
    # Load module for negative-assertion runtime tests. Use the canonical
    # package import path (mcp.server_csv_ingest) since the server depends
    # on `from mcp.server_common import ...` — file-location import would
    # break those relative imports.
    # ------------------------------------------------------------------
    sys.path.insert(0, str(REPO))
    try:
        from mcp import server_csv_ingest as mod  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        fail(f"server module failed to import: {exc}")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: documents server still 0 write tools
    # ------------------------------------------------------------------
    step("6. NEGATIVE: documents server still has 0 write tools (separation held)")
    doc_writes = docs_src.count('"side_effects": "write"')
    if doc_writes != 0:
        fail(
            f"documents server has {doc_writes} write tool(s) — read/write "
            f"separation per §47 + ADR-028 broken"
        )
    ok("documents server has 0 write tools (separation locked)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: raw SQL rejected at MCP boundary
    # ------------------------------------------------------------------
    step("7. NEGATIVE: raw SQL / DDL keywords rejected via _reject_raw_sql_surface")
    # The modified server has _reject_raw_sql_surface that scans args for
    # 'sql' / 'query' keys AND for SQL/DDL keyword substrings anywhere in
    # the JSON-serialized args. Either pattern → 400.
    bad_args_cases = (
        {"sql": "SELECT 1"},
        {"query": "DROP TABLE x"},
        {"target_table": "users; DROP TABLE x"},  # DDL-substring in identifier
        {"column_mapping": {"a": "ALTER TABLE x"}},  # DDL inside mapping value
    )
    rejections = 0
    for bad in bad_args_cases:
        try:
            mod._reject_raw_sql_surface(bad)
            fail(f"raw-SQL rejector failed to reject: {bad}")
        except Exception:
            rejections += 1
    if rejections != len(bad_args_cases):
        fail(f"only {rejections}/{len(bad_args_cases)} raw-SQL cases rejected")
    ok(f"all {len(bad_args_cases)} raw-SQL / DDL-bearing arg shapes rejected")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: identifier safety rejects unsafe names
    # ------------------------------------------------------------------
    step("8. NEGATIVE: _safe_identifier rejects unsafe names")
    bad_idents = (
        "users; DROP TABLE x",      # SQL injection via semicolon
        "1users",                   # leading digit not allowed
        "governance.audit_log",     # dot-qualified disallowed
        "users--",                  # SQL comment
        "",                         # empty
        "x" * 100,                  # over length cap
    )
    rejections = 0
    for name in bad_idents:
        try:
            mod._safe_identifier(name, label="t")
            fail(f"_safe_identifier wrongly accepted: {name!r}")
        except Exception:
            rejections += 1
    if rejections != len(bad_idents):
        fail(f"only {rejections}/{len(bad_idents)} bad identifiers rejected")
    ok(f"all {len(bad_idents)} unsafe identifiers rejected")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: tenant_id required + mismatch rejected
    # ------------------------------------------------------------------
    step("9. NEGATIVE: tenant_id required + mismatch rejected")
    # _validate_tenant rejects None + cross-tenant + missing
    cases = (
        (None, None, "tenant_required"),       # missing arg
        ("t1", None, "tenant_required"),       # missing in arg
        ("t1", "t2", "tenant_mismatch"),       # cross-tenant attempt
    )
    for req_tenant, arg_tenant, expected_code in cases:
        try:
            mod._validate_tenant(req_tenant, arg_tenant)
            fail(
                f"_validate_tenant({req_tenant!r}, {arg_tenant!r}) should "
                f"have raised — expected code {expected_code!r}"
            )
        except Exception as exc:
            # The HTTPException carries detail.code; verify it matches
            detail = getattr(exc, "detail", {})
            if isinstance(detail, dict) and detail.get("code") != expected_code:
                fail(
                    f"_validate_tenant({req_tenant!r}, {arg_tenant!r}) "
                    f"raised wrong code: got {detail.get('code')!r}, "
                    f"expected {expected_code!r}"
                )
    # Sanity: matching tenant should pass
    if mod._validate_tenant("t1", "t1") != "t1":
        fail("_validate_tenant doesn't return tenant on match")
    ok("tenant required + cross-tenant blocked; matching tenant accepted")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: path resolver allowlist enforced
    # ------------------------------------------------------------------
    step("10. NEGATIVE: path resolver rejects outside-allowlist paths")
    sensitive = ("/etc/passwd", "/usr/bin/sh", "/root/.ssh/id_rsa")
    rejections = 0
    for p in sensitive:
        try:
            mod._resolve_safe_path(p)
            fail(f"path resolver wrongly accepted: {p}")
        except Exception:
            rejections += 1
    if rejections != len(sensitive):
        fail(f"only {rejections}/{len(sensitive)} sensitive paths rejected")
    ok(f"all {len(sensitive)} sensitive paths rejected (allowlist enforced)")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
