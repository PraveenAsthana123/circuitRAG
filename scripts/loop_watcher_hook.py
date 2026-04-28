#!/usr/bin/env python3
"""Post-commit watcher hook - runs LoopWatcher on the latest commit.

Invoked by .git/hooks/post-commit (or scripts/git-hooks/post-commit
when core.hooksPath points at it). Reads HEAD's commit metadata,
loads the most recent drill status from disk, applies LoopWatcher's
deterministic rules, appends a JSON-line verdict to
.loop/watcher.log.

ADVISORY ONLY - always exits 0. The hook does NOT block the commit
(post-commit hooks can't anyway). It writes a verdict the operator
can consult; subsequent iterations of the autonomous loop check the
log to decide whether to proceed.

Drill exercises this script's main() with explicit args, bypassing
git/disk so it runs in tier 1 without a working repo.

Read the verdict log:
    cat .loop/watcher.log | jq

Disable: remove or rename .loop/watcher.log; the hook still runs
but downstream consumers see no log to act on.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATUS_PATH = REPO / ".loop" / "last_drill_outcome.json"
DEFAULT_LOG_PATH = REPO / ".loop" / "watcher.log"

log = logging.getLogger("loop_watcher_hook")


def _load_loop_watcher():
    """Load LoopWatcher via importlib so this script doesn't need
    documind_core / app.services on PYTHONPATH."""
    p = REPO / "services" / "sidecar-advisor" / "loop_watcher.py"
    spec = importlib.util.spec_from_file_location("_lw_for_hook", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_lw_for_hook"] = mod
    spec.loader.exec_module(mod)
    return mod


def _git_head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, cwd=REPO,
    ).stdout.strip()


def _git_head_message() -> str:
    return subprocess.run(
        ["git", "log", "-1", "--format=%B", "HEAD"],
        capture_output=True, text=True, check=True, cwd=REPO,
    ).stdout.strip()


def _git_head_files() -> list[str]:
    out = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        capture_output=True, text=True, check=True, cwd=REPO,
    ).stdout
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _git_recent_files_per_commit(window: int = 3) -> list[list[str]]:
    """Files touched in each of the last `window` commits BEFORE
    HEAD. Used by rule 5 (thrash detection)."""
    out = subprocess.run(
        ["git", "log", "-n", str(window), "--format=COMMIT %H",
         "--name-only", "HEAD~1..HEAD~" + str(window + 1)],
        capture_output=True, text=True, check=False, cwd=REPO,
    ).stdout
    # If there aren't enough commits, return what we have
    commits: list[list[str]] = []
    current: list[str] = []
    for ln in out.splitlines():
        if ln.startswith("COMMIT "):
            if current:
                commits.append(current)
                current = []
        elif ln.strip():
            current.append(ln.strip())
    if current:
        commits.append(current)
    return commits


def _load_drill_status(path: Path) -> tuple[list[str], int]:
    """Read .loop/last_drill_outcome.json. Format:
        {"failed_drills": [...], "total_drills": N}
    Missing/corrupt -> default to (no failures, 0 drills) so the
    hook doesn't false-reject on a fresh repo."""
    if not path.exists():
        log.info("hook_no_drill_status path=%s assuming green", path)
        return [], 0
    try:
        data = json.loads(path.read_text())
        return list(data.get("failed_drills", [])), int(data.get("total_drills", 0))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        log.warning("hook_drill_status_corrupt path=%s err=%s", path, exc)
        return [], 0


def _append_log(log_path: Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main(
    *,
    commit_sha: str | None = None,
    commit_message: str | None = None,
    files_touched: list[str] | None = None,
    drill_status_path: Path | None = None,
    log_path: Path | None = None,
    recent_files_per_commit: list[list[str]] | None = None,
    policy_path: Path | None = None,
) -> dict:
    """Run the watcher and return the entry that was logged.

    All optional args default to deriving from git/disk. Drill
    passes explicit values to test deterministically without git.
    """
    lw_mod = _load_loop_watcher()
    LoopWatcher = lw_mod.LoopWatcher
    CommitContext = lw_mod.CommitContext
    DrillContext = lw_mod.DrillContext

    if commit_sha is None:
        commit_sha = _git_head_sha()
    if commit_message is None:
        commit_message = _git_head_message()
    if files_touched is None:
        files_touched = _git_head_files()
    if recent_files_per_commit is None:
        recent_files_per_commit = _git_recent_files_per_commit(window=3)

    status_path = drill_status_path or DEFAULT_STATUS_PATH
    log_target = log_path or DEFAULT_LOG_PATH
    policy = policy_path or (REPO / "docs" / "NEXT_POLICY.md")

    failed_drills, total_drills = _load_drill_status(status_path)

    watcher = LoopWatcher(
        policy_path=policy if policy.exists() else None,
    )
    decision = watcher.decide(
        commit=CommitContext(
            sha=commit_sha,
            message=commit_message,
            files_touched=list(files_touched),
        ),
        drills=DrillContext(
            failed_drills=list(failed_drills),
            total_drills=int(total_drills),
        ),
        recent_files_per_commit=recent_files_per_commit,
    )

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit_sha": commit_sha[:12],
        "commit_message_first_line": commit_message.splitlines()[0]
            if commit_message else "",
        "files_touched_count": len(files_touched),
        "verdict": decision.verdict,
        "rule_fired": decision.rule_fired,
        "reason": decision.reason,
        "blocking_files": decision.blocking_files,
        "drill_outcome": "green" if not failed_drills else "FAILED",
        "drill_failures": failed_drills,
    }
    _append_log(log_target, entry)
    return entry


def cli() -> int:
    """CLI wrapper - always exit 0 (advisory-only contract)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", action="store_true",
                        help="echo the verdict to stderr")
    args = parser.parse_args()

    try:
        entry = main()
        if args.print:
            print(
                f"loop_watcher: {entry['verdict']} "
                f"(rule {entry['rule_fired']}) - {entry['reason']}",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001
        log.error("hook_unexpected_failure err=%s", exc)
        # Even on internal failure, exit 0 - we're advisory only.
    return 0


if __name__ == "__main__":
    sys.exit(cli())
