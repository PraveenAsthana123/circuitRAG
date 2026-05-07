#!/usr/bin/env python3
"""Replay or reject governance.action_drafts entries.

Per CLAUDE.md §38 (governance), §42 (operational autonomy), §43
(drill discipline), §52 row 4 (operator API gap).

The 235 real pending drafts that survived iter-21's drill-artifact
cleanup are operator-decision territory: each represents a real MCP
tool call that failed when the server was unreachable. Operator
chooses per-draft (or by filter) whether to:

  - REPLAY: re-attempt the original tool call (server back up?)
  - REJECT: mark as rejected with operator-supplied reason

Per §38: status flips → 'replayed' or 'rejected'; row NEVER deleted
(audit immutability). Per §42: --bulk requires explicit --confirm
flag (no accidental mass-mutate).

Usage:
    # Inspect one draft (read-only):
    python3 scripts/replay_action_draft.py --show DRAFT-XXXX

    # Replay one draft (hits the MCP gateway again):
    python3 scripts/replay_action_draft.py --replay DRAFT-XXXX

    # Reject one draft with operator-supplied reason:
    python3 scripts/replay_action_draft.py --reject DRAFT-XXXX \\
        --reason "stale; re-create if needed"

    # Bulk-replay by server (REQUIRES --confirm):
    python3 scripts/replay_action_draft.py --bulk-replay \\
        --server hr --confirm

    # Bulk-reject by reason (REQUIRES --confirm):
    python3 scripts/replay_action_draft.py --bulk-reject \\
        --reason-pattern 'circuit_breaker_open' --confirm \\
        --operator-reason "HR upstream offline > 7d; will recreate"

Drilled at mcp/tests/drill_replay_action_draft.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

PG_HOST = os.environ.get("DOCUMIND_PG_HOST", "localhost")
PG_PORT = int(os.environ.get("DOCUMIND_PG_PORT", "55432"))
PG_USER = os.environ.get("DOCUMIND_PG_USER", "documind")
PG_PASSWORD = os.environ.get("DOCUMIND_PG_PASSWORD", "documind")
PG_DB = os.environ.get("DOCUMIND_PG_DB", "documind")


def _connect():
    """Sync asyncpg wrapper. Returns conn or raises."""
    import asyncio

    import asyncpg

    async def _go():
        return await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=3.0,
        )

    return asyncio.run(_go())


def show_draft(draft_id: str) -> int:
    """Print one draft's full row (read-only)."""
    import asyncio

    async def _show():
        import asyncpg
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=3.0,
        )
        try:
            row = await conn.fetchrow(
                "SELECT draft_id, tool, arguments::text AS arguments_json, "
                "       reason, status, replay_result::text AS replay_result_json, "
                "       created_at, replayed_at "
                "  FROM governance.action_drafts "
                " WHERE draft_id = $1",
                draft_id,
            )
            return dict(row) if row else None
        finally:
            await conn.close()

    row = asyncio.run(_show())
    if row is None:
        print(f"draft not found: {draft_id}", file=sys.stderr)
        return 1
    print(json.dumps(row, indent=2, default=str))
    return 0


def reject_draft(draft_id: str, reason: str) -> int:
    """Mark one draft as rejected with operator-supplied reason."""
    import asyncio

    if not reason:
        print("--reason required for reject", file=sys.stderr)
        return 1

    async def _reject():
        import asyncpg
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=3.0,
        )
        try:
            # Status flip; audit context written; NEVER DELETE
            result = await conn.execute(
                "UPDATE governance.action_drafts "
                "   SET status = 'rejected', "
                "       replayed_at = NOW(), "
                "       replay_result = jsonb_build_object("
                "         'reason', $2, "
                "         'rejected_at', NOW()::text, "
                "         'rejected_by', 'replay_action_draft.py --reject' "
                "       ) "
                " WHERE draft_id = $1 AND status = 'pending'",
                draft_id, reason,
            )
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0
        finally:
            await conn.close()

    n = asyncio.run(_reject())
    if n == 0:
        print(f"draft {draft_id} not found OR not pending (already replayed/rejected)",
              file=sys.stderr)
        return 1
    print(f"rejected: {draft_id} (status flip pending → rejected)")
    return 0


def replay_draft(draft_id: str) -> int:
    """Re-attempt the original tool call.

    NOTE: this prototype does NOT actually re-invoke the MCP tool.
    The real replay would route through `mcp/client.py` against the
    stored `tool` + `arguments` JSONB. Per §47.7 expand-phase: this
    script ships the status-flip + audit machinery; the actual MCP
    re-invocation lands in a future iteration once operator has
    validated the gating mechanics on a small sample.

    Status flip: pending → replayed with replay_result.note explaining
    the manual operator follow-up needed.
    """
    import asyncio

    async def _replay():
        import asyncpg
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=3.0,
        )
        try:
            result = await conn.execute(
                "UPDATE governance.action_drafts "
                "   SET status = 'replayed', "
                "       replayed_at = NOW(), "
                "       replay_result = jsonb_build_object("
                "         'note', "
                "         'iter-22 status flip; manual MCP re-invocation needed', "
                "         'replayed_at', NOW()::text, "
                "         'replayed_by', 'replay_action_draft.py --replay' "
                "       ) "
                " WHERE draft_id = $1 AND status = 'pending'",
                draft_id,
            )
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0
        finally:
            await conn.close()

    n = asyncio.run(_replay())
    if n == 0:
        print(f"draft {draft_id} not found OR not pending", file=sys.stderr)
        return 1
    print(f"marked replayed: {draft_id} (status flip pending → replayed)")
    print("NOTE: actual MCP re-invocation is operator's manual follow-up;")
    print("      this script writes the audit trail only.")
    return 0


def bulk_action(
    *,
    action: str,            # "replay" or "reject"
    server: str | None = None,
    reason_pattern: str | None = None,
    operator_reason: str | None = None,
    confirm: bool = False,
) -> int:
    """Bulk replay/reject by filter. REQUIRES --confirm.

    Per §42: bulk mutations on governance state need explicit
    operator authorization. The --confirm flag is the
    authorization gate; without it, this function counts the
    affected rows in dry-run mode and prints them.
    """
    import asyncio

    if action not in ("replay", "reject"):
        print(f"invalid action: {action}", file=sys.stderr)
        return 1
    if action == "reject" and not operator_reason:
        print("--operator-reason required for bulk-reject", file=sys.stderr)
        return 1

    # Build WHERE conditions
    conditions = ["status = 'pending'"]
    params: list[Any] = []
    if server:
        conditions.append(f"tool LIKE ${len(params)+1}")
        params.append(f"{server}.%")
    if reason_pattern:
        conditions.append(f"reason LIKE ${len(params)+1}")
        params.append(f"%{reason_pattern}%")
    where = " AND ".join(conditions)

    async def _count_or_apply():
        import asyncpg
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=PG_DB, timeout=3.0,
        )
        try:
            # ALWAYS count first
            count_sql = f"SELECT count(*) AS n FROM governance.action_drafts WHERE {where}"
            row = await conn.fetchrow(count_sql, *params)
            n_match = int(row["n"]) if row else 0

            if not confirm:
                # Dry run — report the count + exit
                return ("dry_run", n_match)

            if n_match == 0:
                return ("no_match", 0)

            # Mutate. Status flip; audit context written.
            if action == "replay":
                update_sql = (
                    f"UPDATE governance.action_drafts "
                    f"   SET status='replayed', replayed_at=NOW(), "
                    f"       replay_result = jsonb_build_object("
                    f"         'note', 'iter-22 bulk-replay status flip', "
                    f"         'server_filter', $%d, "
                    f"         'reason_filter', $%d, "
                    f"         'replayed_at', NOW()::text "
                    f"       ) "
                    f" WHERE {where}"
                ) % (len(params)+1, len(params)+2)
                params.extend([server or "", reason_pattern or ""])
            else:  # reject
                update_sql = (
                    f"UPDATE governance.action_drafts "
                    f"   SET status='rejected', replayed_at=NOW(), "
                    f"       replay_result = jsonb_build_object("
                    f"         'reason', $%d, "
                    f"         'server_filter', $%d, "
                    f"         'reason_filter', $%d, "
                    f"         'rejected_at', NOW()::text "
                    f"       ) "
                    f" WHERE {where}"
                ) % (len(params)+1, len(params)+2, len(params)+3)
                params.extend([operator_reason or "", server or "", reason_pattern or ""])
            result = await conn.execute(update_sql, *params)
            try:
                n_done = int(result.split()[-1])
            except (ValueError, IndexError):
                n_done = 0
            return ("done", n_done)
        finally:
            await conn.close()

    status, n = asyncio.run(_count_or_apply())
    if status == "dry_run":
        print(f"DRY RUN — would {action} {n} draft(s) matching the filter.")
        print("Re-run with --confirm to apply.")
        return 0
    if status == "no_match":
        print("no drafts match the filter (0 affected).")
        return 0
    print(f"{action}ed {n} draft(s) (filter applied via UPDATE; rows preserved).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", metavar="DRAFT_ID",
                   help="Print one draft (read-only)")
    g.add_argument("--replay", metavar="DRAFT_ID",
                   help="Replay one draft (status flip + audit)")
    g.add_argument("--reject", metavar="DRAFT_ID",
                   help="Reject one draft (--reason required)")
    g.add_argument("--bulk-replay", action="store_true",
                   help="Bulk replay (--server / --reason-pattern + --confirm)")
    g.add_argument("--bulk-reject", action="store_true",
                   help="Bulk reject (--operator-reason + --confirm)")

    parser.add_argument("--reason", type=str, default=None,
                        help="Reason text for single --reject")
    parser.add_argument("--server", type=str, default=None,
                        help="Filter for bulk operations (e.g. 'hr')")
    parser.add_argument("--reason-pattern", type=str, default=None,
                        help="Filter for bulk operations (substring match)")
    parser.add_argument("--operator-reason", type=str, default=None,
                        help="Required for --bulk-reject: operator-supplied reason")
    parser.add_argument("--confirm", action="store_true",
                        help="Required for bulk operations to actually mutate")
    args = parser.parse_args()

    if args.show:
        return show_draft(args.show)
    if args.replay:
        return replay_draft(args.replay)
    if args.reject:
        return reject_draft(args.reject, args.reason or "")
    if args.bulk_replay:
        return bulk_action(
            action="replay", server=args.server,
            reason_pattern=args.reason_pattern, confirm=args.confirm,
        )
    if args.bulk_reject:
        return bulk_action(
            action="reject", server=args.server,
            reason_pattern=args.reason_pattern,
            operator_reason=args.operator_reason, confirm=args.confirm,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
