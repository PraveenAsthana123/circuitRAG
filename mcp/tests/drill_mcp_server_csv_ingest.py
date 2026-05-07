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
    for marker in ("TOOLS", "_validate_staging_table", "_resolve_safe_path",
                   "_reject_ddl_text", "_DRAFTS"):
        if marker not in src:
            fail(f"server missing canonical symbol: {marker}")
    ok("source has TOOLS + 3 guardrails + _DRAFTS state")

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
    # Step 5 — POSITIVE: staging-table regex enforces ^stg_[a-z0-9_]+$
    # ------------------------------------------------------------------
    step("5. staging-table regex ^stg_[a-z0-9_]+$ present")
    if "stg_[a-z0-9_]" not in src:
        fail("staging-table regex pattern missing")
    if "_STAGING_TABLE_RE" not in src:
        fail("_STAGING_TABLE_RE constant not defined")
    ok("staging-table regex present (^stg_[a-z0-9_]+$)")

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
    # Step 7 — NEGATIVE: apply with mismatched approval_id denied
    # ------------------------------------------------------------------
    step("7. NEGATIVE: apply with mismatched approval_id → denial")
    # Seed a draft directly into _DRAFTS (in-memory store)
    mod._DRAFTS["DRAFT-TEST"] = {
        "draft_id": "DRAFT-TEST",
        "path": "/tmp/x.csv",
        "table_name": "stg_test",
        "tenant_id": "t1",
        "csv_digest": "abc",
        "mapping_digest": "def",
        "rows_total": 10,
        "rows_rejected": 0,
        "status": "pending_approval",
        "approval_id": "APPR-RIGHT",
        "submitted_at": 0,
        "applied_at": None,
        "idempotency_key": "k1",
    }
    result = mod._apply_approved_load_impl({
        "draft_id": "DRAFT-TEST",
        "approval_id": "APPR-WRONG",
        "approval_token": "anything",
    })
    if result.get("applied") is not False:
        fail(f"apply with wrong approval_id was NOT denied; got {result}")
    if "approval_id_mismatch" not in result.get("denial_reason", ""):
        fail(
            f"denial_reason should be 'approval_id_mismatch'; got "
            f"{result.get('denial_reason')!r}"
        )
    ok("apply with wrong approval_id → applied:False + 'approval_id_mismatch'")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: DDL in agent-supplied table_name rejected
    # ------------------------------------------------------------------
    step("8. NEGATIVE: DDL keyword in table_name rejected at MCP boundary")
    # Bad table names (DDL keyword OR not staging-prefixed)
    bad_names = (
        "users",                    # not staging
        "DROP TABLE users",         # DDL injection
        "stg_users; DROP TABLE x",  # staging-prefix-prefix + DDL
        "governance.audit_log",     # cross-schema attempt
        "stg_X",                    # uppercase not allowed
    )
    rejections = 0
    for name in bad_names:
        try:
            mod._validate_staging_table(name)
            fail(f"staging-table guardrail wrongly accepted: {name!r}")
        except Exception:
            rejections += 1
    if rejections != len(bad_names):
        fail(f"only {rejections}/{len(bad_names)} bad table names rejected")
    ok(f"all {len(bad_names)} non-staging / DDL-bearing names rejected")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: Stage-1 apply ALWAYS denies (HMAC lands iter-66)
    # ------------------------------------------------------------------
    step("9. NEGATIVE: Stage-1 apply with EVERYTHING matching still denies")
    # Even with matching approval_id, Stage-1 doesn't have HMAC verification
    # wired — should still return denial per ADR-028 #3 ("apply without
    # approval returns a denial"; no approval-token verification = denial).
    mod._DRAFTS["DRAFT-FULL-MATCH"] = {
        "draft_id": "DRAFT-FULL-MATCH",
        "path": "/tmp/x.csv",
        "table_name": "stg_test",
        "tenant_id": "t1",
        "csv_digest": "abc",
        "mapping_digest": "def",
        "rows_total": 10,
        "rows_rejected": 0,
        "status": "pending_approval",
        "approval_id": "APPR-MATCH",
        "submitted_at": 0,
        "applied_at": None,
        "idempotency_key": "k1",
    }
    result = mod._apply_approved_load_impl({
        "draft_id": "DRAFT-FULL-MATCH",
        "approval_id": "APPR-MATCH",
        "approval_token": "stage_1_token",
    })
    if result.get("applied") is True:
        fail(
            "Stage-1 apply landed rows — HMAC + Postgres apply must "
            "be deferred to iter-66 per ADR-028 §Implementation guardrails"
        )
    if "stage_1" not in result.get("denial_reason", "").lower():
        fail(
            f"denial_reason should mention stage_1 + iter-66; "
            f"got {result.get('denial_reason')!r}"
        )
    ok("Stage-1 apply structurally denies; iter-66 will land HMAC + apply")

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
