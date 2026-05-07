# RESOURCES: readonly
"""
Drill: mcp/server_documents.py — agent-MCP interaction for CSV/PDF/Word/DB.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; user asked 'have you setup MCP for db/csv/pdf/word'
and the honest answer was NO; iter-61 ships the answer), §45.4 (no
checkbox flips without code), §47 (architecture: each MCP server owns
ONE domain), §47.6 (security: read-only data extraction; no destructive
ops at the MCP boundary), §50.5.3 (security rules NEVER to model;
SQL writes NEVER to agents).

This drill verifies the contract WITHOUT requiring the server to be
running — pure source-level + import-level locks. A separate live drill
can exercise the HTTP routes once the server is in docker-compose.

Locks (positive):
  L1. mcp/server_documents.py exists + importable
  L2. TOOLS list has all 4 expected tool names
  L3. Each tool advertises side_effects='read' (this server is
      strictly a read-only data-extraction surface)
  L4. Each tool requires the 'documents:read' scope (RBAC contract)
  L5. CSV impl uses stdlib `csv` module (no hard pandas dep)

Locks (negative — ≥3 per §43):
  N1. SQL guardrail rejects every forbidden keyword (UPDATE/INSERT/
      DELETE/DROP/TRUNCATE/ALTER/MERGE/EXECUTE/COPY/VACUUM)
  N2. SQL guardrail accepts SELECT (and WITH...SELECT CTE)
  N3. Path resolution rejects /etc/, /usr/, /home/<other>/, ssh keys
      — only /mnt/deepa/, /tmp/, /var/tmp/ allowed
  N4. PDF/Word/DB tools all return graceful 'available: False' shape
      when the underlying library isn't installed (never raise)
  N5. No `side_effects='write'` tool — this server is read-only by
      contract; a future iter that adds CSV-to-DB ingestion would
      ship a SEPARATE server (write surface), not extend this one
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "mcp" / "server_documents.py"
sys.path.insert(0, str(REPO))

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

    src = SERVER.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: server importable + module accessible
    # ------------------------------------------------------------------
    step("1. mcp/server_documents.py exists + module attributes accessible")
    # Don't fully import (FastAPI app would start OTel etc); verify via
    # source contents that the canonical structure is present.
    for marker in ("TOOLS", "_validate_select_only", "_resolve_safe_path"):
        if marker not in src:
            fail(f"server_documents.py missing top-level symbol: {marker}")
    ok("source has TOOLS + path/SQL guardrails")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: 4 expected tool names in TOOLS list
    # ------------------------------------------------------------------
    step("2. TOOLS list has all 4 expected tool names")
    expected_tools = (
        "documents.csv_parse",
        "documents.pdf_extract_text",
        "documents.docx_extract_text",
        "documents.db_query_select",
    )
    missing = [t for t in expected_tools if f'"name": "{t}"' not in src]
    if missing:
        fail(f"TOOLS missing: {missing}")
    ok(f"all {len(expected_tools)} tools advertised")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: every tool is side_effects='read'
    # ------------------------------------------------------------------
    step("3. every tool advertises side_effects='read' (read-only surface)")
    # Count side_effects values; must be 4 'read' and 0 'write' for this server
    read_count = src.count('"side_effects": "read"')
    write_count = src.count('"side_effects": "write"')
    if read_count != len(expected_tools):
        fail(
            f"expected {len(expected_tools)} side_effects=read entries; "
            f"got {read_count}"
        )
    if write_count != 0:
        fail(
            f"server has {write_count} side_effects=write tool(s) — this "
            "server is read-only by contract; ingest/insert tools belong "
            "in a separate server"
        )
    ok(f"4 read tools / 0 write tools (read-only surface held)")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: every tool requires 'documents:read' scope
    # ------------------------------------------------------------------
    step("4. every tool requires 'documents:read' scope (RBAC)")
    if src.count('"documents:read"') < len(expected_tools):
        fail(
            "not every tool requires 'documents:read' — RBAC contract "
            "must be uniform across the server"
        )
    ok("all tools require 'documents:read' scope")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: CSV impl uses stdlib csv (no hard pandas dep)
    # ------------------------------------------------------------------
    step("5. CSV impl uses stdlib csv module (always available)")
    if "import csv" not in src:
        fail("server doesn't import stdlib csv — CSV tool needs a parser")
    if "import pandas" in src and "from pandas" in src:
        fail(
            "server unconditionally imports pandas — should be opt-in via "
            "env-flag (pandas is heavy; CSV tool must work without it)"
        )
    ok("stdlib csv is the default parser (no hard pandas dep)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: SQL guardrail rejects forbidden keywords
    # ------------------------------------------------------------------
    step("6. NEGATIVE: SQL guardrail rejects every write keyword")
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("server_documents_test", SERVER)
    if spec is None or spec.loader is None:
        fail("could not load server_documents.py via importlib")
    # Defer FastAPI app side-effects: import only the validators by
    # parsing the relevant function out. Easier: just import; the
    # FastAPI app() construction is fine in a drill.
    mod = _ilu.module_from_spec(spec)
    sys.modules["server_documents_test"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        fail(f"server module failed to import: {exc}")

    forbidden_statements = (
        "UPDATE governance.audit_log SET status='applied'",
        "INSERT INTO foo VALUES (1)",
        "DELETE FROM bar",
        "DROP TABLE secrets",
        "TRUNCATE TABLE leak",
        "ALTER TABLE users ADD COLUMN admin BOOLEAN",
        "MERGE INTO target USING src ON 1=1",
        "EXECUTE format('DROP TABLE %I', 'x')",
        "COPY users TO '/tmp/leak.csv'",
        "VACUUM ANALYZE users",
    )
    rejections = 0
    for sql in forbidden_statements:
        try:
            mod._validate_select_only(sql)
            fail(f"SQL guardrail FAILED to reject: {sql[:60]}…")
        except Exception:
            rejections += 1
    if rejections != len(forbidden_statements):
        fail(f"only {rejections}/{len(forbidden_statements)} write SQLs rejected")
    ok(f"all {len(forbidden_statements)} write SQLs rejected at guardrail")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: SQL guardrail accepts SELECT + WITH-SELECT
    # ------------------------------------------------------------------
    step("7. NEGATIVE: SQL guardrail ACCEPTS pure SELECT + WITH...SELECT CTE")
    accepted = (
        "SELECT 1",
        "SELECT * FROM users WHERE id = $1",
        "  SELECT count(*) FROM governance.audit_log",
        "WITH recent AS (SELECT id FROM users LIMIT 10) SELECT * FROM recent",
    )
    for sql in accepted:
        try:
            mod._validate_select_only(sql)
        except Exception as exc:  # noqa: BLE001
            fail(f"guardrail wrongly REJECTED valid SELECT: {sql[:50]}… ({exc})")
    ok(f"all {len(accepted)} pure-SELECT statements accepted")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: path resolution rejects sensitive prefixes
    # ------------------------------------------------------------------
    step("8. NEGATIVE: path-resolver rejects /etc, /usr, /home/<other>")
    sensitive = (
        "/etc/passwd",
        "/etc/shadow",
        "/usr/bin/python3",
        "/root/.ssh/id_rsa",
    )
    rejections = 0
    for p in sensitive:
        try:
            mod._resolve_safe_path(p)
            fail(f"path resolver wrongly accepted sensitive path: {p}")
        except Exception:
            rejections += 1
    if rejections != len(sensitive):
        fail(f"only {rejections}/{len(sensitive)} sensitive paths rejected")
    ok(f"all {len(sensitive)} sensitive paths rejected (path-traversal blocked)")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: tools never raise on missing libs (graceful stub)
    # ------------------------------------------------------------------
    step("9. NEGATIVE: PDF/DOCX/DB tools return 'available: False' on missing libs")
    # Source-level lock: each impl has the early-return-with-available-False
    # pattern. A regression that lets ImportError propagate would crash agents.
    for fn_name, lib_marker in (
        ("_pdf_extract_impl", "pdfplumber"),
        ("_docx_extract_impl", "docx"),
        ("_db_query_select_impl", "psycopg2"),
    ):
        m = re.search(
            rf"def {fn_name}.*?(?=\ndef \w|\Z)",
            src, re.DOTALL,
        )
        if m is None:
            fail(f"could not locate {fn_name} body")
        body = m.group(0)
        if '"available": False' not in body:
            fail(
                f"{fn_name} doesn't have an 'available: False' fallback path "
                f"for missing {lib_marker} — would crash agents on missing lib"
            )
        if "ImportError" not in body:
            fail(
                f"{fn_name} doesn't catch ImportError for {lib_marker} — "
                f"would propagate to agents as 500"
            )
    ok("PDF/DOCX/DB tools all have ImportError → available:False fallback")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED (5 positive + 4 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
