#!/usr/bin/env python3
"""Run the 3-model council on every medium-difficulty issue in the checklist.

Sequential (each council takes ~225s; 6 issues ≈ 22 minutes).
Reads .loop/issue_checklist.jsonl; calls scripts/issue_dispatcher.py
--council --id <id> per medium issue. Skips duplicates by tracking
seen ids. Writes a summary to .loop/council_batch_summary.json.

Usage:
    python3 scripts/run_council_batch.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKLIST = REPO / ".loop" / "issue_checklist.jsonl"
SUMMARY = REPO / ".loop" / "council_batch_summary.json"


def main() -> int:
    if not CHECKLIST.exists():
        print(f"missing {CHECKLIST.relative_to(REPO)}; run issue_scanner.py first")
        return 2

    issues = [json.loads(line) for line in CHECKLIST.read_text().splitlines() if line.strip()]
    medium = [i for i in issues if i["difficulty"] == "medium"]
    seen_ids = set()
    runs = []

    for issue in medium:
        if issue["id"] in seen_ids:
            print(f"\n--- SKIP duplicate id: {issue['id']} ---")
            continue
        seen_ids.add(issue["id"])
        print(f"\n========== {issue['id']} ==========")
        started = time.time()
        proc = subprocess.run(
            [sys.executable, "scripts/issue_dispatcher.py", "--council", "--id", issue["id"]],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=600,
        )
        elapsed = time.time() - started
        runs.append({
            "id": issue["id"],
            "code": issue["code"],
            "file": issue["file"],
            "elapsed_s": round(elapsed, 1),
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
        })
        # Per-issue tail to operator
        print(proc.stdout[-1500:])

    summary = {
        "total_medium": len(medium),
        "unique_ids_run": len(seen_ids),
        "runs": runs,
        "total_elapsed_s": sum(r["elapsed_s"] for r in runs),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"\n\n=== BATCH SUMMARY ===")
    print(f"Total: {summary['unique_ids_run']} unique medium issues")
    print(f"Elapsed: {summary['total_elapsed_s']:.0f}s ({summary['total_elapsed_s']/60:.1f} min)")
    print(f"Summary written to {SUMMARY.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
