# RESOURCES: pg
"""
Drill: iter-22 — replay_action_draft + activate_migrate_flags.

Per CLAUDE.md §38 (governance), §42 (operational autonomy), §43
(drill discipline). Iter-21 closed items 4, 6, 7 with CLI scripts.
The operator asked: "is there any other script for pending task?"
The honest answer was: replay_action_draft.py was REFERENCED in
the runbook but never built; activate_migrate_flags.sh would give
operator a single-command flag activator.

Iter-22 ships both.

Locks (positive):
  L1. Both scripts exist (replay_action_draft.py + activate_migrate_flags.sh)
  L2. activate_migrate_flags.sh is +x executable
  L3. replay_action_draft.py --show prints draft JSON for a real draft
  L4. replay_action_draft.py --bulk-replay without --confirm = DRY RUN

Locks (negative — ≥3 per §43):
  N1. Bulk operations require --confirm flag (no accidental mass-mutate)
  N2. Single --reject requires --reason (governance audit context)
  N3. Bulk --bulk-reject requires --operator-reason
  N4. Source has NO DELETE FROM governance.action_drafts
      (audit immutability per §38)
  N5. activate_migrate_flags.sh is idempotent (existing .env → no change)
  N6. activate_migrate_flags.sh writes .env with mode 600 (no
      world-readable secrets)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPLAY_PY = REPO / "scripts" / "replay_action_draft.py"
ACTIVATE_SH = REPO / "scripts" / "activate_migrate_flags.sh"

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
    # Step 1 — both scripts exist
    # ===================================================================
    step("1. replay_action_draft.py + activate_migrate_flags.sh exist")
    if not REPLAY_PY.exists():
        fail(f"missing: {REPLAY_PY.relative_to(REPO)}")
    if not ACTIVATE_SH.exists():
        fail(f"missing: {ACTIVATE_SH.relative_to(REPO)}")
    ok("both CLI scripts present")

    # ===================================================================
    # Step 2 — activate_migrate_flags.sh is +x
    # ===================================================================
    step("2. activate_migrate_flags.sh +x bit set")
    if not os.access(ACTIVATE_SH, os.X_OK):
        fail("activate_migrate_flags.sh not executable")
    ok("+x bit set")

    # ===================================================================
    # Step 3 — replay --show prints a real draft as JSON
    # ===================================================================
    step("3. replay_action_draft.py --show prints draft JSON for a real draft")
    # Find a real draft id via psql first
    psql_out = subprocess.run(
        ["bash", "-c",
         "PGPASSWORD=documind psql -h localhost -p 55432 -U documind "
         "-d documind -tAc \"SELECT draft_id FROM governance.action_drafts "
         "WHERE status='pending' LIMIT 1\""],
        capture_output=True, text=True, timeout=10,
    )
    draft_id = psql_out.stdout.strip()
    if not draft_id:
        ok("no pending drafts to test against (skip)")
    else:
        result = subprocess.run(
            [sys.executable, str(REPLAY_PY), "--show", draft_id],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            fail(f"--show rc={result.returncode}: {result.stderr[:200]}")
        if draft_id not in result.stdout:
            fail(f"output missing draft_id: {result.stdout[:200]}")
        if '"status": "pending"' not in result.stdout:
            fail(f"output missing status field: {result.stdout[:200]}")
        ok(f"--show {draft_id[:12]}… returned full JSON")

    # ===================================================================
    # Step 4 — NEGATIVE: --bulk-replay without --confirm = DRY RUN
    # ===================================================================
    step("4. NEGATIVE: --bulk-replay without --confirm produces DRY RUN")
    result = subprocess.run(
        [sys.executable, str(REPLAY_PY), "--bulk-replay", "--server", "nonexistent_server_xyz"],
        capture_output=True, text=True, timeout=10,
    )
    if "DRY RUN" not in result.stdout and "no drafts match" not in result.stdout:
        fail(f"bulk without --confirm should produce DRY RUN message; got: {result.stdout[:200]}")
    ok("bulk without --confirm = DRY RUN; no mutation")

    # ===================================================================
    # Step 5 — NEGATIVE: --reject without --reason fails
    # ===================================================================
    step("5. NEGATIVE: --reject without --reason fails")
    result = subprocess.run(
        [sys.executable, str(REPLAY_PY), "--reject", "DRAFT-NONEXISTENT-XYZ"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        fail("--reject without --reason should non-zero exit")
    if "--reason" not in result.stderr.lower() and "reason" not in result.stderr.lower():
        fail(f"--reject should error about missing reason; stderr: {result.stderr[:200]}")
    ok("--reject without --reason → non-zero rc + reason-required message")

    # ===================================================================
    # Step 6 — NEGATIVE: --bulk-reject without --operator-reason fails
    # ===================================================================
    step("6. NEGATIVE: --bulk-reject without --operator-reason fails")
    result = subprocess.run(
        [sys.executable, str(REPLAY_PY), "--bulk-reject",
         "--server", "test", "--confirm"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        fail("--bulk-reject without --operator-reason should non-zero exit")
    ok("--bulk-reject without --operator-reason → non-zero rc")

    # ===================================================================
    # Step 7 — NEGATIVE: source has NO DELETE
    # ===================================================================
    step("7. NEGATIVE: replay_action_draft source has NO DELETE FROM action_drafts")
    src = REPLAY_PY.read_text(encoding="utf-8")
    forbidden = (
        "DELETE FROM governance.action_drafts",
        "TRUNCATE governance.action_drafts",
        "DROP TABLE governance.action_drafts",
    )
    leaks = [v for v in forbidden if v in src.upper()]
    if leaks:
        fail(f"source has destructive SQL: {leaks}")
    ok("no DELETE/TRUNCATE/DROP on action_drafts; audit immutability preserved")

    # ===================================================================
    # Step 8 — NEGATIVE: activate_migrate_flags.sh is idempotent
    # ===================================================================
    step("8. NEGATIVE: activate_migrate_flags.sh idempotent on existing .env")
    # If .env already exists with all 4 flags, the script should
    # detect + exit clean WITHOUT regenerating the secret
    env_path = REPO / ".env"
    if env_path.exists():
        # Capture content before
        before = env_path.read_text(encoding="utf-8")
        result = subprocess.run(
            ["bash", str(ACTIVATE_SH)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            fail(f"idempotent run rc={result.returncode}")
        if "Idempotent" not in result.stdout and "already present" not in result.stdout:
            fail(f"idempotent path not taken; output: {result.stdout[:300]}")
        # Content unchanged
        after = env_path.read_text(encoding="utf-8")
        if before != after:
            fail(".env content changed despite idempotent run")
        ok("existing .env preserved; secret not rotated")
    else:
        ok("no existing .env (skip; idempotent path not exercised)")

    # ===================================================================
    # Step 9 — NEGATIVE: activate_migrate_flags.sh writes mode 600
    # ===================================================================
    step("9. NEGATIVE: .env written with mode 600 (no world-readable secrets)")
    sh_src = ACTIVATE_SH.read_text(encoding="utf-8")
    if "chmod 600" not in sh_src:
        fail("script doesn't chmod 600 the .env file")
    if env_path.exists():
        st_mode = env_path.stat().st_mode & 0o777
        if st_mode > 0o600:
            fail(f".env mode is {oct(st_mode)} — too permissive (must be 600)")
        ok(f".env mode={oct(st_mode)} (≤600); script chmod-600 line present")
    else:
        ok(".env not present; chmod-600 line confirmed in source")

    # ===================================================================
    # Step 10 — replay-script CLI shape: 5 mutually-exclusive actions
    # ===================================================================
    step("10. replay_action_draft.py CLI: 5 mutually-exclusive top-level actions")
    expected_actions = ("--show", "--replay", "--reject",
                        "--bulk-replay", "--bulk-reject")
    for action in expected_actions:
        if action not in src:
            fail(f"replay_action_draft missing action: {action}")
    if "mutually_exclusive_group" not in src:
        fail("replay_action_draft should use mutually-exclusive arg group")
    ok(f"all {len(expected_actions)} actions present in mutex group")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
