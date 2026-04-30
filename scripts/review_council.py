#!/usr/bin/env python3
"""Review tool — surfaces the latest council take per unique issue.

Reads .loop/issue_audit.jsonl, groups by issue id, picks the most-
recent council row per id, prints AUTHOR diff + REVIEWER critique +
ADVISOR synthesis. Operator decides per issue: apply / skip / reject.

Decisions persist to .loop/issue_decisions.jsonl with timestamp.

Default is read-only summary (no apply, no skip). Operator drives via
flags:
    --interactive  step through each issue with prompts
    --apply <id>   record an "applied" decision for one id (operator
                   then applies the diff manually + commits)
    --skip <id>    record a "skip" decision for one id
    --reject <id>  record a "reject" decision (mark as not actionable)
    --since <iso>  only consider audit rows newer than ISO timestamp

The decisions file is the source of truth for "which issues did the
operator review and what was the call". Running review again skips
issues with a decision already recorded (unless --rerun).

Usage:
    python3 scripts/review_council.py                    # summary
    python3 scripts/review_council.py --interactive      # step through
    python3 scripts/review_council.py --apply <issue-id> # record decision

Locked by mcp/tests/drill_issue_dispatcher_format.py (next iter).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / ".loop" / "issue_audit.jsonl"
DECISIONS = REPO / ".loop" / "issue_decisions.jsonl"


def load_council_rows(since_iso: str | None = None) -> list[dict]:
    if not AUDIT.exists():
        return []
    rows = []
    for line in AUDIT.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("lane") != "council":
            continue
        if since_iso and r.get("ts", "") < since_iso:
            continue
        rows.append(r)
    return rows


def latest_per_id(rows: list[dict]) -> dict[str, dict]:
    """Group by issue id, keep latest by ts."""
    by_id: dict[str, dict] = {}
    for r in rows:
        rid = r.get("id", "")
        if not rid:
            continue
        ts = r.get("ts", "")
        if rid not in by_id or ts > by_id[rid].get("ts", ""):
            by_id[rid] = r
    return by_id


def load_decisions() -> dict[str, dict]:
    if not DECISIONS.exists():
        return {}
    out: dict[str, dict] = {}
    for line in DECISIONS.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = d.get("id", "")
        if rid:
            out[rid] = d  # last write wins
    return out


def write_decision(issue_id: str, decision: str, note: str = "") -> None:
    DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "id": issue_id,
        "decision": decision,
        "note": note,
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with DECISIONS.open("a") as f:
        f.write(json.dumps(row) + "\n")


def print_council(issue_id: str, row: dict) -> None:
    chain = row.get("chain", {})
    print(f"\n{'='*70}")
    print(f"ISSUE: {issue_id}")
    print(f"  ts: {row.get('ts', '?')}")
    print(f"{'='*70}")
    for role in ("author", "reviewer", "advisor"):
        info = chain.get(role, {})
        model = info.get("model", "?")
        tokens = info.get("tokens", 0)
        latency = info.get("latency_s", 0)
        output = info.get("output", "")
        print(f"\n--- {role.upper()} ({model}, {tokens} tokens, {latency}s) ---")
        # Trim excessive output but keep the diff visible
        print(output[:1500])
        if len(output) > 1500:
            print("...[truncated]...")


def summary(rows: list[dict], decisions: dict[str, dict]) -> None:
    latest = latest_per_id(rows)
    print(f"\n{'='*70}")
    print("COUNCIL REVIEW SUMMARY")
    print(f"{'='*70}")
    print(f"Total council audit rows: {len(rows)}")
    print(f"Unique issues:            {len(latest)}")
    print(f"Decisions recorded:       {len(decisions)}")
    print("\nPer-issue state:")
    for rid in sorted(latest):
        decision = decisions.get(rid, {}).get("decision", "PENDING")
        ts = latest[rid].get("ts", "?")[-12:]
        print(f"  [{decision:8}] {rid}  (last council: {ts})")


def interactive(rows: list[dict], decisions: dict[str, dict], rerun: bool) -> None:
    latest = latest_per_id(rows)
    pending_ids = [rid for rid in latest if rerun or rid not in decisions]
    if not pending_ids:
        print("No pending issues. Use --rerun to revisit decided ones.")
        return
    print(f"\n{len(pending_ids)} issue(s) pending review.\n")
    for rid in sorted(pending_ids):
        print_council(rid, latest[rid])
        while True:
            ans = input("\n[a]pply / [s]kip / [r]eject / [q]uit > ").strip().lower()
            if ans == "q":
                print("Quit; remaining issues unchanged.")
                return
            if ans in ("a", "s", "r"):
                kind = {"a": "applied", "s": "skip", "r": "reject"}[ans]
                note = input("Note (optional): ").strip()
                write_decision(rid, kind, note)
                print(f"  recorded: {kind}")
                break
            print("invalid; try again")
    print("\nAll pending reviewed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", action="store_true",
                        help="step through pending issues with prompts")
    parser.add_argument("--apply", metavar="ID",
                        help="record 'applied' decision for issue id")
    parser.add_argument("--skip", metavar="ID",
                        help="record 'skip' decision for issue id")
    parser.add_argument("--reject", metavar="ID",
                        help="record 'reject' decision for issue id")
    parser.add_argument("--note", default="", help="note for the decision")
    parser.add_argument("--since", help="ISO timestamp; only newer audit rows")
    parser.add_argument("--rerun", action="store_true",
                        help="re-review issues with existing decisions")
    args = parser.parse_args()

    rows = load_council_rows(since_iso=args.since)
    decisions = load_decisions()

    if args.apply:
        write_decision(args.apply, "applied", args.note)
        print(f"recorded applied: {args.apply}")
        return 0
    if args.skip:
        write_decision(args.skip, "skip", args.note)
        print(f"recorded skip: {args.skip}")
        return 0
    if args.reject:
        write_decision(args.reject, "reject", args.note)
        print(f"recorded reject: {args.reject}")
        return 0

    if args.interactive:
        interactive(rows, decisions, args.rerun)
    else:
        summary(rows, decisions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
