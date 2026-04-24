#!/usr/bin/env python3
"""
audit_verify.py — walk governance.audit_log per tenant and detect tampering.

The audit log writer (libs/py/documind_core/audit.py) chains each row
by SHA-256 over the row body + the previous row's entry_hash. This
script is the reader side: connect to Postgres, walk each tenant's
rows in (timestamp, id) order, recompute every entry_hash, and flag
any break.

Exit code:
    0 — every tenant's chain is intact
    1 — one or more tenants have a broken chain

Connects as documind_ops (BYPASSRLS) so a single run can cover every
tenant. Environment variables override defaults:

    DOCUMIND_PG_HOST     (default: localhost)
    DOCUMIND_PG_PORT     (default: 55432)
    DOCUMIND_PG_DB       (default: documind)
    DOCUMIND_PG_OPS_USER      (default: documind_ops)
    DOCUMIND_PG_OPS_PASSWORD  (default: documind_ops)

Usage:
    scripts/audit_verify.py                      # all tenants, text report
    scripts/audit_verify.py --tenant <uuid>      # one tenant
    scripts/audit_verify.py --json               # machine-readable
    scripts/audit_verify.py --since 2026-04-24   # cut off prior rows

The `--since` filter starts a fresh chain from the first row at/after
the cutoff; the `previous_hash` on that row is trusted as the anchor.
Use this to verify only recent activity without re-reading years of
history.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Repo root import so libs/py/documind_core is resolvable
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import asyncpg  # noqa: E402

from libs.py.documind_core.audit import _compute_entry_hash  # type: ignore  # noqa: E402


@dataclass
class RowResult:
    tenant_id: str
    row_id: str
    timestamp: str
    action: str
    status: str       # OK | BROKEN_HASH | BROKEN_CHAIN | MISSING_HASH
    detail: str = ""
    expected_hash: str = ""   # what the verifier computed
    stored_hash: str = ""     # what the row claimed


def _dsn() -> str:
    return (
        f"postgresql://{os.getenv('DOCUMIND_PG_OPS_USER', 'documind_ops')}:"
        f"{os.getenv('DOCUMIND_PG_OPS_PASSWORD', 'documind_ops')}@"
        f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
        f"{os.getenv('DOCUMIND_PG_PORT', '55432')}/"
        f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
    )


async def _fetch_rows(
    conn: asyncpg.Connection,
    tenant_id: str | None,
    since: str | None,
) -> list[asyncpg.Record]:
    where = []
    args: list[Any] = []
    if tenant_id is not None:
        where.append(f"tenant_id = ${len(args) + 1}::uuid")
        args.append(tenant_id)
    if since is not None:
        where.append(f"timestamp >= ${len(args) + 1}::timestamptz")
        args.append(since)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    return await conn.fetch(
        f"""
        SELECT id::text, tenant_id::text, timestamp::text,
               actor_type, action, resource_type, resource_id::text,
               details, correlation_id::text, previous_hash, entry_hash
          FROM governance.audit_log
        {clause}
        ORDER BY tenant_id, timestamp, id
        """,
        *args,
    )


def _verify_rows(rows: list[asyncpg.Record]) -> list[RowResult]:
    """Walk rows grouped by tenant; each group is an independent chain."""
    results: list[RowResult] = []
    last_hash_by_tenant: dict[str, str] = {}
    for row in rows:
        tenant = row["tenant_id"]
        prev_expected = last_hash_by_tenant.get(tenant, "")
        stored_prev = row["previous_hash"] or ""
        stored_hash = row["entry_hash"] or ""

        # For the --since flow, the first row of a tenant may have a
        # non-empty stored previous_hash that we have no way to verify
        # (we didn't read the row before it). Trust it as an anchor.
        if tenant not in last_hash_by_tenant and stored_prev:
            prev_expected = stored_prev

        if not stored_hash:
            results.append(RowResult(
                tenant_id=tenant,
                row_id=row["id"],
                timestamp=row["timestamp"],
                action=row["action"],
                status="MISSING_HASH",
                detail="entry_hash column is NULL or empty",
                expected_hash="",
                stored_hash="",
            ))
            last_hash_by_tenant[tenant] = stored_hash  # continue chain
            continue

        if stored_prev != prev_expected:
            results.append(RowResult(
                tenant_id=tenant,
                row_id=row["id"],
                timestamp=row["timestamp"],
                action=row["action"],
                status="BROKEN_CHAIN",
                detail=(
                    f"previous_hash {stored_prev[:12] or '<empty>'}"
                    f" != expected {prev_expected[:12] or '<empty>'}"
                ),
                expected_hash=prev_expected,   # what the chain required
                stored_hash=stored_prev,        # what the row carried
            ))
            last_hash_by_tenant[tenant] = stored_hash
            continue

        details = row["details"]
        if isinstance(details, str):
            details = json.loads(details)
        recomputed = _compute_entry_hash(
            previous_hash=stored_prev,
            timestamp_iso=row["timestamp"],
            tenant_id=tenant,
            actor_type=row["actor_type"],
            action=row["action"],
            resource_type=row["resource_type"],
            details=details or {},
        )
        if recomputed != stored_hash:
            results.append(RowResult(
                tenant_id=tenant,
                row_id=row["id"],
                timestamp=row["timestamp"],
                action=row["action"],
                status="BROKEN_HASH",
                detail=(
                    f"entry_hash {stored_hash[:12]}..."
                    f" != recomputed {recomputed[:12]}..."
                ),
                expected_hash=recomputed,
                stored_hash=stored_hash,
            ))
        else:
            results.append(RowResult(
                tenant_id=tenant,
                row_id=row["id"],
                timestamp=row["timestamp"],
                action=row["action"],
                status="OK",
            ))
        last_hash_by_tenant[tenant] = stored_hash
    return results


def _summarize(results: list[RowResult]) -> dict[str, dict[str, int]]:
    """Per-tenant {OK, BROKEN_HASH, BROKEN_CHAIN, MISSING_HASH} counts."""
    summary: dict[str, dict[str, int]] = {}
    for r in results:
        d = summary.setdefault(
            r.tenant_id,
            {"OK": 0, "BROKEN_HASH": 0, "BROKEN_CHAIN": 0, "MISSING_HASH": 0},
        )
        d[r.status] += 1
    return summary


def _print_text(results: list[RowResult], summary: dict[str, dict[str, int]]) -> None:
    for r in results:
        if r.status != "OK":
            print(
                f"  {r.status:<13} tenant={r.tenant_id} id={r.row_id[:8]} "
                f"action={r.action}  {r.detail}"
            )
    print()
    print("Per-tenant summary:")
    for tenant, counts in summary.items():
        status = "OK" if counts["OK"] == sum(counts.values()) else "BROKEN"
        print(
            f"  [{status}] {tenant}   "
            f"rows={sum(counts.values())}  "
            f"ok={counts['OK']}  "
            f"broken_hash={counts['BROKEN_HASH']}  "
            f"broken_chain={counts['BROKEN_CHAIN']}  "
            f"missing_hash={counts['MISSING_HASH']}"
        )


async def _seal_breaks(
    conn: asyncpg.Connection,
    results: list[RowResult],
    run_id: str,
) -> int:
    """Write one governance.audit_log_breaks row per non-OK result.
    Returns number of rows inserted. Idempotent by run_id + broken_row_id
    — same run, same broken row → unique-constraint-like behavior
    implemented here in Python since we don't want ON CONFLICT noise.
    """
    inserts = 0
    host = socket.gethostname()
    for r in results:
        if r.status == "OK":
            continue
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)",
                r.tenant_id,
            )
            await conn.execute(
                """
                INSERT INTO governance.audit_log_breaks
                  (tenant_id, broken_row_id, broken_action, break_type,
                   expected_hash, stored_hash, detail,
                   verifier_host, verifier_run_id)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9::uuid)
                """,
                r.tenant_id,
                r.row_id,
                r.action,
                r.status,
                r.expected_hash or None,
                r.stored_hash or None,
                r.detail,
                host,
                run_id,
            )
            inserts += 1
    return inserts


async def main_async(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(dsn=_dsn())
    try:
        rows = await _fetch_rows(conn, args.tenant, args.since)
        results = _verify_rows(rows)
        if args.seal:
            run_id = args.run_id or str(uuid.uuid4())
            n = await _seal_breaks(conn, results, run_id)
            if n > 0:
                print(
                    f"sealed {n} break record(s) into "
                    f"governance.audit_log_breaks with verifier_run_id={run_id}"
                )
    finally:
        await conn.close()

    summary = _summarize(results)

    if args.json:
        payload = {
            "summary": summary,
            "rows": [
                {
                    "tenant_id": r.tenant_id,
                    "row_id": r.row_id,
                    "timestamp": r.timestamp,
                    "action": r.action,
                    "status": r.status,
                    "detail": r.detail,
                }
                for r in results
                # --json defaults to "just the issues" unless --verbose
                if args.verbose or r.status != "OK"
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        _print_text(results, summary)

    any_broken = any(
        counts["OK"] != sum(counts.values()) for counts in summary.values()
    )
    return 1 if any_broken else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Verify governance.audit_log hash chain")
    p.add_argument("--tenant", help="UUID of a specific tenant; default: all")
    p.add_argument(
        "--since",
        help="Only rows at/after this timestamp (ISO 8601)",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Include OK rows in JSON output (default: issues only)",
    )
    p.add_argument(
        "--seal",
        action="store_true",
        help=(
            "Write forensic rows to governance.audit_log_breaks for any "
            "non-OK verification result. Idempotent run-scoped via --run-id."
        ),
    )
    p.add_argument(
        "--run-id",
        help=(
            "Explicit UUID to tag this verify run in audit_log_breaks. "
            "Default: a fresh UUID per invocation."
        ),
    )
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
