#!/usr/bin/env python3
"""Prune old advisor_council_runs rows for storage discipline.

The advisor_council_runs table (Phase 2E) carries 10-50 KB JSON
columns per row (drafts_json, reviews_json). At 1 commit/min over
months of autonomous operation, the table grows unboundedly.

Operator usage:

  # See what would be pruned (default, safe to re-run):
  python3 scripts/prune_council_runs.py
  python3 scripts/prune_council_runs.py --older-than-days 60

  # Actually prune:
  python3 scripts/prune_council_runs.py --apply
  python3 scripts/prune_council_runs.py --older-than-days 30 --apply

Defaults:
  older_than_days = 90  (3 months retention)
  --apply         not set  (dry-run; safe re-run)

Companion advisor_events rows are NOT pruned by this script -
they're small (KB each) and preserve the "we reviewed X commits at
time Y" audit trail. A separate prune for events is Phase 2F+ if
event-table size becomes a concern.

Schedule for production:
  cron: 0 4 * * 0  # Sundays 04:00 UTC
  command: python3 scripts/prune_council_runs.py --apply
  redirect to: .loop/prune.log
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO / "advisor.db"

log = logging.getLogger("prune_council_runs")


def _load_memory():
    p = REPO / "services" / "sidecar-advisor" / "memory.py"
    spec = importlib.util.spec_from_file_location("_memory_for_prune", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_memory_for_prune"] = mod
    spec.loader.exec_module(mod)
    return mod


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default=str(DEFAULT_DB),
        help="path to advisor.db (default ./advisor.db)",
    )
    parser.add_argument(
        "--older-than-days", type=int, default=90,
        help="rows with created_at older than this are pruned (default 90)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually delete rows (default: dry-run report only)",
    )
    parser.add_argument(
        "--vacuum", action="store_true",
        help="run VACUUM after the prune to reclaim disk (only with --apply)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db_path = Path(args.db)
    if not db_path.exists():
        print(
            f"[prune_council_runs] db not found at {db_path}; nothing to do.",
            file=sys.stderr,
        )
        return 0

    mem_mod = _load_memory()
    AdvisorMemory = mem_mod.AdvisorMemory
    memory = AdvisorMemory(db_path)

    result = memory.prune_council_runs(
        older_than_days=args.older_than_days,
        dry_run=(not args.apply),
    )

    # Optional VACUUM to reclaim disk after delete (apply-mode only)
    if args.apply and args.vacuum and result["deleted"] > 0:
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            # VACUUM cannot be inside a transaction; sqlite3's default
            # isolation_level=None autocommit mode handles this fine
            # since AdvisorMemory uses isolation_level=None too.
            conn.isolation_level = None
            conn.execute("VACUUM")

    print(json.dumps(result, indent=2))

    if args.apply:
        print(
            f"[prune_council_runs] deleted {result['deleted']} rows; "
            f"kept {result['kept']}; threshold={result['threshold_iso']}",
            file=sys.stderr,
        )
        if args.vacuum and result["deleted"] > 0:
            print("[prune_council_runs] VACUUM complete", file=sys.stderr)
    else:
        print(
            f"[prune_council_runs] DRY RUN: would delete "
            f"{result['would_delete']} rows; would keep {result['kept']}; "
            f"threshold={result['threshold_iso']}; "
            f"re-run with --apply to execute",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
