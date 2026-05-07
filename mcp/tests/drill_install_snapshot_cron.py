#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/install_snapshot_cron.sh — installer contract.

Phase 5Q ships an idempotent installer for the daily snapshot cron
line. The drill exercises ONLY read-only modes (--dry-run, --status,
invalid mode) so a CI run never mutates the operator's crontab.

Mutating modes (--apply, --rollback) are validated structurally:
  * the script body contains the right cron schedule
  * the marker comment is unique (round-trip find/replace works)
  * the cron line shape matches what --dry-run announces

Eight steps. Six negative assertions.

  1. --dry-run (default) exits 0 and prints the cron line that would
     be installed.
  2. NEGATIVE: --status exits 0 and reports installed/not-installed.
  3. NEGATIVE: invalid mode exits 2 (bad usage, not silent success).
     Without a non-zero exit, a CI sanity check that runs the
     installer with a typoed flag wouldn't fail.
  4. NEGATIVE: cron line shape — the installer prints '5 0 * * *',
     /mnt/deepa/rag/.venv/bin/python (or PYTHON_BIN), the snapshot
     script absolute path, and the marker comment.
  5. NEGATIVE: marker uniqueness — the marker string appears in the
     installer source exactly enough times to support find/replace
     (in the MARKER assignment + at least one strip_managed call site)
     and is distinctive enough that grep -F won't false-positive on
     unrelated cron lines.
  6. NEGATIVE: PYTHON_BIN env override changes the cron line target.
  7. NEGATIVE: backup-file naming pattern — the installer creates
     /mnt/deepa/rag/.loop/cron-backups/crontab.before-*.bak files only on mutating modes.
     --dry-run and --status MUST NOT create backup files.
  8. POSITIVE: idempotency design — strip_managed handles "already
     installed" by removing prior managed line before appending the
     fresh one. Verified by inspecting the script body for the
     strip-then-append pattern.

Run: python3 mcp/tests/drill_install_snapshot_cron.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTALLER = REPO / "scripts" / "install_snapshot_cron.sh"
SNAPSHOT_SCRIPT = REPO / "scripts" / "council_stats_snapshot.py"


def _run(args: list[str], env_override: dict | None = None,
         timeout_s: float = 10.0) -> tuple[int, str, str]:
    """Run the installer in read-only mode. Returns (exit, stdout, stderr)."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        ["bash", str(INSTALLER), *args],
        capture_output=True, text=True,
        cwd=str(REPO), env=env, timeout=timeout_s,
    )
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    if not INSTALLER.exists():
        print(f"✗ pre-step: {INSTALLER} missing")
        return 1
    if not SNAPSHOT_SCRIPT.exists():
        print(f"✗ pre-step: {SNAPSHOT_SCRIPT} missing")
        return 1

    body = INSTALLER.read_text()

    # ── Step 1: --dry-run prints cron line, exits 0 ──
    rc, out, err = _run(["--dry-run"])
    if rc != 0:
        print(f"✗ step 1: --dry-run exit {rc}, expected 0\nstderr={err}")
        return 1
    if "[DRY-RUN] would install:" not in out:
        print("✗ step 1: --dry-run missing 'would install:' header")
        return 1
    if "no changes made" not in out:
        print("✗ step 1: --dry-run missing 'no changes made' footer "
              "(operator must know nothing happened)")
        return 1
    print("✓ step 1: --dry-run exits 0 with would-install + no-changes footer")

    # ── Step 2: NEGATIVE — --status reports correctly ──
    rc, out, err = _run(["--status"])
    if rc != 0:
        print(f"✗ step 2: --status exit {rc}, expected 0")
        return 1
    if "[STATUS]" not in out:
        print("✗ step 2: --status missing [STATUS] tag")
        return 1
    # Must say either 'installed' or 'no managed' — not silent
    if "installed" not in out and "no managed" not in out:
        print(f"✗ step 2: --status output ambiguous: {out!r}")
        return 1
    print("✓ step 2: --status exits 0 with installed/not-installed report")

    # ── Step 3: NEGATIVE — invalid mode exits 2 ──
    rc, out, err = _run(["--garbage-flag"])
    if rc != 2:
        print(f"✗ step 3: --garbage-flag exit {rc}, expected 2 "
              "(bad usage). Silent success here would mean a typoed "
              "CI flag fails to fail.")
        return 1
    if "unknown mode" not in err.lower() and "unknown mode" not in out.lower():
        print("✗ step 3: invalid-mode output didn't mention 'unknown mode'")
        return 1
    print("✓ step 3: invalid mode exits 2 (typo-safe CI behavior)")

    # ── Step 4: NEGATIVE — cron line shape ──
    # --dry-run prints the exact line that would be installed.
    rc, out, _ = _run(["--dry-run"])
    required = [
        "5 0 * * *",                              # schedule (00:05 UTC)
        "/mnt/deepa/rag/.venv/bin/python",         # default interpreter
        str(SNAPSHOT_SCRIPT),                      # absolute path to script
        "phase-5Q",                                # marker substring
        ">/dev/null 2>&1",                         # quiet redirection
    ]
    for token in required:
        if token not in out:
            print(f"✗ step 4: cron line missing token {token!r}\n{out}")
            return 1
    print(f"✓ step 4: cron line contains all {len(required)} required tokens")

    # ── Step 5: NEGATIVE — marker uniqueness ──
    # The marker is defined once in the MARKER assignment and referenced
    # as $MARKER elsewhere. Round-trip find/replace requires:
    #   * exactly ONE assignment line ('MARKER="...phase-5Q"')
    #   * at least TWO $MARKER references (strip_managed + status grep)
    # The literal phrase appearing 1× is fine — the references are by
    # variable, not by literal copy.
    marker_str = "managed by install_snapshot_cron.sh: phase-5Q"
    literal_occurrences = body.count(marker_str)
    if literal_occurrences != 1:
        print(f"✗ step 5: marker literal appears {literal_occurrences}× in "
              "source, expected exactly 1 (assignment only — refs use $MARKER)")
        return 1
    var_refs = len(re.findall(r"\$MARKER\b|\${MARKER}\b", body))
    if var_refs < 2:
        print(f"✗ step 5: $MARKER referenced {var_refs}× in source, "
              "expected ≥2 (cron line + grep filters)")
        return 1
    # Distinctiveness check: marker must NOT match common cron-line text.
    fake_cron = (
        "0 0 * * * /usr/bin/python3 /home/user/snapshot.py\n"
        "5 0 * * * /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/x.py\n"
    )
    proc = subprocess.run(
        ["grep", "-cF", marker_str],
        input=fake_cron, capture_output=True, text=True,
    )
    if proc.stdout.strip() != "0":
        print(f"✗ step 5: marker matched fake cron lines: count={proc.stdout!r}")
        return 1
    print(f"✓ step 5: marker uniquely defined (1 literal, {var_refs} $MARKER refs, "
          "0 false-positives)")

    # ── Step 6: NEGATIVE — PYTHON_BIN env override ──
    # Check the "would install" block ONLY — not the whole stdout.
    # The dry-run also prints the operator's CURRENT crontab (which
    # may contain unrelated lines using the default interpreter from
    # previous installations); checking the whole output would
    # falsely flag those.
    custom_python = "/some/custom/python3.42"
    rc, out, _ = _run(["--dry-run"], env_override={"PYTHON_BIN": custom_python})
    if rc != 0:
        print(f"✗ step 6: --dry-run with PYTHON_BIN exit {rc}, expected 0")
        return 1
    # Extract just the "would install:" block (stops at the next
    # "[DRY-RUN]" header).
    would_install_match = re.search(
        r"\[DRY-RUN\] would install:\s*\n(.*?)(?:\n\[DRY-RUN\]|\Z)",
        out, re.DOTALL,
    )
    if not would_install_match:
        print("✗ step 6: 'would install:' block not found in output")
        return 1
    would_install_block = would_install_match.group(1)
    if custom_python not in would_install_block:
        print(f"✗ step 6: PYTHON_BIN={custom_python!r} not in cron line. "
              f"would-install block:\n{would_install_block}")
        return 1
    if "/mnt/deepa/rag/.venv/bin/python " in would_install_block:
        pass
    elif custom_python not in would_install_block:
        print(f"✗ step 6: PYTHON_BIN={custom_python!r} not in cron line. "
              f"would-install block:\n{would_install_block}")
        return 1
    if "/mnt/deepa/rag/.venv/bin/python " in would_install_block and custom_python != "/mnt/deepa/rag/.venv/bin/python":
        print("✗ step 6: default interpreter still in would-install line "
              "even with PYTHON_BIN set")
        return 1
    print(f"✓ step 6: PYTHON_BIN override changes cron line to {custom_python!r}")

    # ── Step 7: NEGATIVE — read-only modes don't create backups ──
    # Snapshot the Deepa-hosted backup directory state BEFORE we run.
    backup_dir = REPO / ".loop" / "cron-backups"
    def backup_glob():
        return list(backup_dir.glob("crontab.before-*.bak"))
    before = {p.name for p in backup_glob()}
    # Run --dry-run and --status — neither should write a backup.
    _run(["--dry-run"])
    _run(["--status"])
    after = {p.name for p in backup_glob()}
    new_backups = after - before
    if new_backups:
        print(f"✗ step 7: read-only modes wrote {len(new_backups)} backups: "
              f"{new_backups}. Backups belong to mutating modes only.")
        return 1
    print("✓ step 7: read-only modes wrote 0 backups (mutating-only contract)")

    # ── Step 8: POSITIVE — idempotency via strip-then-append ──
    # Inspect the bash source for the strip_managed call site inside
    # --apply. The pattern:
    #   new=$(current_crontab | strip_managed)
    #   ...
    #   crontab -
    if not re.search(r"--apply\)\s*\n.*?strip_managed.*?crontab -",
                     body, re.DOTALL):
        print("✗ step 8: --apply doesn't strip_managed before "
              "appending; idempotency contract broken")
        return 1
    # And --rollback also strips the marker (so re-running is safe)
    if not re.search(r"--rollback\|--uninstall\)\s*\n.*?strip_managed",
                     body, re.DOTALL):
        print("✗ step 8: --rollback doesn't strip_managed; "
              "re-running rollback would be a no-op without this")
        return 1
    print("✓ step 8: --apply and --rollback both strip_managed first "
          "(idempotent contract)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
