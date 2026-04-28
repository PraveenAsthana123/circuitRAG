#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: AdvisorMemory.prune_council_runs() retention policy.

The advisor_council_runs table grows unbounded without a purge.
This drill verifies the prune correctly partitions old vs new
rows AND defaults to dry-run safety.

Eight steps. Six negative assertions.

  1. Insert 2 old + 2 new rows; prune older_than_days=30,
     dry_run=False -> exactly 2 deleted, 2 kept.
  2. NEGATIVE: dry_run=True (default) does NOT delete; would_delete
     reports the count without mutating.
  3. NEGATIVE: empty advisor_council_runs table -> no-op result
     (deleted=0, kept=0); no error.
  4. NEGATIVE: re-run after apply is idempotent (already-pruned
     table stays clean, no double-counts).
  5. NEGATIVE: rows with FUTURE timestamps preserved (clock-skew
     safety - threshold is "older than", future > threshold).
  6. NEGATIVE: older_than_days=0 prunes everything older than
     "now" (instant cutoff); rows from "right now" stay.
  7. NEGATIVE: older_than_days < 0 raises ValueError (sanity).
  8. NEGATIVE: prune does NOT touch advisor_events rows (companion
     audit trail preserved).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

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


def _load_memory():
    p = REPO / "services" / "sidecar-advisor" / "memory.py"
    spec = importlib.util.spec_from_file_location("memory_for_prune", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["memory_for_prune"] = mod
    spec.loader.exec_module(mod)
    return mod


memory_mod = _load_memory()
AdvisorMemory = memory_mod.AdvisorMemory


def _seed_event(mem, content="x"):
    """Insert a minimal event row (so we have an event_id to FK)."""
    return mem.record_event(
        event_type="pr_review", source="manual",
        content=content, model_used=None, advisor_output=None,
    )


def _insert_council_run_at(db_path: pathlib.Path, *,
                           created_at: str, event_id: int | None = None):
    """Bypass record_council_run() so we can backdate the timestamp.
    record_council_run uses _utcnow_iso() which is always 'now' -
    the drill needs synthetic historical rows."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO advisor_council_runs (
                event_id, created_at, outcome, advisor_id,
                prompt_version, duration_s, advisor_error,
                failed_authors, drafts_json, reviews_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, created_at, "ok", "chair_test",
                "v_test", 1.0, None,
                "[]", "[]", "[]",
            ),
        )


def main():
    # Step 1: prune deletes old, keeps new
    step("1. 2 old + 2 new rows; older_than_days=30, apply -> 2 deleted")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")

        now = datetime.now(timezone.utc)
        # 2 old (60 days ago), 2 new (5 days ago)
        for i in range(2):
            _insert_council_run_at(
                db, created_at=(now - timedelta(days=60+i)).isoformat(timespec="seconds"),
            )
        for i in range(2):
            _insert_council_run_at(
                db, created_at=(now - timedelta(days=5+i)).isoformat(timespec="seconds"),
            )
        result = mem.prune_council_runs(
            older_than_days=30, dry_run=False,
        )
        if result["deleted"] != 2:
            fail(f"expected 2 deleted, got {result['deleted']}")
        if result["kept"] != 2:
            fail(f"expected 2 kept, got {result['kept']}")
        if result["dry_run"]:
            fail(f"apply mode should report dry_run=False")
        # Verify on disk
        with sqlite3.connect(str(db)) as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM advisor_council_runs"
            ).fetchone()[0]
        if n != 2:
            fail(f"DB has {n} rows after prune; expected 2")
        ok(f"deleted=2 kept=2; DB rowcount={n}")

    # Step 2: dry_run=True doesn't mutate
    step("2. NEGATIVE: dry_run=True (default) reports without deleting")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        now = datetime.now(timezone.utc)
        for i in range(3):
            _insert_council_run_at(
                db, created_at=(now - timedelta(days=100+i)).isoformat(timespec="seconds"),
            )
        result = mem.prune_council_runs(older_than_days=30)  # default dry_run=True
        if result["would_delete"] != 3:
            fail(f"would_delete should be 3, got {result['would_delete']}")
        if result["deleted"] != 0:
            fail(f"dry_run should report deleted=0, got {result['deleted']}")
        # Verify nothing actually deleted
        with sqlite3.connect(str(db)) as conn:
            n = conn.execute("SELECT COUNT(*) FROM advisor_council_runs").fetchone()[0]
        if n != 3:
            fail(f"dry_run mutated DB: {n} rows remain (expected 3)")
        ok(f"would_delete=3 reported; DB unchanged ({n} rows)")

    # Step 3: empty table no-op
    step("3. NEGATIVE: empty advisor_council_runs -> no-op, no error")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)  # init schema, no inserts
        result = mem.prune_council_runs(older_than_days=30, dry_run=False)
        if result["deleted"] != 0 or result["kept"] != 0:
            fail(f"empty table should yield 0/0, got {result}")
        ok(f"empty table: deleted=0 kept=0 (graceful)")

    # Step 4: idempotent re-run
    step("4. NEGATIVE: re-run after apply is idempotent")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        now = datetime.now(timezone.utc)
        for i in range(2):
            _insert_council_run_at(
                db, created_at=(now - timedelta(days=100+i)).isoformat(timespec="seconds"),
            )
        for i in range(2):
            _insert_council_run_at(
                db, created_at=(now - timedelta(days=5+i)).isoformat(timespec="seconds"),
            )
        # First apply
        r1 = mem.prune_council_runs(older_than_days=30, dry_run=False)
        if r1["deleted"] != 2:
            fail(f"first run deleted != 2: {r1}")
        # Re-run; should now have nothing to delete
        r2 = mem.prune_council_runs(older_than_days=30, dry_run=False)
        if r2["deleted"] != 0:
            fail(f"re-run should be no-op: {r2}")
        if r2["kept"] != 2:
            fail(f"re-run kept != 2: {r2}")
        ok(f"re-run: deleted=0 kept=2 (idempotent)")

    # Step 5: future timestamps preserved
    step("5. NEGATIVE: future-timestamped rows preserved (clock-skew safety)")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        now = datetime.now(timezone.utc)
        # Future timestamp (e.g. NTP skew on a node)
        _insert_council_run_at(
            db, created_at=(now + timedelta(days=5)).isoformat(timespec="seconds"),
        )
        # Old timestamp
        _insert_council_run_at(
            db, created_at=(now - timedelta(days=100)).isoformat(timespec="seconds"),
        )
        result = mem.prune_council_runs(older_than_days=30, dry_run=False)
        if result["deleted"] != 1:
            fail(f"should delete only the old one: {result}")
        if result["kept"] != 1:
            fail(f"future row should be kept: {result}")
        ok(f"future timestamp preserved (clock-skew safe)")

    # Step 6: older_than_days=0 cutoff at "now"
    step("6. NEGATIVE: older_than_days=0 prunes anything before now")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        now = datetime.now(timezone.utc)
        # 1 second ago - should be < threshold
        _insert_council_run_at(
            db, created_at=(now - timedelta(seconds=1)).isoformat(timespec="seconds"),
        )
        # Future - should be kept
        _insert_council_run_at(
            db, created_at=(now + timedelta(seconds=10)).isoformat(timespec="seconds"),
        )
        result = mem.prune_council_runs(older_than_days=0, dry_run=False)
        if result["deleted"] != 1:
            fail(f"older_than_days=0: should delete 1, got {result}")
        if result["kept"] != 1:
            fail(f"future-timestamp row kept: expected 1, got {result['kept']}")
        ok(f"older_than_days=0: instant cutoff at now")

    # Step 7: negative days raises
    step("7. NEGATIVE: older_than_days < 0 raises ValueError (sanity)")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        try:
            mem.prune_council_runs(older_than_days=-1, dry_run=True)
            fail("negative days should raise ValueError")
        except ValueError:
            pass
        ok(f"negative days rejected at parameter validation")

    # Step 8: events untouched
    step("8. NEGATIVE: prune does NOT touch advisor_events rows")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        # Seed 3 events (these can't have backdated timestamps via the
        # API; but they're fresh, NOT eligible for prune by date anyway.
        # The point is the prune shouldn't delete them regardless).
        for i in range(3):
            _seed_event(mem, content=f"content_{i}")
        # Insert 3 council runs - 2 old, 1 new
        now = datetime.now(timezone.utc)
        for i in range(2):
            _insert_council_run_at(
                db, created_at=(now - timedelta(days=100+i)).isoformat(timespec="seconds"),
            )
        _insert_council_run_at(
            db, created_at=(now - timedelta(days=5)).isoformat(timespec="seconds"),
        )
        # Prune
        result = mem.prune_council_runs(older_than_days=30, dry_run=False)
        if result["deleted"] != 2:
            fail(f"should prune 2 council_runs: {result}")
        # Events still there
        events = mem.recent_events(limit=10)
        if len(events) != 3:
            fail(f"events touched by prune: {len(events)} (expected 3)")
        # Council_runs has 1
        with sqlite3.connect(str(db)) as conn:
            n = conn.execute("SELECT COUNT(*) FROM advisor_council_runs").fetchone()[0]
        if n != 1:
            fail(f"council_runs final count != 1: {n}")
        ok(f"prune deleted 2 council_runs; 3 events + 1 council_run preserved")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 PRUNE-COUNCIL-RUNS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
