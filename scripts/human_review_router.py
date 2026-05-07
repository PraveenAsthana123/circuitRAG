#!/usr/bin/env python3
"""Human-review router — routes retry-storm ids out of the council loop.

Per CLAUDE.md §44 (autonomous-loop ONE-thing-per-iter; iter-58's
reflection engine identified retry-storm ids; iter-59 acts on that
finding by routing them out of the council retry loop), §50.5.3
(security rules NEVER to model; high-failure rules go to human-review),
§55.3 (outcome-based contract: apply_rate must trend up; ids that keep
failing council are dragging the metric down), §47 (architecture: a
separate router because retry-storm detection is a council-runtime
concern that should NOT live inside the reflection engine — read-only
analyzer stays pure).

CONTRACT
  route_retry_storms(audit_path, queue_path, threshold) -> RouterReport

  RouterReport contains:
    - generated_at: UTC timestamp
    - storm_ids_detected: list[str] — ids meeting the threshold
    - newly_routed: list[str] — first time appearing in queue
    - already_routed: list[str] — already in queue (idempotent skip)
    - queue_size_before / queue_size_after: int
    - dry_run: bool
    - honesty_signal: one-line summary

Mutates .loop/human_review_queue.jsonl by APPENDING new entries (never
deletes; never modifies prior entries — append-only audit per §38).

Each queue entry shape (one JSON per line):
  {
    "id": "<issue-id>",
    "routed_at": "<iso-utc>",
    "reason": "retry_storm",
    "attempt_count": <int>,
    "lanes_attempted": [<lane>, ...],
    "first_seen": "<iso-utc>",
    "last_attempt": "<iso-utc>",
    "router_version": "v1"
  }

Run from CLI:
  python3 scripts/human_review_router.py --threshold 5
  python3 scripts/human_review_router.py --threshold 5 --dry-run
  python3 scripts/human_review_router.py --threshold 5 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOOP_DIR = REPO / ".loop"
DEFAULT_AUDIT = LOOP_DIR / "issue_audit.jsonl"
DEFAULT_QUEUE = LOOP_DIR / "human_review_queue.jsonl"

ROUTER_VERSION = "v1"


@dataclass(frozen=True)
class RouterReport:
    generated_at: str
    storm_ids_detected: list[str] = field(default_factory=list)
    newly_routed: list[str] = field(default_factory=list)
    already_routed: list[str] = field(default_factory=list)
    queue_size_before: int = 0
    queue_size_after: int = 0
    dry_run: bool = False
    honesty_signal: str = ""


def _read_jsonl(path: Path, limit: int = 50000) -> list[dict]:
    """Read JSONL, tolerating malformed lines."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _detect_storms(
    audit_rows: list[dict], threshold: int
) -> dict[str, dict]:
    """Aggregate by id; return only ids at or above the threshold.

    Returns: {id → {count, lanes_attempted, first_seen, last_attempt}}
    """
    stats: dict[str, dict] = defaultdict(
        lambda: {
            "count": 0,
            "lanes_attempted": set(),
            "first_seen": None,
            "last_attempt": None,
        }
    )
    for row in audit_rows:
        rid = row.get("id") or row.get("issue_id") or ""
        if not rid:
            continue
        ts = row.get("ts") or ""
        lane = row.get("lane") or "?"
        stats[rid]["count"] += 1
        stats[rid]["lanes_attempted"].add(lane)
        if stats[rid]["first_seen"] is None or ts < stats[rid]["first_seen"]:
            stats[rid]["first_seen"] = ts
        if stats[rid]["last_attempt"] is None or ts > stats[rid]["last_attempt"]:
            stats[rid]["last_attempt"] = ts
    # Filter to threshold + materialize sets to lists
    return {
        rid: {
            "count": s["count"],
            "lanes_attempted": sorted(s["lanes_attempted"]),
            "first_seen": s["first_seen"] or "",
            "last_attempt": s["last_attempt"] or "",
        }
        for rid, s in stats.items()
        if s["count"] >= threshold
    }


def route_retry_storms(
    *,
    audit_path: Path = DEFAULT_AUDIT,
    queue_path: Path = DEFAULT_QUEUE,
    threshold: int = 5,
    dry_run: bool = False,
) -> RouterReport:
    """Route retry-storm ids to the human-review queue.

    Idempotent: ids already in the queue are NOT re-added (append-only;
    deduped on read by id). The queue is the audit surface; an id appears
    exactly once after first detection.
    """
    audit_rows = _read_jsonl(audit_path)
    storms = _detect_storms(audit_rows, threshold)

    # Read existing queue → dedup set of already-routed ids
    existing_rows = _read_jsonl(queue_path)
    already_in_queue = {r.get("id") for r in existing_rows if r.get("id")}
    queue_size_before = len(existing_rows)

    newly_routed: list[str] = []
    already_routed: list[str] = []
    new_entries: list[dict] = []
    now = datetime.now(UTC).isoformat()

    for rid, info in sorted(storms.items()):
        if rid in already_in_queue:
            already_routed.append(rid)
            continue
        newly_routed.append(rid)
        new_entries.append({
            "id": rid,
            "routed_at": now,
            "reason": "retry_storm",
            "attempt_count": info["count"],
            "lanes_attempted": info["lanes_attempted"],
            "first_seen": info["first_seen"],
            "last_attempt": info["last_attempt"],
            "router_version": ROUTER_VERSION,
        })

    # Mutation step (skipped on dry_run)
    queue_size_after = queue_size_before
    if not dry_run and new_entries:
        # Ensure parent dir exists
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        # Append-only: never rewrite existing entries
        with queue_path.open("a", encoding="utf-8") as f:
            for entry in new_entries:
                f.write(json.dumps(entry) + "\n")
        queue_size_after = queue_size_before + len(new_entries)

    honesty = (
        f"detected {len(storms)} storm(s); "
        f"routed {len(newly_routed)} new "
        f"(skipped {len(already_routed)} already in queue)"
        + (" — DRY RUN" if dry_run else "")
    )

    return RouterReport(
        generated_at=now,
        storm_ids_detected=sorted(storms.keys()),
        newly_routed=sorted(newly_routed),
        already_routed=sorted(already_routed),
        queue_size_before=queue_size_before,
        queue_size_after=queue_size_after,
        dry_run=dry_run,
        honesty_signal=honesty,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold", type=int, default=5,
        help="Attempts threshold for storm detection (default: 5)",
    )
    parser.add_argument(
        "--audit", type=Path, default=DEFAULT_AUDIT,
        help=f"Audit JSONL path (default: {DEFAULT_AUDIT.relative_to(REPO)})",
    )
    parser.add_argument(
        "--queue", type=Path, default=DEFAULT_QUEUE,
        help=f"Queue JSONL path (default: {DEFAULT_QUEUE.relative_to(REPO)})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Detect + report only; do NOT mutate the queue file",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON report instead of human-readable summary",
    )
    args = parser.parse_args()

    report = route_retry_storms(
        audit_path=args.audit,
        queue_path=args.queue,
        threshold=args.threshold,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str))
        return 0

    # Human-readable
    print(f"Human-Review Router — {report.generated_at}")
    print(f"  threshold: ≥{args.threshold} attempts")
    print(f"  storms detected: {len(report.storm_ids_detected)}")
    print(f"  newly routed: {len(report.newly_routed)}")
    print(f"  already in queue: {len(report.already_routed)}")
    print(f"  queue size: {report.queue_size_before} → {report.queue_size_after}")
    print(f"  honesty: {report.honesty_signal}")
    if report.newly_routed:
        print()
        print("newly routed ids:")
        for rid in report.newly_routed[:10]:
            print(f"  - {rid}")
    if report.already_routed:
        print()
        print("already-routed ids (idempotent skip):")
        for rid in report.already_routed[:10]:
            print(f"  - {rid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
