# RESOURCES: readonly
"""
Drill: documents MCP server is wired into inference-svc + has launcher.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop;
iter-61 shipped the server, iter-62 wires it so it's actually reachable),
§45.4 (no checkbox flips without code), §47 (architecture: MCP integration
boundary), §47.7 (expand-phase: shipping the wiring is its own iter,
separate from shipping the server).

Iter-61 shipped mcp/server_documents.py; iter-62 ships:
  - scripts/start_mcp_documents.sh           launcher (port 8094 default)
  - inference-svc/main.py mcp_spec extension  documents namespace recognition

Together: when the operator sets DOCUMIND_MCP_DOCUMENTS_URL=http://localhost:8094
and runs the launcher, inference-svc agents can call documents.* tools.

Locks (positive):
  L1. scripts/start_mcp_documents.sh exists + is executable
  L2. Launcher supports --help (prints USAGE block; per §43 every script)
  L3. Launcher uses uvicorn when available (production ASGI runner)
  L4. inference-svc mcp_spec list includes the 'documents' tuple with
      DOCUMIND_MCP_DOCUMENTS_URL env hook
  L5. The mcp_spec entry uses the same env-var prefix pattern as 'hr'
      and 'itsm' (DOCUMIND_MCP_<NS>_URL convention preserved)

Locks (negative — ≥3 per §43):
  N1. Launcher does NOT hardcode the port (must be overridable via
      MCP_DOCUMENTS_PORT env var; test with port 8095)
  N2. Launcher does NOT require sudo (the server is read-only;
      if a sudo invocation appears it's a regression)
  N3. inference-svc DOES NOT pass a documents URL by default
      (default-safe — DOCUMIND_MCP_DOCUMENTS_URL unset → no client
      created, no failed-connection retries)
  N4. Documentation comment in inference-svc cites iter-61 (the
      server commit) so a future maintainer can trace the chain
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "scripts" / "start_mcp_documents.sh"
INFERENCE_MAIN = REPO / "services" / "inference-svc" / "app" / "main.py"

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
    if not LAUNCHER.exists():
        fail(f"missing: {LAUNCHER.relative_to(REPO)}")
    if not INFERENCE_MAIN.exists():
        fail(f"missing: {INFERENCE_MAIN.relative_to(REPO)}")

    launcher_src = LAUNCHER.read_text(encoding="utf-8")
    inference_src = INFERENCE_MAIN.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: launcher exists + is executable
    # ------------------------------------------------------------------
    step("1. scripts/start_mcp_documents.sh exists + is executable")
    if not os.access(LAUNCHER, os.X_OK):
        fail("launcher is NOT executable; chmod +x missed")
    ok("launcher present + +x bit set")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: --help prints USAGE block
    # ------------------------------------------------------------------
    step("2. launcher supports --help with USAGE block")
    if "--help" not in launcher_src:
        fail("launcher missing --help handler")
    if "USAGE" not in launcher_src:
        fail("launcher --help doesn't print USAGE block")
    if "MCP_DOCUMENTS_PORT" not in launcher_src:
        fail("launcher doesn't document the MCP_DOCUMENTS_PORT env var")
    ok("launcher --help documents USAGE + env vars")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: uvicorn-when-available pattern
    # ------------------------------------------------------------------
    step("3. launcher uses uvicorn when available (production ASGI)")
    if "uvicorn" not in launcher_src:
        fail("launcher doesn't reference uvicorn — production runner missing")
    if "mcp.server_documents:app" not in launcher_src:
        fail("launcher doesn't target mcp.server_documents:app FastAPI app")
    ok("launcher targets mcp.server_documents:app via uvicorn")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: inference-svc mcp_spec includes 'documents'
    # ------------------------------------------------------------------
    step("4. inference-svc mcp_spec includes the 'documents' tuple")
    if "DOCUMIND_MCP_DOCUMENTS_URL" not in inference_src:
        fail(
            "inference-svc/main.py doesn't reference "
            "DOCUMIND_MCP_DOCUMENTS_URL — wiring is missing"
        )
    if not re.search(
        r'\(\s*"documents"\s*,\s*os\.getenv\("DOCUMIND_MCP_DOCUMENTS_URL"',
        inference_src,
    ):
        fail(
            "inference-svc mcp_spec doesn't have the ('documents', getenv(...)) "
            "tuple in the canonical shape"
        )
    ok("inference-svc mcp_spec wires documents namespace via env-flag")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: env-var prefix matches the convention
    # ------------------------------------------------------------------
    step("5. env-var follows the DOCUMIND_MCP_<NS>_URL convention")
    # Both hr + documents must use the same prefix shape
    expected = (
        "DOCUMIND_MCP_HR_URL",
        "DOCUMIND_MCP_ITSM_URL",
        "DOCUMIND_MCP_DOCUMENTS_URL",
    )
    for var in expected:
        if var not in inference_src:
            fail(f"convention violated: missing env var {var}")
    ok(f"all 3 mcp namespaces use the DOCUMIND_MCP_<NS>_URL convention")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: launcher does NOT hardcode the port
    # ------------------------------------------------------------------
    step("6. NEGATIVE: launcher honors MCP_DOCUMENTS_PORT override")
    if not re.search(r'MCP_DOCUMENTS_PORT.*[:-].*8094', launcher_src):
        fail(
            "launcher doesn't have a default-with-override pattern "
            "(${MCP_DOCUMENTS_PORT:-8094})"
        )
    # Source-level lock: an override pattern must be present
    if "${MCP_DOCUMENTS_PORT:-8094}" not in launcher_src:
        fail(
            "launcher doesn't use ${MCP_DOCUMENTS_PORT:-8094} "
            "(env-override-with-default pattern)"
        )
    ok("launcher port is overridable via MCP_DOCUMENTS_PORT env var")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: launcher does NOT require sudo
    # ------------------------------------------------------------------
    step("7. NEGATIVE: launcher does NOT use sudo (read-only server)")
    sudo_lines = [
        ln for ln in launcher_src.splitlines()
        if "sudo " in ln
        and not ln.strip().startswith("#")
        and not ln.strip().startswith("echo")
    ]
    if sudo_lines:
        fail(
            f"launcher contains sudo invocation(s): {sudo_lines[:2]}. "
            "documents server is read-only; no privilege escalation needed."
        )
    ok("launcher has no sudo invocations (least-privilege)")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: inference-svc default is empty (no auto-connect)
    # ------------------------------------------------------------------
    step("8. NEGATIVE: inference-svc default is empty (operator opt-in)")
    # The os.getenv call must have a "" default so unset env-flag = no
    # client created. A non-empty default would auto-connect even when
    # the operator hasn't started the server.
    if not re.search(
        r'os\.getenv\("DOCUMIND_MCP_DOCUMENTS_URL",\s*""\)',
        inference_src,
    ):
        fail(
            "DOCUMIND_MCP_DOCUMENTS_URL has a non-empty default — would "
            "auto-attempt connection on startup even when server is down"
        )
    ok("default is empty string (operator opt-in; no auto-connect)")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: provenance comment cites iter-61
    # ------------------------------------------------------------------
    step("9. NEGATIVE: inference-svc comment cites iter-61 (provenance)")
    # Trace the iter-61 server back from the wiring so a future
    # maintainer reading mcp_spec can find the server commit.
    if "iter-61" not in inference_src:
        fail(
            "inference-svc mcp_spec comment doesn't cite iter-61 — "
            "future maintainer can't trace the documents wiring back "
            "to the server commit"
        )
    ok("inference-svc cites iter-61 (server commit traceable from wiring)")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED (5 positive + 4 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
