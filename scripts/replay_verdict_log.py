#!/usr/bin/env python3
"""Replay .loop/watcher.log: find REJECT verdicts, optionally revert.

Closes the autonomous correction loop. Phase 4B's post-commit hook
appends APPROVE/HOLD/REJECT verdicts; this script reads them and
either:

  * default (dry-run): prints the list of pending REJECT commits
    + suggested `git revert` commands. Operator decides.
  * --apply: actually runs `git revert --no-edit <sha>` for each
    pending REJECT. Idempotent via .loop/replayed.log so a re-run
    doesn't double-revert.

Why default to dry-run + opt-in --apply:

  * Auto-reverting commits is operationally aggressive. A
    transient drill flake (LLM provider timeout, e.g.) would
    REJECT a perfectly good commit and the auto-revert would
    undo correct work.
  * The dry-run mode is read-only - safe to run repeatedly to
    inspect "what would I revert?".
  * --apply is the explicit consent: operator has reviewed the
    list AND confirmed the underlying drill failures are real.

Composes with:
  * Phase 4A LoopWatcher - the source of REJECT verdicts
  * Phase 4B post-commit hook - the writer of watcher.log
  * Phase 4C drill-status writer - the source of rule 1's input

The full Phase 4 chain end-to-end:

    write_drill_status -> commit -> hook fires LoopWatcher
        -> watcher.log appends verdict
        -> replay_verdict_log [--apply] surfaces REJECT entries
        -> revert + replayed.log marks processed
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_WATCHER_LOG = REPO / ".loop" / "watcher.log"
DEFAULT_REPLAYED_LOG = REPO / ".loop" / "replayed.log"

log = logging.getLogger("replay_verdict_log")


@dataclass(frozen=True)
class VerdictEntry:
    """One line from watcher.log."""

    timestamp: str
    commit_sha: str          # 12-char truncated
    verdict: str             # APPROVE | HOLD | REJECT
    rule_fired: int
    reason: str
    blocking_files: list[str]
    raw: dict                # full row, for audit


@dataclass(frozen=True)
class ReplayResult:
    """One revert attempt's outcome."""

    commit_sha: str
    success: bool
    error: str | None
    timestamp: str


def parse_watcher_log(path: Path) -> list[VerdictEntry]:
    """Read newline-delimited JSON. Malformed lines are logged and
    skipped (don't sink the whole replay)."""
    entries: list[VerdictEntry] = []
    if not path.exists():
        return entries
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            log.warning(
                "replay_log_malformed_line line=%d err=%s preview=%r",
                i, exc, line[:80],
            )
            continue
        entries.append(VerdictEntry(
            timestamp=str(data.get("timestamp", "")),
            commit_sha=str(data.get("commit_sha", "")),
            verdict=str(data.get("verdict", "")),
            rule_fired=int(data.get("rule_fired", 0)),
            reason=str(data.get("reason", "")),
            blocking_files=list(data.get("blocking_files", [])),
            raw=data,
        ))
    return entries


def load_replayed_set(path: Path) -> set[str]:
    """Each line in replayed.log is one commit_sha. Return as a set
    for O(1) idempotency lookup."""
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text().splitlines():
        sha = line.strip()
        if sha:
            out.add(sha)
    return out


def find_pending_rejects(
    entries: list[VerdictEntry],
    replayed: set[str],
) -> list[VerdictEntry]:
    """REJECT verdicts whose commit_sha isn't already in replayed.
    APPROVE + HOLD are filtered out."""
    return [
        e for e in entries
        if e.verdict == "REJECT" and e.commit_sha not in replayed
    ]


def render_revert_plan(rejects: list[VerdictEntry]) -> str:
    """Pretty-print the dry-run plan."""
    if not rejects:
        return "No pending REJECT verdicts. Nothing to revert."
    lines = [
        f"Pending REJECT verdicts: {len(rejects)} commit(s) to revert.",
        "",
    ]
    for e in rejects:
        lines.append(f"  - {e.commit_sha}  rule_fired={e.rule_fired}  "
                     f"reason={e.reason!r}")
        if e.blocking_files:
            lines.append(f"      blocking_files: {e.blocking_files[:3]}")
    lines.append("")
    lines.append("Suggested revert commands (run with --apply to auto-execute):")
    for e in rejects:
        lines.append(f"  git revert --no-edit {e.commit_sha}")
    return "\n".join(lines)


def _git_revert(sha: str) -> tuple[bool, str | None]:
    """Default revert function. Returns (success, error_msg)."""
    try:
        result = subprocess.run(
            ["git", "revert", "--no-edit", sha],
            capture_output=True, text=True, cwd=str(REPO),
        )
        if result.returncode == 0:
            return True, None
        return False, (
            result.stderr or result.stdout or "unknown error"
        )[-300:].strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def apply_reverts(
    rejects: list[VerdictEntry],
    *,
    revert_fn: Callable[[str], tuple[bool, str | None]] = _git_revert,
    replayed_log: Path = DEFAULT_REPLAYED_LOG,
) -> list[ReplayResult]:
    """Run revert_fn for each pending reject. Successes are
    appended to replayed_log immediately - if a later revert fails,
    the earlier ones STAY recorded (idempotent partial progress)."""
    results: list[ReplayResult] = []
    replayed_log.parent.mkdir(parents=True, exist_ok=True)
    for e in rejects:
        success, err = revert_fn(e.commit_sha)
        result = ReplayResult(
            commit_sha=e.commit_sha,
            success=success,
            error=err,
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        results.append(result)
        if success:
            with replayed_log.open("a") as f:
                f.write(f"{e.commit_sha}\n")
        else:
            log.warning(
                "replay_revert_failed sha=%s err=%s",
                e.commit_sha, (err or "")[:120],
            )
    return results


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watcher-log", default=str(DEFAULT_WATCHER_LOG),
        help="path to watcher.log (default .loop/watcher.log)",
    )
    parser.add_argument(
        "--replayed-log", default=str(DEFAULT_REPLAYED_LOG),
        help="path to replayed.log (default .loop/replayed.log)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually run git revert (default: dry-run / report only)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    watcher_log = Path(args.watcher_log)
    replayed_log = Path(args.replayed_log)

    entries = parse_watcher_log(watcher_log)
    replayed = load_replayed_set(replayed_log)
    pending = find_pending_rejects(entries, replayed)

    if not args.apply:
        # Dry-run mode
        print(render_revert_plan(pending))
        return 0

    if not pending:
        print("No pending REJECT verdicts. Nothing to revert.")
        return 0

    print(f"[replay] applying {len(pending)} revert(s)...", file=sys.stderr)
    results = apply_reverts(pending, replayed_log=replayed_log)
    n_success = sum(1 for r in results if r.success)
    n_fail = len(results) - n_success
    print(
        f"[replay] {n_success} reverted, {n_fail} failed; "
        f"see {replayed_log} for processed shas",
        file=sys.stderr,
    )
    if n_fail > 0:
        for r in results:
            if not r.success:
                print(f"  FAILED {r.commit_sha}: {r.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli())
