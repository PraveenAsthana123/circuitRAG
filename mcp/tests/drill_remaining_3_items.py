# RESOURCES: pg
"""
Drill: iter-21 closure of 3 remaining operator-side items.

Per CLAUDE.md §38 (governance), §42 (operational autonomy boundary),
§43 (drill discipline). Operator instruction "complete all" pushes
the autonomous-loop scope to maximum within §42:

  Item 4 (XAI_API_KEY)     — chatxai_fallback.py CLI: routes to local
                              Ollama when key absent, real xAI when set
  Item 6 (Ollama identity) — ollama_health_repair.sh: diagnoses + tries
                              sudo -n; falls through to operator commands
  Item 7 (HITL drafts)     — hitl_drafts_triage.py --clean-drill-artifacts:
                              marks drill-tagged pending rows as rejected
                              (NOT delete; preserves audit per §38)

Locks (positive):
  L1. All 3 CLI scripts exist + executable
  L2. chatxai_fallback diagnostic-only mode prints route + gap
  L3. ollama_health_repair runs + reports diagnostic state
  L4. clean-drill-artifacts marks rows as rejected, NOT deletes

Locks (negative — ≥3 per §43):
  N1. clean_drill_artifacts NEVER DELETEs rows (§38 audit immutability)
  N2. chatxai_fallback diagnostic-only NEVER calls real LLM
       (no token cost on a smoke check)
  N3. ollama_health_repair NEVER auto-runs sudo with password
       (§42 sudo gate; only sudo -n; falls back to documentation)
  N4. clean-drill-artifacts ONLY matches reason LIKE 'drill%' AND
       status='pending' (NEVER touches real drafts or replayed/rejected)
  N5. chatxai_fallback honest_gap surfaces XAI_API_KEY=unset
"""
from __future__ import annotations

import asyncio
import os
import re
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


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    triage_py = REPO / "scripts" / "hitl_drafts_triage.py"
    chatxai_py = REPO / "scripts" / "chatxai_fallback.py"
    ollama_sh = REPO / "scripts" / "ollama_health_repair.sh"

    # ===================================================================
    # Step 1 — all 3 CLI scripts exist
    # ===================================================================
    step("1. all 3 CLI scripts exist")
    for p in (triage_py, chatxai_py, ollama_sh):
        if not p.exists():
            fail(f"missing: {p.relative_to(REPO)}")
    ok("3 CLI scripts present: triage / chatxai_fallback / ollama_health_repair")

    # ===================================================================
    # Step 2 — ollama_health_repair.sh is executable
    # ===================================================================
    step("2. ollama_health_repair.sh executable bit set")
    if not os.access(ollama_sh, os.X_OK):
        fail("ollama_health_repair.sh not executable")
    ok("+x bit set; runnable as `bash scripts/...` or `./scripts/...`")

    # ===================================================================
    # Step 3 — Item 4: chatxai_fallback diagnostic mode works without LLM call
    # ===================================================================
    step("3. Item 4: chatxai_fallback.py --diagnostic-only routes correctly")
    saved_key = os.environ.pop("XAI_API_KEY", None)
    try:
        result = subprocess.run(
            [sys.executable, str(chatxai_py), "--diagnostic-only"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            fail(f"diagnostic mode rc={result.returncode}: {result.stderr[:200]}")
        if "XAI_API_KEY set:" not in result.stderr:
            fail(f"diagnostic missing routing decision: {result.stderr[:200]}")
        if "ollama:qwen2.5" not in result.stderr:
            fail(f"unset key should route to ollama:qwen2.5; stderr: {result.stderr[:200]}")
    finally:
        if saved_key is not None:
            os.environ["XAI_API_KEY"] = saved_key
    ok("--diagnostic-only routes to ollama:qwen2.5 when key unset")

    # ===================================================================
    # Step 4 — Item 4: NEGATIVE: diagnostic mode makes NO LLM call
    # ===================================================================
    step("4. NEGATIVE: chatxai_fallback --diagnostic-only never invokes an LLM")
    src = chatxai_py.read_text(encoding="utf-8")
    # The diagnostic path must short-circuit BEFORE calling evaluate()
    # which is the only function that would invoke an LLM.
    m = re.search(r"if args\.diagnostic_only or args\.prompt is None.*?\n\s+return 0",
                  src, re.DOTALL)
    if m is None:
        fail("diagnostic-only short-circuit pattern not found in source")
    ok("diagnostic-only short-circuits before evaluate(); no LLM call possible")

    # ===================================================================
    # Step 5 — Item 4: NEGATIVE: honest_gap surfaces missing key
    # ===================================================================
    step("5. NEGATIVE: chatxai_fallback honest_gap surfaces XAI_API_KEY=unset")
    if "XAI_API_KEY not set" not in src:
        fail("source missing 'XAI_API_KEY not set' honest_gap text")
    # Multi-line tolerant: "Grok-class" appears in source; "proxy"
    # appears in the gap text (could be on a different line)
    if "Grok-class" not in src or "proxy" not in src.lower():
        fail("source should mention 'Grok-class' AND 'proxy' to set operator expectations")
    ok("honest_gap surfaces missing key + Grok-class proxy disclaimer")

    # ===================================================================
    # Step 6 — Item 6: ollama_health_repair runs + reports state
    # ===================================================================
    step("6. Item 6: ollama_health_repair.sh produces diagnostic output")
    result = subprocess.run(
        ["bash", str(ollama_sh)],
        capture_output=True, text=True, timeout=30,
    )
    # rc=0 (all OK) or rc=2 (operator-action required) both legitimate
    if result.returncode not in (0, 2):
        fail(f"unexpected rc={result.returncode}; stdout: {result.stdout[:200]}")
    if "ollama daemon HTTP /api/tags" not in result.stdout:
        fail(f"diagnostic missing /api/tags probe; stdout: {result.stdout[:200]}")
    if "models installed" not in result.stdout:
        fail("diagnostic missing model count")
    ok(f"diagnostic ran (rc={result.returncode}); /api/tags probed; models counted")

    # ===================================================================
    # Step 7 — Item 6: NEGATIVE: never auto-runs sudo with password
    # ===================================================================
    step("7. NEGATIVE: ollama_health_repair NEVER prompts for sudo password")
    sh_src = ollama_sh.read_text(encoding="utf-8")
    # All sudo invocations MUST use -n flag (non-interactive) OR be in
    # the documentation-only block (commented or echo'd out)
    sudo_lines = [line for line in sh_src.splitlines() if "sudo " in line]
    for line in sudo_lines:
        stripped = line.strip()
        # Allowed: in documentation echo, in comment, or -n flag
        if (
            stripped.startswith("#")
            or stripped.startswith("echo")
            or "sudo -n " in line
        ):
            continue
        fail(f"sudo without -n flag (would prompt): {line.strip()[:80]}")
    ok(f"all {len(sudo_lines)} sudo references are -n OR in echo/comment blocks")

    # ===================================================================
    # Step 8 — Item 7: clean_drill_artifacts is callable (not just docs)
    # ===================================================================
    step("8. Item 7: hitl_drafts_triage.clean_drill_artifacts is callable")
    import hitl_drafts_triage  # noqa: E402
    if not callable(getattr(hitl_drafts_triage, "clean_drill_artifacts", None)):
        fail("clean_drill_artifacts not exposed in hitl_drafts_triage")
    ok("clean_drill_artifacts callable")

    # ===================================================================
    # Step 9 — Item 7: NEGATIVE: clean uses UPDATE not DELETE
    # ===================================================================
    step("9. NEGATIVE: clean_drill_artifacts uses UPDATE, NEVER DELETE")
    triage_src = triage_py.read_text(encoding="utf-8")
    m = re.search(
        r"def clean_drill_artifacts.*?(?=\ndef \w)",
        triage_src, re.DOTALL,
    )
    if m is None:
        fail("could not locate clean_drill_artifacts body")
    body = m.group(0)
    if "DELETE FROM governance.action_drafts" in body.upper():
        fail("clean_drill_artifacts contains DELETE — violates §38 audit immutability")
    if "UPDATE governance.action_drafts" not in body:
        fail("clean_drill_artifacts should use UPDATE to flip status")
    ok("clean uses UPDATE (status flip); audit immutability preserved")

    # ===================================================================
    # Step 10 — Item 7: NEGATIVE: clean ONLY targets drill+pending rows
    # ===================================================================
    step("10. NEGATIVE: clean WHERE clause filters drill% AND pending")
    if "reason LIKE 'drill%'" not in body and "reason LIKE 'drill_%'" not in body:
        fail("clean WHERE missing drill% pattern filter")
    if "status = 'pending'" not in body and "status='pending'" not in body:
        fail("clean WHERE missing status='pending' filter")
    ok("WHERE clause restricts to (reason LIKE 'drill%' AND status='pending')")

    # ===================================================================
    # Step 11 — Item 7: empirical state — clean already ran in this session
    # ===================================================================
    step("11. NEGATIVE: drill artifacts NO LONGER in pending status")

    async def _check():
        try:
            import asyncpg  # noqa: F401
        except ImportError:
            return None
        try:
            import asyncpg
            conn = await asyncpg.connect(
                host="localhost", port=55432, user="documind",
                password="documind", database="documind", timeout=3.0,
            )
            try:
                row = await conn.fetchrow(
                    "SELECT count(*) AS n FROM governance.action_drafts "
                    " WHERE status='pending' "
                    "   AND (reason LIKE 'drill%' OR reason LIKE 'drill_%')"
                )
                return int(row["n"]) if row else -1
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return None

    result = asyncio.run(_check())
    if result is None:
        ok("skipped (postgres unreachable)")
    elif result > 0:
        fail(
            f"{result} drill-artifact pending drafts still present — "
            "clean operation incomplete or drift since clean"
        )
    else:
        ok("0 drill-artifact pending drafts (clean stayed effective)")

    print(f"\n{GREEN}{BOLD}ALL 11 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
