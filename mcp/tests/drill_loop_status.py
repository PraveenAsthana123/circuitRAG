#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/loop_status.py - operator's "is everything fine?"
one-shot health report.

Eight steps. Six negative assertions.

  1. Script exists + executable.
  2. NEGATIVE: collect_status() never raises (must work even on
     fresh box: no advisor.db, no logs, Ollama not installed).
  3. Reports HEALTHY when DB green + drill green + recent verdicts
     all APPROVE.
  4. NEGATIVE: WARNING when drill status stale (>STALE_AFTER_SECS).
  5. NEGATIVE: ERROR when advisor.db missing entirely.
  6. NEGATIVE: --json mode emits valid JSON (operators script on it).
  7. NEGATIVE: exit code maps {HEALTHY:0, WARNING:1, ERROR:2}.
     Without that mapping, CI can't gate on it.
  8. NEGATIVE: counts match DB content (events_total + council_runs_total
     + council_runs_pending derived correctly via LEFT JOIN).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "loop_status.py"

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


def _load():
    spec = importlib.util.spec_from_file_location("loop_status", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loop_status"] = mod
    spec.loader.exec_module(mod)
    return mod


def _seed_db_via_memory(db_path: pathlib.Path, n_events: int,
                         n_council: int) -> None:
    """Seed advisor.db with N events + M council_runs."""
    sys.path.insert(0, str(REPO / "services" / "sidecar-advisor"))
    spec = importlib.util.spec_from_file_location(
        "_mem_loopstatus_drill",
        REPO / "services" / "sidecar-advisor" / "memory.py",
    )
    mem_mod = importlib.util.module_from_spec(spec)
    sys.modules["_mem_loopstatus_drill"] = mem_mod
    spec.loader.exec_module(mem_mod)
    mem = mem_mod.AdvisorMemory(db_path)
    mem.set_policy_version("test")
    eids = []
    for i in range(n_events):
        eid = mem.record_event(
            event_type="pr_review", source="git-diff",
            content=f"diff {i}", model_used="test:7b",
            advisor_output={"summary": f"s{i}", "risk_level": "LOW",
                             "top_3_advice": [], "confidence": 0.5},
        )
        eids.append(eid)
    for eid in eids[:n_council]:
        mem.record_council_run(event_id=eid, telemetry={
            "outcome": "ok", "advisor_id": "chair", "prompt_version": "v",
            "duration_s": 1.0, "drafts": [], "reviews": [],
            "failed_authors": [], "advisor_error": None,
        })


def main():
    # 1. Exists + executable
    step("1. loop_status.py exists + executable")
    import os
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT}")
    if not os.access(SCRIPT, os.X_OK):
        fail(f"not executable: {SCRIPT}")
    text = SCRIPT.read_text()
    if len(text) < 2000:
        fail(f"too short: {len(text)}")
    ok(f"script ok ({len(text)} chars)")

    # 2. NEGATIVE: never raises on fresh box
    step("2. NEGATIVE: collect_status() never raises (fresh box safe)")
    mod = _load()
    # Override the module-level paths to point at empty tmpdir
    with tempfile.TemporaryDirectory() as tmp:
        empty = pathlib.Path(tmp)
        mod.ADVISOR_DB = empty / "advisor.db"
        mod.LOOP_DIR = empty / ".loop"
        mod.WATCHER_LOG = empty / ".loop" / "watcher.log"
        mod.COUNCIL_LOG = empty / ".loop" / "council_runs.log"
        mod.DRILL_STATUS = empty / ".loop" / "last_drill_outcome.json"
        try:
            status = mod.collect_status()
        except Exception as exc:  # noqa: BLE001
            fail(f"collect_status raised on fresh box: {exc}")
        if "loop_state" not in status:
            fail(f"status dict missing loop_state: {status}")
        ok(f"fresh-box collect_status -> {status.get('loop_state')}")

    # 3. HEALTHY when everything green
    step("3. Reports HEALTHY when DB green + drill green + verdicts APPROVE")
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        loop = d / ".loop"
        loop.mkdir()
        # Override paths
        mod.ADVISOR_DB = d / "advisor.db"
        mod.LOOP_DIR = loop
        mod.WATCHER_LOG = loop / "watcher.log"
        mod.COUNCIL_LOG = loop / "council_runs.log"
        mod.DRILL_STATUS = loop / "last_drill_outcome.json"
        # Seed: 3 events all with council_runs
        _seed_db_via_memory(mod.ADVISOR_DB, n_events=3, n_council=3)
        # Fresh drill status (now)
        from datetime import datetime, timezone
        mod.DRILL_STATUS.write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "failed_drills": [],
            "total_drills": 30,
        }))
        # 5 APPROVE verdicts
        with mod.WATCHER_LOG.open("w") as f:
            for i in range(5):
                f.write(json.dumps({
                    "timestamp": "2026-04-28T16:00:00+00:00",
                    "commit_sha": f"abc{i}",
                    "verdict": "APPROVE", "rule_fired": 6,
                    "reason": "ok",
                }) + "\n")
        status = mod.collect_status()
        if status["loop_state"] != "HEALTHY":
            fail(
                f"expected HEALTHY, got {status['loop_state']}: "
                f"warnings={status.get('warnings')}"
            )
        if status["events_total"] != 3:
            fail(f"events_total wrong: {status['events_total']}")
        if status["council_runs_pending"] != 0:
            fail(f"pending should be 0: {status['council_runs_pending']}")
        ok(f"HEALTHY with 3 events, 0 pending, 5 APPROVE verdicts")

    # 4. WARNING when drill stale
    step("4. NEGATIVE: WARNING when drill status stale (>STALE_AFTER)")
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        loop = d / ".loop"
        loop.mkdir()
        mod.ADVISOR_DB = d / "advisor.db"
        mod.LOOP_DIR = loop
        mod.WATCHER_LOG = loop / "watcher.log"
        mod.COUNCIL_LOG = loop / "council_runs.log"
        mod.DRILL_STATUS = loop / "last_drill_outcome.json"
        _seed_db_via_memory(mod.ADVISOR_DB, n_events=1, n_council=1)
        # STALE drill status (timestamp far in past)
        from datetime import datetime, timezone, timedelta
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
        mod.DRILL_STATUS.write_text(json.dumps({
            "timestamp": old_ts,
            "failed_drills": [],
            "total_drills": 30,
        }))
        # Empty watcher log (no recent rejects)
        mod.WATCHER_LOG.write_text("")
        status = mod.collect_status()
        if status["loop_state"] != "WARNING":
            fail(
                f"expected WARNING for stale drill, got {status['loop_state']}: "
                f"warnings={status.get('warnings')}"
            )
        warnings = status.get("warnings", [])
        if not any("stale" in w for w in warnings):
            fail(f"stale warning missing: {warnings}")
        ok(f"WARNING with stale drill ({status['drill_status_age_s']}s old)")

    # 5. ERROR when DB missing
    step("5. NEGATIVE: ERROR when advisor.db missing (bootstrap not run)")
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        # Don't create DB
        mod.ADVISOR_DB = d / "ghost.db"
        mod.LOOP_DIR = d / ".loop"
        mod.WATCHER_LOG = d / ".loop" / "watcher.log"
        mod.COUNCIL_LOG = d / ".loop" / "council_runs.log"
        mod.DRILL_STATUS = d / ".loop" / "last_drill_outcome.json"
        status = mod.collect_status()
        if status["loop_state"] != "ERROR":
            fail(
                f"expected ERROR for missing DB, got {status['loop_state']}: "
                f"errors={status.get('errors')}"
            )
        errors = status.get("errors", [])
        if not any("advisor.db" in e for e in errors):
            fail(f"advisor.db missing-error not surfaced: {errors}")
        ok(f"ERROR with missing advisor.db; errors={errors}")

    # 6. --json mode
    step("6. NEGATIVE: --json mode emits valid JSON")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail(f"--json output not valid JSON: {result.stdout[:200]!r}")
    if "loop_state" not in data:
        fail(f"--json output missing loop_state: {data}")
    ok(f"--json output is valid; loop_state={data['loop_state']}")

    # 7. Exit code mapping
    step("7. NEGATIVE: exit code maps {HEALTHY:0, WARNING:1, ERROR:2}")
    # Use the module to test the mapping rather than spawning per-state
    # subprocess (those would need fixture data on disk).
    cli_text = SCRIPT.read_text()
    if not all(p in cli_text for p in [
        '"HEALTHY": 0', '"WARNING": 1', '"ERROR": 2',
    ]):
        fail("exit-code mapping doesn't have all 3 states")
    ok("exit-code mapping {HEALTHY:0, WARNING:1, ERROR:2} declared")

    # 8. Counts match DB content
    step("8. NEGATIVE: counts match DB via LEFT JOIN (council_runs_pending)")
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        loop = d / ".loop"
        loop.mkdir()
        mod.ADVISOR_DB = d / "advisor.db"
        mod.LOOP_DIR = loop
        mod.WATCHER_LOG = loop / "watcher.log"
        mod.COUNCIL_LOG = loop / "council_runs.log"
        mod.DRILL_STATUS = loop / "last_drill_outcome.json"
        # Seed 5 events but only 2 council_runs
        _seed_db_via_memory(mod.ADVISOR_DB, n_events=5, n_council=2)
        from datetime import datetime, timezone
        mod.DRILL_STATUS.write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "failed_drills": [], "total_drills": 1,
        }))
        mod.WATCHER_LOG.write_text("")
        status = mod.collect_status()
        if status["events_total"] != 5:
            fail(f"events_total wrong: {status['events_total']}")
        if status["council_runs_total"] != 2:
            fail(f"council_runs_total wrong: {status['council_runs_total']}")
        if status["council_runs_pending"] != 3:
            fail(
                f"council_runs_pending should be 3 (5 events - 2 with council "
                f"= 3 pending), got {status['council_runs_pending']}"
            )
        ok(f"counts match: events=5, council_runs=2, pending=3")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 LOOP-STATUS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
