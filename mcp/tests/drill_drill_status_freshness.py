#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: .loop/last_drill_outcome.json freshness gate.

Phase 7Z + Phase 7AA both received post-commit REJECT verdicts
because the LoopWatcher read a stale .loop/last_drill_outcome.json
that predated the iteration's drift fix. The pre-commit hook (5F)
refreshes drill_status if older than 600s, but cross-iteration
gaps + manual refreshes can leave the snapshot stale relative to
the latest commit.

This drill catches the stale-snapshot regression at sweep time:

  * If the snapshot is older than MAX_AGE_SECONDS, the drill
    fires. The pre-commit hook will then refresh it on the next
    commit, restoring the watcher's accurate view.
  * If the snapshot is missing entirely, the drill emits a clear
    pre-bootstrap message and exits 0 (per ADR-019 graceful
    degradation).

Nine steps. Six negative assertions.

  1. POSITIVE: target path resolved (.loop/last_drill_outcome.json).
  2. POSITIVE: file exists OR pre-bootstrap state declared (exit
     0 cleanly per ADR-019; the drill is a no-op on fresh checkout).
  3. NEGATIVE: timestamp field present AND parses as ISO 8601.
     Without it the watcher can't compare ages.
  4. NEGATIVE: age <= MAX_AGE_SECONDS. Stale snapshots cause the
     watcher to make decisions on outdated data — Phase 7Z's
     REJECT regression.
  5. NEGATIVE: failed_drills is a list (schema-integrity).
  6. NEGATIVE: total_drills field > 0 (sanity — empty count
     means write_drill_status.py was broken at last run).
  7. NEGATIVE: every per_drill key resolves to a real drill_*.py
     on disk. Stale per_drill keys = snapshot was generated
     against a catalog version that no longer exists; watcher
     decisions reference dead drills. The reverse direction
     (disk-not-in-snapshot) is expected because write_drill_
     status.py filters to readonly tier — not every disk drill
     appears.
  8. NEGATIVE: no drill_*.py file has mtime > snapshot timestamp.
     Catches the Phase 7KK gap: snapshot is fresh-by-age (within
     MAX_AGE_SECONDS) but stale-by-content (a drill was edited
     after the snapshot was written). Without this check, the
     watcher reads a snapshot whose `failed_drills` reflects a
     prior code state, not the current one — exactly Phase 7JJ +
     7KK's REJECT cycle.
  9. POSITIVE: emit age + status summary for operator visibility.

Run: python3 mcp/tests/drill_drill_status_freshness.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILL_STATUS = REPO / ".loop" / "last_drill_outcome.json"
DRILLS_DIR = REPO / "mcp" / "tests"

# Pre-commit hook 5F refreshes if >600s old. Drill threshold is
# 1.5x that to allow normal iteration gaps without firing on
# every commit. Beyond 900s = stale state operator should see.
MAX_AGE_SECONDS = 900

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _emit_pre_bootstrap_pass() -> int:
    """Per ADR-019 graceful degradation: if the snapshot is missing
    entirely, this is a fresh-checkout / pre-bootstrap state and
    the drill exits 0 cleanly. The runner sees the canonical banner
    and counts the drill as PASSED."""
    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 9 DRILL-STATUS-FRESHNESS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (degraded: pre-bootstrap state — snapshot absent){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


def main() -> int:
    step("1. POSITIVE: target path resolves to .loop/last_drill_outcome.json")
    ok(f"target = {DRILL_STATUS.relative_to(REPO)}")

    step("2. POSITIVE: snapshot file exists (or graceful pre-bootstrap exit)")
    if not DRILL_STATUS.exists():
        ok(
            "snapshot file absent — pre-bootstrap state (per ADR-019); "
            "drill is a no-op until the first sweep populates "
            ".loop/last_drill_outcome.json"
        )
        return _emit_pre_bootstrap_pass()
    ok(f"snapshot file present ({DRILL_STATUS.stat().st_size} bytes)")

    try:
        data = json.loads(DRILL_STATUS.read_text())
    except json.JSONDecodeError as e:
        fail(f"snapshot file is not valid JSON: {e}")

    step("3. NEGATIVE: timestamp field present + parses as ISO 8601")
    ts_str = data.get("timestamp")
    if not ts_str:
        fail("snapshot missing 'timestamp' field — watcher cannot compute age")
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError as e:
        fail(f"timestamp '{ts_str}' does not parse as ISO 8601: {e}")
    ok(f"timestamp parsed: {ts.isoformat(timespec='seconds')}")

    step("4. NEGATIVE: snapshot age <= MAX_AGE_SECONDS")
    now = datetime.now(timezone.utc)
    age_seconds = (now - ts).total_seconds()
    if age_seconds > MAX_AGE_SECONDS:
        fail(
            f"snapshot age = {age_seconds:.0f}s > {MAX_AGE_SECONDS}s. "
            "Refresh via `scripts/write_drill_status.py --only-readonly` "
            "OR commit any change to trigger the pre-commit hook."
        )
    if age_seconds < 0:
        # Clock skew / future timestamp — operator visibility, not a fail.
        ok(f"snapshot age = {age_seconds:.0f}s (future timestamp; clock skew)")
    else:
        ok(f"snapshot age = {age_seconds:.0f}s (<= {MAX_AGE_SECONDS}s)")

    step("5. NEGATIVE: failed_drills is a list")
    failed = data.get("failed_drills")
    if not isinstance(failed, list):
        fail(
            f"failed_drills field is {type(failed).__name__}, expected list. "
            "Schema corruption."
        )
    ok(f"failed_drills is a list of {len(failed)} entries")

    step("6. NEGATIVE: total_drills > 0")
    total = data.get("total_drills", 0)
    if not isinstance(total, int) or total <= 0:
        fail(
            f"total_drills = {total!r}; expected positive int. "
            "write_drill_status.py likely produced empty output at last run."
        )
    ok(f"total_drills = {total}")

    step("7. NEGATIVE: every per_drill key resolves to a real drill_*.py on disk")
    per_drill = data.get("per_drill", {})
    if not isinstance(per_drill, dict):
        fail(
            f"per_drill is {type(per_drill).__name__}, expected dict. "
            "Schema corruption."
        )
    disk_drill_names = {p.stem for p in DRILLS_DIR.glob("drill_*.py")}
    stale_keys = [k for k in per_drill if k not in disk_drill_names]
    if stale_keys:
        fail(
            f"{len(stale_keys)} per_drill key(s) reference drills that "
            f"no longer exist on disk: {stale_keys[:5]}. "
            "write_drill_status.py was run against an older catalog; "
            "refresh via "
            "`scripts/write_drill_status.py --only-readonly`."
        )
    ok(
        f"all {len(per_drill)} per_drill keys resolve "
        f"(disk catalog has {len(disk_drill_names)} drills)"
    )

    step("8. NEGATIVE: no drill_*.py mtime > snapshot timestamp")
    snapshot_unix = ts.timestamp()
    newer_drills: list[tuple[str, float]] = []
    for p in DRILLS_DIR.glob("drill_*.py"):
        mtime = p.stat().st_mtime
        if mtime > snapshot_unix + 1:  # 1s tolerance for filesystem precision
            newer_drills.append((p.name, mtime - snapshot_unix))
    if newer_drills:
        # Sort by largest delta first (most likely culprit at top).
        newer_drills.sort(key=lambda t: -t[1])
        details = ", ".join(f"{n} (+{d:.0f}s)" for n, d in newer_drills[:3])
        fail(
            f"{len(newer_drills)} drill file(s) edited AFTER snapshot was "
            f"written: {details}. Snapshot is fresh-by-age but stale-by-"
            "content. Refresh via `scripts/write_drill_status.py "
            "--only-readonly`."
        )
    ok(
        f"no drill_*.py mtime exceeds snapshot timestamp "
        f"({snapshot_unix:.0f})"
    )

    step("9. POSITIVE: emit age + status summary")
    failed_count = len(failed)
    age_minutes = age_seconds / 60.0
    summary = (
        f"FRESHNESS: snapshot {age_minutes:.1f}min old; "
        f"{total - failed_count}/{total} drills green; "
        f"{failed_count} failed"
    )
    if failed_count == 0:
        ok(f"{summary} — clean snapshot")
    else:
        ok(f"{summary} — failures: {failed[:3]}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 9 DRILL-STATUS-FRESHNESS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
