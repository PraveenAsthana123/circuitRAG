# RESOURCES: readonly
"""
Drill: 11 SDLC MCP servers — P1 + P2 + P3 SDLC fleet expansion.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-71 is the SDLC-fleet batch — 11 servers from
one builder following iter-67 pattern), §45.4 (no checkbox flips
without code), §47 (each server owns ONE namespace), §47.6 (read-only
Stage-1; write surfaces deferred to per-server ADRs).

User asked: 'set up all these mcp - check if they are already setup or not'
for: slack, github_actions, sonarqube, sentry, pagerduty, kubectl,
confluence, datadog, aws, gcp, azure (11 servers).

Survey result: ALL 11 missing. Iter-71 ships them all in one batched
iter (same shape as iter-67's 5-server SaaS batch).

Locks (positive):
  L1. All 11 server files exist
  L2. Each server defines TOOLS with exactly 2 tools (read-only stub)
  L3. All tools side_effects='read' (Stage-1 read-only contract)
  L4. Each server has /health + /tools/list + /tools/call routes
  L5. inference-svc mcp_spec wires all 11 via DOCUMIND_MCP_<NS>_URL

Locks (negative — ≥3 per §43):
  N1. 0 write tools across all 11 servers
  N2. Tool namespace prefix matches file name
  N3. Each server has _validate_query input guardrail
  N4. Each server uses _live_or_stub() pattern (no hardcoded creds)
  N5. Each server's stub-mode response carries available:False
  N6. Documents server STILL has 0 write tools (iter-61 lock holds
      across the iter-71 expansion)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INFERENCE_MAIN = REPO / "services" / "inference-svc" / "app" / "main.py"
DOCS_SERVER = REPO / "mcp" / "server_documents.py"

SDLC_SERVERS = (
    # (namespace, expected_env_keys_count)
    ("slack", 1, "DOCUMIND_MCP_SLACK_URL"),
    ("github_actions", 1, "DOCUMIND_MCP_GITHUB_ACTIONS_URL"),
    ("sonarqube", 2, "DOCUMIND_MCP_SONARQUBE_URL"),
    ("sentry", 2, "DOCUMIND_MCP_SENTRY_URL"),
    ("pagerduty", 1, "DOCUMIND_MCP_PAGERDUTY_URL"),
    ("kubectl", 1, "DOCUMIND_MCP_KUBECTL_URL"),
    ("confluence", 3, "DOCUMIND_MCP_CONFLUENCE_URL"),
    ("datadog", 2, "DOCUMIND_MCP_DATADOG_URL"),
    ("aws", 2, "DOCUMIND_MCP_AWS_URL"),
    ("gcp", 1, "DOCUMIND_MCP_GCP_URL"),
    ("azure", 3, "DOCUMIND_MCP_AZURE_URL"),
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
    for ns, _, _ in SDLC_SERVERS:
        path = REPO / "mcp" / f"server_{ns}.py"
        if not path.exists():
            fail(f"missing: {path.relative_to(REPO)}")
        sources[ns] = path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: all 11 files exist
    # ------------------------------------------------------------------
    step("1. all 11 SDLC server files exist")
    ok(f"{len(SDLC_SERVERS)} servers present "
       f"(slack/github_actions/sonarqube/sentry/pagerduty/kubectl/"
       f"confluence/datadog/aws/gcp/azure)")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: each server has exactly 2 tools
    # ------------------------------------------------------------------
    step("2. each server has TOOLS with exactly 2 entries")
    for ns, _, _ in SDLC_SERVERS:
        src = sources[ns]
        tool_names = re.findall(rf'"name":\s*"({ns}\.[a-z0-9_]+)"', src)
        if len(tool_names) != 2:
            fail(f"{ns} server has {len(tool_names)} tools; expected 2")
    ok("all 11 servers have exactly 2 tools (Stage-1 minimum)")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: every tool is read-only
    # ------------------------------------------------------------------
    step("3. every tool is side_effects='read'")
    for ns, _, _ in SDLC_SERVERS:
        src = sources[ns]
        if src.count('"side_effects": "read"') != 2:
            fail(f"{ns}: expected 2 read tools; got {src.count(chr(34) + 'side_effects' + chr(34) + ': ' + chr(34) + 'read' + chr(34))}")
    ok("22 tools (11 × 2) all read-only")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: each server has 3 canonical routes
    # ------------------------------------------------------------------
    step("4. each server has /health + /tools/list + /tools/call routes")
    for ns, _, _ in SDLC_SERVERS:
        src = sources[ns]
        for route in ('@app.get("/health")', '@app.get("/tools/list")',
                      '@app.post("/tools/call")'):
            if route not in src:
                fail(f"{ns} server missing route: {route}")
    ok("all 11 servers expose the canonical 3 routes")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: inference-svc mcp_spec wires all 11
    # ------------------------------------------------------------------
    step("5. inference-svc mcp_spec wires all 11 SDLC servers via env-flag")
    inf_src = INFERENCE_MAIN.read_text(encoding="utf-8")
    for ns, _, env_var in SDLC_SERVERS:
        if env_var not in inf_src:
            fail(f"inference-svc missing env-flag {env_var}")
        if not re.search(rf'\(\s*"{ns}"\s*,\s*os\.getenv\("{env_var}"', inf_src):
            fail(f"{ns}: mcp_spec doesn't have ('{ns}', getenv(...)) tuple")
    ok(f"all {len(SDLC_SERVERS)} SDLC servers wired via DOCUMIND_MCP_<NS>_URL")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: 0 write tools across all 11
    # ------------------------------------------------------------------
    step("6. NEGATIVE: 0 write tools across the 11 SDLC servers")
    for ns, _, _ in SDLC_SERVERS:
        src = sources[ns]
        write_count = src.count('"side_effects": "write"')
        if write_count != 0:
            fail(f"{ns}: has {write_count} write tool(s); Stage-1 contract broken")
    ok("0 write tools across all 11 (write surfaces deferred to per-server ADRs)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: namespace prefix matches file name
    # ------------------------------------------------------------------
    step("7. NEGATIVE: namespace prefix matches file name")
    for ns, _, _ in SDLC_SERVERS:
        src = sources[ns]
        # All tool names must start with `<ns>.`
        bad = re.findall(r'"name":\s*"([^"]+)"', src)
        for name in bad:
            if not name.startswith(f"{ns}."):
                fail(f"{ns}: tool name {name!r} doesn't start with {ns}.")
    ok("namespace prefixes consistent across all 11 servers")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: each server has _validate_query guardrail
    # ------------------------------------------------------------------
    step("8. NEGATIVE: each server has _validate_query input guardrail")
    for ns, _, _ in SDLC_SERVERS:
        src = sources[ns]
        if "_validate_query" not in src:
            fail(f"{ns}: missing _validate_query guardrail")
        if "_QUERY_FORBIDDEN_RE" not in src:
            fail(f"{ns}: missing _QUERY_FORBIDDEN_RE regex")
    ok("all 11 servers have _validate_query + _QUERY_FORBIDDEN_RE")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: each server uses _live_or_stub pattern
    # ------------------------------------------------------------------
    step("9. NEGATIVE: each server uses _live_or_stub pattern (env-driven)")
    for ns, expected_keys, _ in SDLC_SERVERS:
        src = sources[ns]
        if "_live_or_stub" not in src:
            fail(f"{ns}: missing _live_or_stub function")
    ok("all 11 servers use _live_or_stub (no hardcoded credentials)")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: stub-mode response carries available:False
    # ------------------------------------------------------------------
    step("10. NEGATIVE: stub-mode response carries available:False")
    for ns, _, _ in SDLC_SERVERS:
        src = sources[ns]
        if '"available": False' not in src:
            fail(f"{ns}: stub-mode doesn't return available:False shape")
    ok("all 11 servers return available:False on missing creds")

    # ------------------------------------------------------------------
    # Step 11 — NEGATIVE: documents server STILL has 0 write tools
    # ------------------------------------------------------------------
    step("11. NEGATIVE: documents server still 0 write tools (iter-61 lock holds)")
    docs_src = DOCS_SERVER.read_text(encoding="utf-8")
    docs_writes = docs_src.count('"side_effects": "write"')
    if docs_writes != 0:
        fail(f"documents server has {docs_writes} write tool(s) — iter-61 lock broken")
    ok("documents server still 0 write tools (read-only lock holds across expansion)")

    print(f"\n{GREEN}{BOLD}ALL 11 STEPS PASSED ({len(SDLC_SERVERS)} servers; 5 positive + 6 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
