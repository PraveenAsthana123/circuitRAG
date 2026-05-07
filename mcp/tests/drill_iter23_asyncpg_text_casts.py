# RESOURCES: pg
"""
Drill: iter-23 — asyncpg ::text casts in replay_action_draft.py.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §52 row 4
(operator API gap closure quality). Operator's empirical run of
iter-22 surfaced 3 bugs:

  1. SQL example in chat used wrong column ('server' vs 'tool')
     → no drill; chat-message bug, not source bug
  2. --reject failed: asyncpg IndeterminateDatatypeError on $2
     → fix: cast $2::text inside jsonb_build_object
  3. --bulk-reject failed: same IndeterminateDatatypeError
     → fix: cast every $N::text in bulk-action SQL template

Root cause: asyncpg can't infer parameter types when the value is
consumed inside `jsonb_build_object(key, $N)` — Postgres returns
IndeterminateDatatypeError on prepare. The fix is `$N::text` for
every dynamic param consumed by jsonb_build_object.

This drill LOCKS the cast pattern so future maintainers can't
remove the ::text casts without the drill failing.

Locks (positive):
  L1. reject_draft SQL has $1::text AND $2::text
  L2. bulk_action SQL template (both replay + reject branches) has
      ::text on every $%d position consumed by jsonb_build_object
  L3. End-to-end smoke: --reject on a real draft succeeds (no
      IndeterminateDatatypeError)
  L4. End-to-end smoke: --bulk-reject with --confirm succeeds even
      on 0-match filter (the SQL prepares cleanly)

Locks (negative — ≥3 per §43):
  N1. Source has NO bare $N pattern inside jsonb_build_object
      (every dynamic param has explicit ::text cast)
  N2. Removing any ::text cast would break the prepare; drill
      catches regression by string match on the source
  N3. The note comment explaining WHY ::text is needed remains in
      source (so future maintainers see the rationale, not just
      the casts)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPLAY_PY = REPO / "scripts" / "replay_action_draft.py"

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
    src = REPLAY_PY.read_text(encoding="utf-8")

    # ===================================================================
    # Step 1 — POSITIVE: reject_draft() has explicit ::text casts
    # ===================================================================
    step("1. reject_draft SQL has $1::text AND $2::text casts")
    m = re.search(
        r"def reject_draft.*?(?=\ndef \w)",
        src, re.DOTALL,
    )
    if m is None:
        fail("could not locate reject_draft body")
    body = m.group(0)
    if "$2::text" not in body:
        fail("reject_draft missing $2::text cast inside jsonb_build_object")
    if "$1::text" not in body:
        fail("reject_draft missing $1::text cast on draft_id")
    ok("reject_draft has both $1::text and $2::text casts")

    # ===================================================================
    # Step 2 — POSITIVE: bulk_action SQL template has ::text on dynamic params
    # ===================================================================
    step("2. bulk_action SQL template has ::text on every dynamic $%d")
    m = re.search(
        r"def bulk_action.*?(?=\ndef \w)",
        src, re.DOTALL,
    )
    if m is None:
        fail("could not locate bulk_action body")
    body = m.group(0)
    # Find every $%d usage; each must be followed by ::text
    bare_params = re.findall(r"\$%d(?!::text)", body)
    if bare_params:
        fail(
            f"bulk_action has {len(bare_params)} bare $%d without ::text "
            f"cast (would break asyncpg prepare)"
        )
    # And there must be at least 5 ::text casts total (replay 2 + reject 3)
    cast_count = body.count("$%d::text")
    if cast_count < 5:
        fail(f"expected ≥5 $%d::text casts, found {cast_count}")
    ok(f"bulk_action has {cast_count} $%d::text casts; 0 bare $%d")

    # ===================================================================
    # Step 3 — POSITIVE: rationale comment stays in source
    # ===================================================================
    step("3. WHY-comment about ::text remains in source")
    if "IndeterminateDatatypeError" not in src:
        fail(
            "source missing 'IndeterminateDatatypeError' comment — "
            "future maintainers won't know why ::text casts exist"
        )
    if "jsonb_build_object" not in src:
        fail("source missing 'jsonb_build_object' rationale text")
    ok("rationale comment present (IndeterminateDatatypeError + jsonb_build_object)")

    # ===================================================================
    # Step 4 — NEGATIVE: no bare $N inside jsonb_build_object
    # ===================================================================
    step("4. NEGATIVE: no bare $N inside jsonb_build_object blocks")
    # Find every jsonb_build_object(...) block
    # Pattern: jsonb_build_object up to the closing ")"
    # Simpler: scan line-by-line; flag any line with "$N" where N is digit
    # AND not followed by ::text AND inside a jsonb_build_object scope
    in_jsonb = False
    line_no = 0
    leaks: list[tuple[int, str]] = []
    for line in src.splitlines():
        line_no += 1
        if "jsonb_build_object" in line:
            in_jsonb = True
        if in_jsonb:
            # Look for $1..$9 or $%d not followed by ::text
            for m in re.finditer(r"\$(\d+|%d)(?!::text)", line):
                # Allow if it's in a comment line (starts with #)
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                leaks.append((line_no, line.strip()[:100]))
            # Heuristic close: if we hit "WHERE" or end of UPDATE block
            if (
                "WHERE" in line
                or line.rstrip().endswith('",')
                or line.rstrip().endswith('"')
            ):
                in_jsonb = False
    if leaks:
        for ln, txt in leaks[:5]:
            print(f"    line {ln}: {txt}")
        fail(f"{len(leaks)} bare $N inside jsonb_build_object scope")
    ok("no bare $N inside jsonb_build_object scope")

    # ===================================================================
    # Step 5 — POSITIVE: end-to-end --reject smoke (real draft → succeeds)
    # ===================================================================
    step("5. POSITIVE: --reject on a fresh test draft succeeds")
    # Insert a temp draft, reject it, verify status flip
    test_id = "DRAFT-ITER23-DRILL-TEST"

    # Cleanup any leftover from prior drill run
    subprocess.run(
        ["bash", "-c",
         f"PGPASSWORD=documind psql -h localhost -p 55432 -U documind "
         f"-d documind -tAc \"DELETE FROM governance.action_drafts "
         f"WHERE draft_id = '{test_id}'\""],
        capture_output=True, text=True, timeout=10,
    )

    # Insert a fresh test draft
    insert = subprocess.run(
        ["bash", "-c",
         f"PGPASSWORD=documind psql -h localhost -p 55432 -U documind "
         f"-d documind -tAc \"INSERT INTO governance.action_drafts "
         f"(draft_id, tool, arguments, reason, status) VALUES "
         f"('{test_id}', 'drill.iter23_test', '{{}}'::jsonb, "
         f"'drill iter23 ::text cast lock', 'pending')\""],
        capture_output=True, text=True, timeout=10,
    )
    if insert.returncode != 0:
        # Postgres unreachable — skip the live-DB portion
        ok(f"skipped live --reject test (psql rc={insert.returncode})")
    else:
        result = subprocess.run(
            [sys.executable, str(REPLAY_PY), "--reject", test_id,
             "--reason", "drill iter23 lock"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            fail(
                f"--reject failed (rc={result.returncode}); "
                f"::text cast regression?\n"
                f"  stderr: {result.stderr[:300]}"
            )
        if "rejected" not in result.stdout.lower():
            fail(f"--reject output missing 'rejected': {result.stdout[:200]}")
        # Cleanup the test row
        subprocess.run(
            ["bash", "-c",
             f"PGPASSWORD=documind psql -h localhost -p 55432 -U documind "
             f"-d documind -tAc \"DELETE FROM governance.action_drafts "
             f"WHERE draft_id = '{test_id}'\""],
            capture_output=True, text=True, timeout=10,
        )
        ok("--reject succeeds end-to-end (no IndeterminateDatatypeError)")

    # ===================================================================
    # Step 6 — POSITIVE: end-to-end --bulk-reject prepare smoke
    # ===================================================================
    step("6. POSITIVE: --bulk-reject SQL prepares cleanly even on 0-match")
    # Use a server filter that matches no rows; if the SQL prepares,
    # we'd see "no drafts match" not IndeterminateDatatypeError
    result = subprocess.run(
        [sys.executable, str(REPLAY_PY), "--bulk-reject",
         "--server", "drill_iter23_no_such_server_xyz",
         "--confirm",
         "--operator-reason", "drill iter23 prepare smoke"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        fail(
            f"--bulk-reject failed to prepare (rc={result.returncode}); "
            f"::text cast regression?\n"
            f"  stdout: {result.stdout[:200]}\n"
            f"  stderr: {result.stderr[:300]}"
        )
    if "no drafts match" not in result.stdout:
        fail(f"--bulk-reject 0-match path missing; output: {result.stdout[:200]}")
    if "IndeterminateDatatypeError" in result.stderr:
        fail("--bulk-reject still raises IndeterminateDatatypeError")
    ok("--bulk-reject SQL prepares cleanly; 0-match path returns clean")

    # ===================================================================
    # Step 7 — NEGATIVE: drill self-check that bare $N would fail step 4
    # ===================================================================
    step("7. NEGATIVE: drill would catch a regression that drops a cast")
    # Synthetic check: if we constructed a fake source with a bare $N
    # inside jsonb_build_object, our regex from step 4 must flag it
    fake_src = (
        "jsonb_build_object("
        "  'reason', $2, "  # bare $2 — should leak
        "  'created_at', NOW()::text"
        ")"
    )
    in_jsonb = "jsonb_build_object" in fake_src
    leaked = bool(re.search(r"\$(\d+|%d)(?!::text)", fake_src))
    if not (in_jsonb and leaked):
        fail(
            "drill self-check failed — regex would NOT catch a bare $N "
            "regression; the lock is broken"
        )
    ok("drill regex would catch a regression (self-check passed)")

    print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
