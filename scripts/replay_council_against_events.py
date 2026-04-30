#!/usr/bin/env python3
"""Batched replay of the Sidecar council against events captured
without a council_run row.

Use cases:
  * Phase 2A2 --no-council bootstrap commits: caught the diff but
    skipped the LLM call. Replay overnight.
  * Phase 2A2 chair-error fallback: event landed but council_run
    didn't. Retry to fill the gap.
  * Bulk imports of historical commits.

Operator usage:

  # See what would be replayed (no LLM calls; just lists):
  python3 scripts/replay_council_against_events.py
  python3 scripts/replay_council_against_events.py --limit 200

  # Actually fire the council:
  python3 scripts/replay_council_against_events.py --apply
  python3 scripts/replay_council_against_events.py --apply --max-concurrent 8

Schedule for production (overnight backlog drain):
  cron: 0 5 * * *   # daily 05:00 UTC
  command: python3 scripts/replay_council_against_events.py --apply --limit 200
  redirect to: .loop/replay_council.log

Idempotent: events that already have an advisor_council_runs row
are filtered out by find_events_without_council_run, so re-running
is a no-op once the backlog is drained.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import sys
from datetime import UTC
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO / "advisor.db"
DEFAULT_LOG = REPO / ".loop" / "replay_council.log"

log = logging.getLogger("replay_council_against_events")


def _load_mod(rel: str, name: str):
    p = REPO / rel
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--log-path", default=str(DEFAULT_LOG))
    parser.add_argument("--limit", type=int, default=50,
                        help="max events per batch (default 50)")
    parser.add_argument("--max-concurrent", type=int, default=4,
                        help="DispatchPool max_parallel (default 4)")
    parser.add_argument("--apply", action="store_true",
                        help="actually fire council (default: dry-run / list only)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[replay_council] db not found at {db_path}; nothing to do.",
              file=sys.stderr)
        return 0

    # Load memory + advisor + replay module via the same package-context
    # trick the drills use, so relative imports inside the sidecar
    # package resolve.
    import types
    pkg = types.ModuleType("sidecar_advisor_pkg")
    pkg.__path__ = [str(REPO / "services" / "sidecar-advisor")]
    sys.modules["sidecar_advisor_pkg"] = pkg

    mem_mod = _load_mod("services/sidecar-advisor/memory.py",
                         "sidecar_advisor_pkg.memory")
    sys.modules["sidecar_advisor_pkg.memory"] = mem_mod
    adv_mod = _load_mod("services/sidecar-advisor/advisor.py",
                         "sidecar_advisor_pkg.advisor")
    sys.modules["sidecar_advisor_pkg.advisor"] = adv_mod
    council_mod = _load_mod("services/sidecar-advisor/council.py",
                             "sidecar_advisor_pkg.council")
    sys.modules["sidecar_advisor_pkg.council"] = council_mod
    replay_mod = _load_mod("services/sidecar-advisor/replay_council.py",
                            "sidecar_advisor_pkg.replay_council")

    import yaml
    policy = yaml.safe_load(
        (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
    )

    memory = mem_mod.AdvisorMemory(db_path)
    pending = memory.find_events_without_council_run(limit=args.limit)

    if not pending:
        print("[replay_council] backlog is empty; nothing to replay.",
              file=sys.stderr)
        return 0

    if not args.apply:
        # Dry-run report
        print(json.dumps({
            "pending": len(pending),
            "first_5_event_ids": [e["id"] for e in pending[:5]],
            "oldest_created_at": pending[0]["created_at"],
            "limit": args.limit,
        }, indent=2))
        print(
            f"[replay_council] DRY RUN: {len(pending)} events would be "
            f"replayed (oldest from {pending[0]['created_at']}); "
            f"re-run with --apply to fire the council.",
            file=sys.stderr,
        )
        return 0

    # --apply path: real council
    advisor = adv_mod.Advisor(policy)
    results, stats = asyncio.run(replay_mod.replay_council_for_events(
        events=pending, advisor=advisor, memory=memory,
        max_concurrent=args.max_concurrent,
    ))

    # Append a summary log line
    log_path = Path(args.log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    entry = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "submitted": stats.submitted,
        "succeeded": stats.succeeded,
        "failed": stats.failed,
        "duration_s": stats.duration_s,
        "risk_counts": stats.risk_counts,
        "failed_event_ids": stats.failed_event_ids,
    }
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    print(json.dumps(entry, indent=2))
    print(
        f"[replay_council] {stats.succeeded}/{stats.submitted} reviewed; "
        f"{stats.failed} failed; "
        f"risk: {stats.risk_counts}; "
        f"duration: {stats.duration_s:.1f}s",
        file=sys.stderr,
    )
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(cli())
