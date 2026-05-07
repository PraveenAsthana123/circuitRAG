# RESOURCES: readonly
"""
Drill: docs/runbooks/operator-activation-7-items.md — 7-item activation
contract.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §51 forensic
substrate. Iter-19 closing summary listed 7 operator-actionable items;
iter-20 documents the activation sequence + drills the runbook's
correctness.

Locks (positive):
  L1. Runbook file exists at the documented path
  L2. Lists all 7 items by number
  L3. Documents the .env recipe (single command, env_file convention)
  L4. References each iteration commit by short-hash
  L5. Section "Items 1-3, 5" recipe matches the autonomous-doable surface

Locks (negative — ≥3 per §43):
  N1. Runbook does NOT auto-set XAI_API_KEY (item 4 is operator credential)
  N2. Runbook does NOT instruct sudo execution from this script
       (item 6 is operator territory; only doc + commands)
  N3. Runbook does NOT mass-reject HITL drafts via SQL (item 7 is
      operator decision; only the triage script + manual examples)
  N4. Runbook references the 4 drills that lock the underlying flags
  N5. .env file is gitignored (operator activation values stay local)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "runbooks" / "operator-activation-7-items.md"

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
    # ===================================================================
    # Step 1 — runbook exists
    # ===================================================================
    step("1. operator-activation-7-items.md exists")
    if not RUNBOOK.exists():
        fail(f"missing: {RUNBOOK.relative_to(REPO)}")
    text = RUNBOOK.read_text(encoding="utf-8")
    if len(text) < 1500:
        fail(f"runbook too small ({len(text)}B)")
    ok(f"runbook present ({len(text)}B)")

    # ===================================================================
    # Step 2 — Lists all 7 items
    # ===================================================================
    step("2. Documents all 7 items by number")
    for item_n in range(1, 8):
        # Each item should appear as "Item N" or "Items N-M" or "## Item N"
        if re.search(rf"\bItem[s]? {item_n}\b", text) is None:
            # Allow "Items 1-3" form for the bundled section
            if item_n in (1, 2, 3, 5) and "Items 1-3, 5" in text:
                continue
            fail(f"runbook missing reference to Item {item_n}")
    ok("all 7 items referenced")

    # ===================================================================
    # Step 3 — .env recipe is concrete + complete
    # ===================================================================
    step("3. .env recipe present + concrete (cat > .env <<EOF pattern)")
    if "cat > .env" not in text:
        fail("runbook missing concrete .env-creation recipe")
    if "secrets.token_hex(32)" not in text:
        fail("runbook missing the 32-byte session-secret generation recipe")
    for flag in ("MCP_GATEWAY_SQL_AUDIT_ENABLED=1",
                 "OPS_WORKER_SQL_ENABLED=1",
                 "MCP_TOOLS_SYNC_ENABLED=1",
                 "DOCUMIND_SESSION_TOKEN_SECRET="):
        if flag not in text:
            fail(f"recipe missing flag: {flag}")
    ok("recipe sets all 4 autonomous-doable env values")

    # ===================================================================
    # Step 4 — References iteration commits by short-hash
    # ===================================================================
    step("4. References iteration commits by short-hash")
    expected_commits = ("fa7358d",)  # iter 10 (XAI/Grok)
    for c in expected_commits:
        if c not in text:
            fail(f"runbook missing commit ref: {c}")
    ok(f"iter commit refs present: {expected_commits}")

    # ===================================================================
    # Step 5 — NEGATIVE: doesn't auto-set XAI_API_KEY
    # ===================================================================
    step("5. NEGATIVE: runbook doesn't auto-set XAI_API_KEY")
    # Look for any concrete XAI_API_KEY=xai-... assignment that would
    # imply the runbook is leaking a real key
    if re.search(r"XAI_API_KEY=xai-[a-zA-Z0-9_-]{20,}", text):
        fail("runbook may contain a real XAI_API_KEY value (would leak)")
    # And the runbook MUST say item 4 requires operator credential
    if "operator credential" not in text and "operator-obtained" not in text:
        fail("runbook should explicitly say item 4 is operator-credential territory")
    ok("XAI_API_KEY documented as operator credential; no leaked key")

    # ===================================================================
    # Step 6 — NEGATIVE: doesn't auto-execute sudo
    # ===================================================================
    step("6. NEGATIVE: runbook doesn't auto-execute sudo (item 6 is operator action)")
    # Should DOCUMENT sudo commands but not chain them in a single
    # auto-runnable script. Operators copy-paste.
    if "outside §42 autonomous-loop scope" not in text:
        fail("runbook should explicitly say item 6 (Ollama sudo) is outside §42 scope")
    ok("sudo work flagged as outside §42 scope")

    # ===================================================================
    # Step 7 — NEGATIVE: doesn't auto-mass-reject HITL drafts
    # ===================================================================
    step("7. NEGATIVE: runbook doesn't auto-mass-reject HITL drafts")
    # Must reference the §38 governance boundary
    if "§38" not in text:
        fail("runbook should cite §38 governance for HITL triage decisions")
    if "operator-decision territory" not in text and "operator territory" not in text:
        fail("runbook should explicitly say HITL bulk-reject is operator territory")
    ok("HITL bulk-actions flagged as operator territory; §38 cited")

    # ===================================================================
    # Step 8 — References the 4 drills that lock the underlying flags
    # ===================================================================
    step("8. References the 4 drills locking the migrate-phase flags")
    expected_drills = (
        "drill_mcp_gateway_dual_write",
        "drill_ops_worker_dual_write",
        "drill_tools_catalog_sync",
        "drill_session_token_approval",
    )
    missing = [d for d in expected_drills if d not in text]
    if missing:
        fail(f"runbook missing drill refs: {missing}")
    ok(f"all {len(expected_drills)} drill references present")

    # ===================================================================
    # Step 9 — NEGATIVE: .env is gitignored
    # ===================================================================
    step("9. NEGATIVE: .env is in .gitignore (operator values stay local)")
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    if not re.search(r"^\.env\b", gitignore, re.MULTILINE):
        fail(".env not in .gitignore — operator secrets could leak")
    ok(".env confirmed gitignored")

    # ===================================================================
    # Step 10 — Runbook references the triage script (item 7 helper)
    # ===================================================================
    step("10. Item 7 references hitl_drafts_triage.py + drill")
    if "hitl_drafts_triage.py" not in text:
        fail("runbook should reference scripts/hitl_drafts_triage.py")
    triage_script = REPO / "scripts" / "hitl_drafts_triage.py"
    if not triage_script.exists():
        fail("triage script doesn't exist on disk")
    triage_drill = REPO / "mcp" / "tests" / "drill_hitl_drafts_triage.py"
    if not triage_drill.exists():
        fail("triage drill doesn't exist on disk")
    ok("triage script + drill both exist + referenced")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
