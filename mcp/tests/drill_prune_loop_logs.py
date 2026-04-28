#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/prune_loop_logs.py — JSONL retention pruner (Phase 6E).

Phase 2F shipped a SQLite-table pruner; Phase 6E ships the JSONL-
file equivalent for `.loop/watcher.log` + `.loop/council_runs.log`.
Both grow unbounded in long-running deployments. The pruner drops
entries older than N days while preserving append-only safety
(atomic tmp + rename) and data-preservation discipline (don't lose
malformed rows we can't classify).

This drill exercises the pruner against synthetic temp files only —
NEVER touches the real `.loop/*.log`. Safe to re-run any time.

Eight steps. Six negative assertions.

  1. POSITIVE: dry-run on real-data shape — keep/drop counts
     correctly classify entries by timestamp.
  2. NEGATIVE: --apply REWRITES the file with kept-only lines;
     dropped entries are gone after the call.
  3. NEGATIVE: dry-run NEVER mutates the file. Re-running --dry-run
     a thousand times produces no change to the file or its mtime.
  4. NEGATIVE: atomic write contract — after --apply, no leftover
     .tmp file remains in the directory. Same contract as 5U's
     write_prometheus_atomic.
  5. NEGATIVE: bad timestamp → entry KEPT (data preservation).
     A row with `timestamp` = "not-a-date" stays in the file
     regardless of cutoff. Operator handles manually.
  6. NEGATIVE: malformed JSON line → KEPT. Same principle:
     don't drop what we can't classify.
  7. NEGATIVE: --older-than-days 0 or negative is rejected at CLI
     (typo-safe; otherwise would drop everything immediately).
  8. NEGATIVE: missing log file is treated as no-op (cron-safe);
     no exception, status is "no-op (file does not exist)".

Run: python3 mcp/tests/drill_prune_loop_logs.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "prune_loop_logs.py"


def _load_pruner():
    spec = importlib.util.spec_from_file_location("_pruner_drill_6E", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pruner_drill_6E"] = mod
    spec.loader.exec_module(mod)
    return mod


def _ts(offset_days: int) -> str:
    """ISO timestamp `offset_days` from now (negative = past)."""
    t = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return t.isoformat(timespec="seconds")


def _entry(timestamp: str, **rest) -> str:
    """Build one JSONL line with the given timestamp + extra fields."""
    return json.dumps({"timestamp": timestamp, **rest})


def main() -> int:
    pruner = _load_pruner()

    # ── Step 1: POSITIVE — dry-run keep/drop counts correct ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "test.log"
        lines = [
            _entry(_ts(-100), commit="a"),  # 100 days ago — drop
            _entry(_ts(-95), commit="b"),   # 95 days ago — drop
            _entry(_ts(-30), commit="c"),   # 30 days ago — keep
            _entry(_ts(0), commit="d"),     # now — keep
        ]
        log_path.write_text("\n".join(lines) + "\n")
        report = pruner.prune_log(log_path, older_than_days=90, apply=False)
        if report["dropped"] != 2 or report["kept"] != 2:
            print(f"✗ step 1: classify wrong: {report}")
            return 1
        if report["status"] != "dry-run (would drop)":
            print(f"✗ step 1: dry-run status wrong: {report['status']}")
            return 1
        print(f"✓ step 1: dry-run classification — kept={report['kept']}, "
              f"dropped={report['dropped']}")

    # ── Step 2: NEGATIVE — --apply rewrites file ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "test.log"
        lines = [
            _entry(_ts(-100), commit="old1"),
            _entry(_ts(-95), commit="old2"),
            _entry(_ts(-30), commit="recent"),
        ]
        log_path.write_text("\n".join(lines) + "\n")
        report = pruner.prune_log(log_path, older_than_days=90, apply=True)
        if report["status"] != "pruned":
            print(f"✗ step 2: apply status wrong: {report['status']}")
            return 1
        # File should now have only the recent entry
        new_content = log_path.read_text()
        if "old1" in new_content or "old2" in new_content:
            print(f"✗ step 2: --apply didn't drop old entries: {new_content!r}")
            return 1
        if "recent" not in new_content:
            print(f"✗ step 2: --apply dropped the recent entry: {new_content!r}")
            return 1
        # File should have exactly 1 non-empty line
        kept_lines = [ln for ln in new_content.splitlines() if ln.strip()]
        if len(kept_lines) != 1:
            print(f"✗ step 2: expected 1 kept line, got {len(kept_lines)}")
            return 1
        print("✓ step 2: --apply rewrote file with kept-only lines")

    # ── Step 3: NEGATIVE — dry-run never mutates ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "test.log"
        original = "\n".join([
            _entry(_ts(-100), commit="a"),
            _entry(_ts(-30), commit="b"),
        ]) + "\n"
        log_path.write_text(original)
        original_mtime = log_path.stat().st_mtime
        # Run dry-run multiple times
        for _ in range(3):
            pruner.prune_log(log_path, older_than_days=90, apply=False)
        if log_path.read_text() != original:
            print("✗ step 3: dry-run mutated file content")
            return 1
        if log_path.stat().st_mtime != original_mtime:
            print("✗ step 3: dry-run touched file mtime")
            return 1
        print("✓ step 3: dry-run × 3 → file content + mtime unchanged")

    # ── Step 4: NEGATIVE — no leftover .tmp file after --apply ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "test.log"
        log_path.write_text(
            _entry(_ts(-100)) + "\n" + _entry(_ts(-30)) + "\n"
        )
        pruner.prune_log(log_path, older_than_days=90, apply=True)
        tmp_files = list(tmpdir.glob("*.tmp"))
        if tmp_files:
            print(f"✗ step 4: leftover .tmp files: {tmp_files}")
            return 1
        print("✓ step 4: atomic write — no .tmp file leak")

    # ── Step 5: NEGATIVE — bad timestamp → KEPT ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "test.log"
        log_path.write_text("\n".join([
            _entry("not-a-real-timestamp", commit="bad-ts"),
            _entry(_ts(-100), commit="old"),
            _entry("", commit="empty-ts"),
        ]) + "\n")
        report = pruner.prune_log(log_path, older_than_days=90, apply=True)
        new_content = log_path.read_text()
        if "bad-ts" not in new_content:
            print("✗ step 5: bad-timestamp entry was dropped (data lost)")
            return 1
        if "empty-ts" not in new_content:
            print("✗ step 5: empty-timestamp entry was dropped")
            return 1
        if "old" in new_content:
            print("✗ step 5: actually-old entry survived (cutoff broken)")
            return 1
        print("✓ step 5: bad/empty timestamps preserved; only valid-old dropped")

    # ── Step 6: NEGATIVE — malformed JSON line → KEPT ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "test.log"
        log_path.write_text(
            _entry(_ts(0), commit="recent") + "\n"
            + "{this is not json — write crashed mid-line\n"
            + _entry(_ts(-100), commit="old") + "\n"
        )
        pruner.prune_log(log_path, older_than_days=90, apply=True)
        new_content = log_path.read_text()
        if "this is not json" not in new_content:
            print("✗ step 6: malformed JSON line was dropped (data lost)")
            return 1
        if "old" in new_content:
            print("✗ step 6: actually-old entry survived")
            return 1
        if "recent" not in new_content:
            print("✗ step 6: recent entry was dropped")
            return 1
        print("✓ step 6: malformed JSON line preserved; cutoff still applied to valid")

    # ── Step 7: NEGATIVE — --older-than-days 0 / negative rejected ──
    rc = subprocess.call(
        [sys.executable, str(SCRIPT), "--older-than-days", "0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(REPO),
    )
    if rc == 0:
        print("✗ step 7: --older-than-days 0 accepted; should fail")
        return 1
    rc = subprocess.call(
        [sys.executable, str(SCRIPT), "--older-than-days", "-5"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(REPO),
    )
    if rc == 0:
        print("✗ step 7: --older-than-days -5 accepted; should fail")
        return 1
    print("✓ step 7: --older-than-days ≤ 0 rejected (typo-safe)")

    # ── Step 8: NEGATIVE — missing log file is no-op ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        missing = tmpdir / "does-not-exist.log"
        try:
            report = pruner.prune_log(missing, older_than_days=90, apply=True)
        except Exception as exc:
            print(f"✗ step 8: missing file raised {type(exc).__name__}: {exc}")
            return 1
        if report["status"] != "no-op (file does not exist)":
            print(f"✗ step 8: missing file status wrong: {report['status']}")
            return 1
        if report["kept"] != 0 or report["dropped"] != 0:
            print(f"✗ step 8: missing file counts non-zero: {report}")
            return 1
        # And no file should have been created
        if missing.exists():
            print("✗ step 8: missing file path was CREATED on prune")
            return 1
        print("✓ step 8: missing log → no-op, no exception, no creation")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
