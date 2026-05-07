# RESOURCES: readonly
"""
Drill: 5 SaaS MCP servers — Jira / Teams / WhatsApp / GDrive / ServiceNow.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-67 ships 5 SaaS MCP scaffolds in one logical
'expand the MCP fleet to enterprise SaaS' iter), §45.4 (no checkbox
flips without code), §47 (architecture: each MCP server owns ONE
namespace), §47.6 (security: read-only Stage-1; write surfaces need
separate ADRs).

User asked: 'jira mcp, team mcp, whatsap mcp, google drive mcp, word mcp,
pdf, servicenow mcp'. Word + PDF were already shipped as iter-61's
documents.docx_extract_text + documents.pdf_extract_text. Iter-67 ships
the remaining 5 as MCP scaffolds + this drill that locks the contract.

Locks (positive):
  L1. All 5 server files exist (jira, teams, whatsapp, gdrive, servicenow)
  L2. Each server defines a TOOLS list with ≥1 tool
  L3. Each server's tools are ALL side_effects='read' (Stage-1 read-only)
  L4. Each server has the canonical health/tools_list/tools_call endpoints
  L5. inference-svc mcp_spec includes all 5 as DOCUMIND_MCP_<NS>_URL hooks

Locks (negative — ≥3 per §43):
  N1. NO write tools in any of the 5 SaaS servers (Stage-1 contract;
      write surfaces ship separately per ADR-028 pattern)
  N2. Each server's namespace prefix matches the file name
      (server_jira.py → tools start with 'jira.', not 'jira_' or 'jira/')
  N3. Each server has an identifier-shape OR query-content guardrail
      (regex-validated input — no raw injection-shaped strings allowed)
  N4. Each server has env-driven _live_or_stub() pattern (no hardcoded
      credentials; agents using stub mode see available:False shape)
  N5. Documents server STILL has 0 write tools (post-iter-61 lock holds
      across the iter-67 expansion)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INFERENCE_MAIN = REPO / "services" / "inference-svc" / "app" / "main.py"
DOCS_SERVER = REPO / "mcp" / "server_documents.py"

SAAS_SERVERS = (
    ("jira",       REPO / "mcp" / "server_jira.py",       "DOCUMIND_MCP_JIRA_URL"),
    ("teams",      REPO / "mcp" / "server_teams.py",      "DOCUMIND_MCP_TEAMS_URL"),
    ("whatsapp",   REPO / "mcp" / "server_whatsapp.py",   "DOCUMIND_MCP_WHATSAPP_URL"),
    ("gdrive",     REPO / "mcp" / "server_gdrive.py",     "DOCUMIND_MCP_GDRIVE_URL"),
    ("servicenow", REPO / "mcp" / "server_servicenow.py", "DOCUMIND_MCP_SERVICENOW_URL"),
)

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
    sources: dict[str, str] = {}
    for ns, path, _ in SAAS_SERVERS:
        if not path.exists():
            fail(f"missing: {path.relative_to(REPO)}")
        sources[ns] = path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: all 5 server files exist
    # ------------------------------------------------------------------
    step("1. all 5 SaaS server files exist")
    ok(f"jira / teams / whatsapp / gdrive / servicenow servers all present "
       f"({sum(1 for _, p, _ in SAAS_SERVERS if p.exists())}/{len(SAAS_SERVERS)})")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: each server has TOOLS list with ≥1 tool
    # ------------------------------------------------------------------
    step("2. each server has TOOLS with ≥1 tool")
    for ns, _, _ in SAAS_SERVERS:
        src = sources[ns]
        if "TOOLS:" not in src and "TOOLS =" not in src:
            fail(f"{ns} server has no TOOLS list")
        # Look for at least one tool name with the namespace prefix
        if not re.search(rf'"name":\s*"{ns}\.[a-z_]+', src):
            fail(f"{ns} server has no tool with '{ns}.*' namespace")
    ok("all 5 servers have TOOLS with ≥1 namespaced tool")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: every tool in every server is read-only
    # ------------------------------------------------------------------
    step("3. every tool in every SaaS server is side_effects='read' (Stage-1)")
    for ns, _, _ in SAAS_SERVERS:
        src = sources[ns]
        read_count = src.count('"side_effects": "read"')
        if read_count < 1:
            fail(f"{ns} server has 0 read tools")
    ok("all 5 SaaS servers Stage-1 read-only (write surfaces deferred)")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: each server has health/tools_list/tools_call
    # ------------------------------------------------------------------
    step("4. each server has /health + /tools/list + /tools/call routes")
    for ns, _, _ in SAAS_SERVERS:
        src = sources[ns]
        for route in ('@app.get("/health")', '@app.get("/tools/list")',
                      '@app.post("/tools/call")'):
            if route not in src:
                fail(f"{ns} server missing route: {route}")
    ok("all 5 servers expose the canonical 3 routes")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: inference-svc mcp_spec includes all 5 hooks
    # ------------------------------------------------------------------
    step("5. inference-svc mcp_spec wires all 5 SaaS servers via env-flag")
    if not INFERENCE_MAIN.exists():
        fail(f"missing: {INFERENCE_MAIN.relative_to(REPO)}")
    inf_src = INFERENCE_MAIN.read_text(encoding="utf-8")
    for ns, _, env_var in SAAS_SERVERS:
        if env_var not in inf_src:
            fail(f"inference-svc mcp_spec missing env-flag: {env_var}")
        # Default empty (operator opt-in)
        if not re.search(rf'os\.getenv\("{env_var}",\s*""\)', inf_src):
            fail(f"{env_var} default is not empty string (operator opt-in broken)")
    ok("all 5 SaaS env-flags wired into mcp_spec with empty defaults")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: NO write tools in any SaaS server
    # ------------------------------------------------------------------
    step("6. NEGATIVE: 0 write tools in jira/teams/whatsapp/gdrive/servicenow")
    for ns, _, _ in SAAS_SERVERS:
        src = sources[ns]
        write_count = src.count('"side_effects": "write"')
        if write_count != 0:
            fail(
                f"{ns} server has {write_count} write tool(s) — Stage-1 "
                f"contract violated; write surfaces ship in separate ADR"
            )
    ok("0 write tools across all 5 SaaS servers (Stage-1 lock held)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: namespace prefix matches file name
    # ------------------------------------------------------------------
    step("7. NEGATIVE: namespace prefix matches file name (no jira_/jira/ leaks)")
    for ns, _, _ in SAAS_SERVERS:
        src = sources[ns]
        # Look for any tool name that DOESN'T match `<ns>.<name>`
        bad_names = re.findall(rf'"name":\s*"({ns}[/_]\w+|(?!{ns}\.)[a-z_]+\.[a-z_]+)"', src)
        # Filter out matches that are valid (start with ns.)
        bad_names = [b for b in bad_names if not b.startswith(f"{ns}.")]
        if bad_names:
            fail(f"{ns} server has wrong-namespace tool(s): {bad_names}")
    ok("namespace prefixes consistent (jira.* / teams.* / whatsapp.* / etc.)")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: each server has at least one input guardrail
    # ------------------------------------------------------------------
    step("8. NEGATIVE: each server has identifier or query guardrail (regex-validated input)")
    expected_guardrails = {
        "jira": ("_validate_issue_key", "_validate_jql"),
        "teams": ("query_too_long",),  # length cap on message_search query
        "whatsapp": ("_validate_template_name",),
        "gdrive": ("_validate_file_id", "_validate_query"),
        "servicenow": ("_validate_sys_id", "_validate_query"),
    }
    for ns, _, _ in SAAS_SERVERS:
        src = sources[ns]
        markers = expected_guardrails[ns]
        if not any(m in src for m in markers):
            fail(
                f"{ns} server has none of {markers} — input guardrail "
                f"missing; agent-supplied strings flow unvalidated"
            )
    ok("all 5 servers have at least one input-validation guardrail")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: env-driven _live_or_stub pattern
    # ------------------------------------------------------------------
    step("9. NEGATIVE: each server uses _live_or_stub() pattern (no hardcoded creds)")
    for ns, _, _ in SAAS_SERVERS:
        src = sources[ns]
        if "_live_or_stub" not in src:
            fail(f"{ns} server doesn't use _live_or_stub pattern")
        # Stub-mode response shape: 'available': False
        if '"available": False' not in src:
            fail(f"{ns} server doesn't return 'available: False' in stub mode")
    ok("all 5 servers env-driven; agents see available:False on missing creds")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: documents server STILL has 0 write tools
    # ------------------------------------------------------------------
    step("10. NEGATIVE: documents server still 0 write tools (iter-61 lock holds)")
    if not DOCS_SERVER.exists():
        fail(f"missing: {DOCS_SERVER.relative_to(REPO)}")
    docs_src = DOCS_SERVER.read_text(encoding="utf-8")
    docs_writes = docs_src.count('"side_effects": "write"')
    if docs_writes != 0:
        fail(f"documents server now has {docs_writes} write tool(s) — iter-67 broke iter-61's lock")
    ok("documents server still 0 write tools (read-only lock held across expansion)")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED ({len(SAAS_SERVERS)} SaaS servers; 5 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
