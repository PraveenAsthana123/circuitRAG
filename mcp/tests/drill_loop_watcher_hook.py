#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/loop_watcher_hook.py invokes LoopWatcher cleanly
and appends a verdict log entry per commit.

The hook is advisory-only - always exits 0, never blocks the
commit. This drill exercises the hook's main() with explicit args
(bypassing git/disk) to verify the verdict-logging contract.

Eight steps. Six negative assertions.

  1. Happy path: APPROVE verdict logged with all required fields.
  2. Hook on drill failure -> log entry has verdict=REJECT,
     rule_fired=1.
  3. NEGATIVE: missing drill_status_path -> graceful default to
     all-green (don't false-reject on a fresh repo).
  4. NEGATIVE: corrupt drill_status JSON -> graceful default,
     no crash.
  5. NEGATIVE: log file is APPENDED (not overwritten) - multiple
     hook invocations leave a JSON-line history.
  6. NEGATIVE: parent directory of log_path auto-created if
     missing.
  7. NEGATIVE: hook's CLI wrapper exits 0 even when LoopWatcher
     imports fail (advisory-only contract).
  8. NEGATIVE: log entry timestamp is ISO-8601 UTC + commit_sha
     truncated to 12 chars (audit + cardinality cap).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]

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


def _load_hook():
    p = REPO / "scripts" / "loop_watcher_hook.py"
    spec = importlib.util.spec_from_file_location("loop_watcher_hook", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loop_watcher_hook"] = mod
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()


def main():
    # Step 1: happy path
    step("1. happy path: APPROVE verdict logged with all fields")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        log_path = tmp_dir / "watcher.log"
        status_path = tmp_dir / "status.json"
        status_path.write_text(json.dumps({
            "failed_drills": [],
            "total_drills": 28,
        }))
        entry = hook.main(
            commit_sha="abc123def456789",
            commit_message="feat: shipping new agent",
            files_touched=[
                "services/sidecar-advisor/foo.py",
                "mcp/tests/drill_foo.py",
            ],
            drill_status_path=status_path,
            log_path=log_path,
            recent_files_per_commit=[],
        )
        if entry["verdict"] != "APPROVE":
            fail(f"expected APPROVE, got {entry['verdict']}")
        if entry["rule_fired"] != 6:
            fail(f"rule_fired should be 6 (default), got {entry['rule_fired']}")
        # Verify required fields present
        for field in ["timestamp", "commit_sha", "commit_message_first_line",
                      "files_touched_count", "verdict", "rule_fired",
                      "reason", "blocking_files", "drill_outcome"]:
            if field not in entry:
                fail(f"log entry missing field: {field}")
        # Verify log file contents
        log_content = log_path.read_text()
        if not log_content.strip():
            fail("log file empty after main()")
        ok(f"verdict={entry['verdict']} fields={len(entry)}")

    # Step 2: drill failure -> REJECT
    step("2. drill failure -> log entry has verdict=REJECT, rule_fired=1")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        status_path = tmp_dir / "status.json"
        status_path.write_text(json.dumps({
            "failed_drills": ["drill_xyz"],
            "total_drills": 28,
        }))
        entry = hook.main(
            commit_sha="bad999",
            commit_message="feat: broke a drill",
            files_touched=["services/sidecar-advisor/x.py"],
            drill_status_path=status_path,
            log_path=tmp_dir / "watcher.log",
            recent_files_per_commit=[],
        )
        if entry["verdict"] != "REJECT":
            fail(f"expected REJECT on drill failure, got {entry['verdict']}")
        if entry["rule_fired"] != 1:
            fail(f"rule_fired should be 1, got {entry['rule_fired']}")
        if entry["drill_outcome"] != "FAILED":
            fail(f"drill_outcome should be FAILED: {entry['drill_outcome']}")
        if "drill_xyz" not in entry["drill_failures"]:
            fail(f"failed drill name lost: {entry['drill_failures']}")
        ok(f"verdict={entry['verdict']} drill_failures={entry['drill_failures']}")

    # Step 3: NEGATIVE - missing drill status -> graceful default
    step("3. NEGATIVE: missing drill_status_path -> default to all-green")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Don't create status_path
        missing_status = tmp_dir / "does_not_exist.json"
        entry = hook.main(
            commit_sha="fresh1",
            commit_message="feat: fresh repo",
            files_touched=["scripts/foo.py"],
            drill_status_path=missing_status,
            log_path=tmp_dir / "watcher.log",
            recent_files_per_commit=[],
        )
        if entry["verdict"] != "APPROVE":
            fail(f"missing status should default to APPROVE, got {entry['verdict']}")
        if entry["drill_outcome"] != "green":
            fail(f"missing status should report green, got {entry['drill_outcome']}")
        ok(f"missing status -> verdict={entry['verdict']} drill_outcome=green")

    # Step 4: NEGATIVE - corrupt status JSON
    step("4. NEGATIVE: corrupt drill_status JSON -> graceful default")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        status_path = tmp_dir / "corrupt.json"
        status_path.write_text("this is not valid json {[}")
        entry = hook.main(
            commit_sha="corrupt1",
            commit_message="feat: corrupt status",
            files_touched=["scripts/x.py"],
            drill_status_path=status_path,
            log_path=tmp_dir / "watcher.log",
            recent_files_per_commit=[],
        )
        # Hook should NOT crash; should default to all-green
        if entry["verdict"] != "APPROVE":
            fail(f"corrupt status should default to APPROVE, got {entry['verdict']}")
        ok(f"corrupt JSON gracefully defaulted to APPROVE")

    # Step 5: NEGATIVE - log file APPENDED, not overwritten
    step("5. NEGATIVE: log file appended (3 entries from 3 invocations)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        log_path = tmp_dir / "watcher.log"
        status_path = tmp_dir / "status.json"
        status_path.write_text(json.dumps({"failed_drills": [], "total_drills": 1}))
        for i in range(3):
            hook.main(
                commit_sha=f"sha_{i}",
                commit_message=f"feat: commit {i}",
                files_touched=["scripts/x.py"],
                drill_status_path=status_path,
                log_path=log_path,
                recent_files_per_commit=[],
            )
        lines = log_path.read_text().strip().split("\n")
        if len(lines) != 3:
            fail(f"expected 3 log lines after 3 invocations, got {len(lines)}")
        # Each line should be valid JSON
        shas = [json.loads(ln)["commit_sha"] for ln in lines]
        if shas != ["sha_0", "sha_1", "sha_2"]:
            fail(f"sha order drift in log: {shas}")
        ok(f"3 invocations -> 3 log lines (append, not overwrite)")

    # Step 6: NEGATIVE - log dir auto-created
    step("6. NEGATIVE: parent directory of log_path auto-created")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Nest the log path 3 dirs deep, none of which exist
        deep_log = tmp_dir / "a" / "b" / "c" / "watcher.log"
        status_path = tmp_dir / "status.json"
        status_path.write_text(json.dumps({"failed_drills": [], "total_drills": 1}))
        hook.main(
            commit_sha="deep1",
            commit_message="feat: deep dir",
            files_touched=["scripts/x.py"],
            drill_status_path=status_path,
            log_path=deep_log,
            recent_files_per_commit=[],
        )
        if not deep_log.exists():
            fail(f"deep log path not created: {deep_log}")
        if not deep_log.parent.exists():
            fail(f"parent dir not auto-created: {deep_log.parent}")
        ok(f"parent dir auto-created at depth 3")

    # Step 7: NEGATIVE - CLI exits 0 always (advisory-only)
    step("7. NEGATIVE: CLI wrapper exits 0 even on internal errors")
    # Run the CLI with --print; it should exit 0 even when the
    # script tries to read git data from a non-git dir.
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "loop_watcher_hook.py"), "--print"],
        capture_output=True, text=True,
        cwd="/tmp",  # not a git repo - git commands will fail
    )
    if result.returncode != 0:
        fail(
            f"hook exited {result.returncode} from non-git dir; "
            f"advisory-only contract requires exit 0 always. "
            f"stderr: {result.stderr[:300]}"
        )
    ok(f"CLI exit code = 0 even from non-git dir (advisory contract held)")

    # Step 8: NEGATIVE - timestamp + sha format
    step("8. NEGATIVE: timestamp ISO-8601 + commit_sha truncated to 12 chars")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        status_path = tmp_dir / "status.json"
        status_path.write_text(json.dumps({"failed_drills": [], "total_drills": 1}))
        entry = hook.main(
            commit_sha="abcdef0123456789abcdef0123456789",  # 32 chars
            commit_message="feat: long sha",
            files_touched=["scripts/x.py"],
            drill_status_path=status_path,
            log_path=tmp_dir / "watcher.log",
            recent_files_per_commit=[],
        )
        # commit_sha should be truncated to 12 chars
        if len(entry["commit_sha"]) != 12:
            fail(f"commit_sha not truncated: {entry['commit_sha']!r} ({len(entry['commit_sha'])} chars)")
        if entry["commit_sha"] != "abcdef012345":
            fail(f"commit_sha truncation wrong: {entry['commit_sha']!r}")
        # timestamp should be ISO-8601 UTC
        ts = entry["timestamp"]
        if "T" not in ts or not (ts.endswith("Z") or "+00:00" in ts):
            fail(f"timestamp not ISO-8601 UTC: {ts!r}")
        ok(f"sha={entry['commit_sha']} timestamp={ts}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 LOOP-WATCHER-HOOK STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
