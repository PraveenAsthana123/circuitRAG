#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/migrate_ollama_to_deepa.sh structural contract.

Tier-2 migration script — touches Ollama daemon + systemd
override + 42GB models. Higher risk than Tier-1 caches because:

  1. Ollama daemon must be stopped before rsync (running models
     would be corrupted)
  2. systemd override file edits affect daemon startup forever
  3. Daemon restart fails if OLLAMA_MODELS path is wrong
  4. Recovery requires sudo + matching the original ownership

This drill verifies the script's safety invariants. Eight steps,
six negative assertions.

  1. Script exists + executable bit set.
  2. NEGATIVE: defaults to dry-run (sudo not invoked at all in
     dry-run — operator can preview safely).
  3. NEGATIVE: declares set -euo pipefail.
  4. NEGATIVE: ALL 4 modes present (dry-run/apply/rollback/finalize)
     identical contract to the Tier-1 cache script.
  5. NEGATIVE: apply path snapshots `ollama list` BEFORE stopping
     daemon. Without snapshot, post-migration verification can't
     compare against the truth.
  6. NEGATIVE: chown ollama:ollama on the destination AFTER
     rsync. Daemon runs as user `ollama`; without chown, daemon
     can't read the models even though files exist.
  7. NEGATIVE: systemd override is BACKED UP before being
     overwritten. If user already had an override (rare but
     possible), rollback/failure recovery needs to restore it.
  8. NEGATIVE: rollback preserves system files and finalize
     requires an explicit delete-ack flag.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import os
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "migrate_ollama_to_deepa.sh"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def main():
    # Step 1: file + executable
    step("1. migrate_ollama_to_deepa.sh exists + executable")
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT}")
    if not os.access(SCRIPT, os.X_OK):
        fail(f"not executable: {SCRIPT}")
    text = SCRIPT.read_text()
    if len(text) < 2000:
        fail(f"script too short: {len(text)} chars")
    ok(f"script exists ({len(text)} chars), +x set")

    # Step 2: dry-run default
    step("2. NEGATIVE: dry-run is default; sudo NOT invoked unconditionally")
    if 'MODE="dry-run"' not in text:
        fail("MODE doesn't default to dry-run")
    # Older parser used `case "${1:-}"`; newer parser iterates over
    # all args and leaves MODE at its initial dry-run default when
    # no mode flags are supplied. Either shape is acceptable.
    has_explicit_empty_branch = re.search(r'""\)\s*MODE="dry-run"', text)
    has_default_initializer = re.search(r'^\s*MODE="dry-run"\s*$', text, re.MULTILINE)
    if not has_explicit_empty_branch and not has_default_initializer:
        fail("dry-run default missing (neither explicit empty-arg branch nor initializer found)")
    # require_sudo() must NOT be called in do_dry_run
    dr_match = re.search(r"do_dry_run\(\)\s*{(.*?)\n}", text, re.DOTALL)
    if not dr_match:
        fail("do_dry_run() function not found")
    if "require_sudo" in dr_match.group(1):
        fail(
            "do_dry_run() calls require_sudo. Dry-run must NOT need "
            "sudo - operator should be able to preview the plan "
            "without auth prompt."
        )
    ok("dry-run default; require_sudo NOT in do_dry_run path")

    # Step 3: set -euo pipefail
    step("3. NEGATIVE: set -euo pipefail")
    if "set -euo pipefail" not in text:
        fail("missing fail-fast flags")
    ok("set -euo pipefail declared")

    # Step 4: all 4 modes
    step("4. NEGATIVE: all 4 modes (dry-run/apply/rollback/finalize)")
    for fn in ["do_dry_run", "do_apply", "do_rollback", "do_finalize"]:
        if f"{fn}()" not in text:
            fail(f"function {fn}() missing")
    branches = re.findall(
        r"^\s*(dry-run|apply|rollback|finalize)\)\s*do_", text, re.MULTILINE,
    )
    if len(set(branches)) < 4:
        fail(f"main case missing branches: have {sorted(set(branches))}")
    ok("all 4 mode functions defined + routed")

    # Step 5: snapshot before stop
    step(
        "5. NEGATIVE: apply snapshots `ollama list` BEFORE stopping daemon"
    )
    apply_match = re.search(r"do_apply\(\)\s*{(.*?)^\}", text,
                             re.DOTALL | re.MULTILINE)
    if not apply_match:
        fail("do_apply() body not found")
    body = apply_match.group(1)
    snapshot_pos = body.find("ollama list")
    stop_pos = body.find("systemctl stop ollama")
    if snapshot_pos < 0:
        fail("do_apply doesn't capture `ollama list` for verification")
    if stop_pos < 0:
        fail("do_apply doesn't stop the daemon")
    if snapshot_pos > stop_pos:
        fail(
            f"snapshot at {snapshot_pos} comes AFTER daemon stop at "
            f"{stop_pos}. After stop, ollama list returns nothing - "
            f"can't snapshot."
        )
    ok(f"snapshot captured before stop (pos {snapshot_pos} < {stop_pos})")

    # Step 6: chown after rsync
    step(
        "6. NEGATIVE: chown ollama:ollama on dest after rsync "
        "(daemon must be able to read its models)"
    )
    if "chown -R ollama:ollama" not in text and "chown -R ollama" not in text:
        fail(
            "no chown on dest. Without it, daemon (running as ollama "
            "user) can't read the migrated models even though files "
            "exist - daemon would start but `ollama list` returns empty."
        )
    # chown should appear AFTER rsync (within do_apply)
    chown_pos = body.find("chown")
    rsync_pos = body.find("rsync")
    if chown_pos < 0 or rsync_pos < 0:
        fail("can't position chown vs rsync")
    if chown_pos < rsync_pos:
        fail(f"chown at {chown_pos} BEFORE rsync at {rsync_pos}")
    ok(f"chown ollama:ollama after rsync (pos {chown_pos} > {rsync_pos})")

    # Step 7: override backup
    step(
        "7. NEGATIVE: existing systemd override is backed up before "
        "being overwritten (rare-but-possible)"
    )
    if "override_backed_up" not in text and "${SYSTEMD_OVERRIDE}.pre" not in text:
        fail(
            "no backup logic for an existing override. If a user "
            "already has /etc/systemd/system/ollama.service.d/override.conf "
            "with custom Environment vars, our migration would silently "
            "wipe them."
        )
    if not re.search(r"\.pre-\$\{?DATE_TAG\}?", text):
        fail("override backup doesn't tag with date — collisions possible")
    ok("existing override backed up to .pre-<DATE_TAG> before overwrite")

    # Step 8: rollback preserves override + finalize needs explicit ack
    step(
        "8. NEGATIVE: rollback preserves override and finalize "
        "requires explicit delete ack"
    )
    rb_match = re.search(r"do_rollback\(\)\s*{(.*?)^\}", text,
                          re.DOTALL | re.MULTILINE)
    if not rb_match:
        fail("do_rollback() body not found")
    rb_body = rb_match.group(1)
    if "mv \"$bak\" \"$OLLAMA_SRC\"" not in rb_body and "mv \"$bak\" $OLLAMA_SRC" not in rb_body:
        fail("rollback doesn't mv .bak back to source")
    if "restore_override_safely" not in rb_body:
        fail(
            "rollback doesn't call restore_override_safely(). "
            "System override recovery must preserve or restore files, "
            "not silently delete them."
        )
    if "daemon-reload" not in rb_body:
        fail("rollback doesn't run daemon-reload after override removal")
    final_match = re.search(r"do_finalize\(\)\s*{(.*?)^\}", text,
                            re.DOTALL | re.MULTILINE)
    if not final_match:
        fail("do_finalize() body not found")
    final_body = final_match.group(1)
    if "--yes-i-accept-delete" not in text or "FINALIZE_DELETE_ACK" not in final_body:
        fail(
            "finalize doesn't require an explicit delete-ack flag. "
            "Deleting the backup must be a separate acknowledged action."
        )
    ok("rollback preserves override state; finalize requires explicit delete ack")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 MIGRATE-OLLAMA STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
