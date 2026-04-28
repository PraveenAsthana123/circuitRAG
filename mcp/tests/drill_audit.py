# RESOURCES: inference mcp_hr pg
"""
Drill: prove the audit-log wiring for MCP draft lifecycle transitions.

Scenario:
 1. Restart inference-svc wired with AuditWriter. Baseline: note the
    current number of rows in governance.audit_log for the test
    tenant, and the last entry_hash.
 2. Kill MCP. Hit /api/v1/agent/ask with a leave request → draft persisted.
 3. Query governance.audit_log — a new row with action='mcp_draft.created'
    MUST be present; its previous_hash MUST equal the baseline hash;
    its entry_hash MUST equal SHA256 computed from its own body.
 4. Restart MCP. POST /api/v1/drafts/{draft_id}/resolve → replay.
 5. Query audit_log — a second new row with action='mcp_draft.replayed'
    MUST be present; its previous_hash MUST equal the row from step 3;
    its entry_hash MUST chain correctly.
 6. Final assertion: the hash chain recomputed row-by-row for this
    tenant matches the stored entry_hash on every row.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_audit.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from libs.py.documind_core.audit import _canonical_json, _compute_entry_hash  # type: ignore  # noqa: E402

TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
PG_DSN = (
    f"postgresql://{os.getenv('DOCUMIND_PG_USER', 'documind_app')}:"
    f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind_app')}@"
    f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
    f"{os.getenv('DOCUMIND_PG_PORT', '55432')}/"
    f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
)

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"
H = {"X-Tenant-Id": TENANT, "Content-Type": "application/json"}


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    log = open("/tmp/documind-mcp-hr-audit-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_hr.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )


async def _healthy(c: httpx.AsyncClient, url: str, tries: int = 30) -> bool:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    return False


async def _dead(c: httpx.AsyncClient, url: str, tries: int = 10) -> None:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=1.0)
            if r.status_code != 200:
                return
        except httpx.HTTPError:
            return
        await asyncio.sleep(0.3)


async def _last_audit_hash(pool: asyncpg.Pool) -> tuple[str, int]:
    """Return (last entry_hash, row count) for the test tenant.

    Uses a tenant-scoped session because ``documind_app`` is NOBYPASSRLS —
    without ``SET LOCAL app.current_tenant`` the RLS policy hides every
    tenant-scoped row.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            rows = await conn.fetch(
                """
                SELECT entry_hash FROM governance.audit_log
                 WHERE tenant_id = $1::uuid
                 ORDER BY timestamp, id
                """,
                TENANT,
            )
    if not rows:
        return "", 0
    return rows[-1]["entry_hash"] or "", len(rows)


async def _all_audit_rows(pool: asyncpg.Pool) -> list:
    """Return every audit row for the test tenant under a tenant session."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            return await conn.fetch(
                """
                SELECT timestamp::text, tenant_id::text, actor_type, action,
                       resource_type, resource_id, details, correlation_id::text,
                       previous_hash, entry_hash
                  FROM governance.audit_log
                 WHERE tenant_id = $1::uuid
                 ORDER BY timestamp, id
                """,
                TENANT,
            )


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as c:
        # --- 0 ---
        step("0. sanity — inference + MCP healthy")
        if (await c.get(f"{INFERENCE}/health")).status_code != 200:
            fail(f"inference not healthy at {INFERENCE}")
        if not await _healthy(c, MCP_BASE, tries=2):
            fail(f"MCP not healthy at {MCP_BASE} — start it first")
        ok("services up")

        pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
        try:
            baseline_hash, baseline_count = await _last_audit_hash(pool)
            ok(f"baseline audit rows for tenant={baseline_count} last_hash={baseline_hash[:12]}...")

            # --- 1: kill MCP ---
            step("1. kill MCP")
            _kill_mcp()
            await _dead(c, MCP_BASE)
            ok("MCP down")

            # --- 2: agent/ask → draft ---
            step("2. agent/ask → draft created")
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers=H,
                json={
                    "query": "Please submit a 5-day leave request for audit drill",
                    "employee_id": "E42",
                },
            )
            if r.status_code != 200:
                fail(f"agent/ask {r.status_code}: {r.text[:300]}")
            action = r.json().get("action") or {}
            if not action.get("degraded") or not action.get("draft_id"):
                fail(f"expected degraded+draft: {action}")
            draft_id = action["draft_id"]
            ok(f"degraded draft_id={draft_id}")

            # --- 3: verify audit row for draft.created ---
            step("3. audit row for mcp_draft.created exists + chains")
            # give the async audit write a moment
            await asyncio.sleep(0.5)
            rows = await _all_audit_rows(pool)
            if len(rows) != baseline_count + 1:
                fail(f"expected {baseline_count + 1} rows got {len(rows)}")
            new_row = rows[-1]
            if new_row["action"] != "mcp_draft.created":
                fail(f"wrong action: {new_row['action']}")
            details = new_row["details"]
            if isinstance(details, str):
                details = json.loads(details)
            if details.get("draft_id") != draft_id:
                fail(f"draft_id mismatch: {details}")
            if new_row["previous_hash"] != baseline_hash:
                fail(f"previous_hash mismatch: expected {baseline_hash!r} got {new_row['previous_hash']!r}")
            expected_hash = _compute_entry_hash(
                previous_hash=new_row["previous_hash"] or "",
                timestamp_iso=new_row["timestamp"],
                tenant_id=new_row["tenant_id"],
                actor_type=new_row["actor_type"],
                action=new_row["action"],
                resource_type=new_row["resource_type"],
                details=details,
            )
            if expected_hash != new_row["entry_hash"]:
                fail(f"entry_hash mismatch: expected {expected_hash[:16]}... got {new_row['entry_hash'][:16]}...")
            ok(f"mcp_draft.created row chain-valid hash={new_row['entry_hash'][:12]}...")

            # --- 4: restart MCP, resolve via admin API ---
            step("4. restart MCP → POST /drafts/{id}/resolve")
            mcp_proc = _spawn_mcp()
            if not await _healthy(c, MCP_BASE):
                fail("MCP didn't come back")
            ok("MCP back up")
            print("    waiting 32s for CB recovery_timeout...")
            await asyncio.sleep(32)
            r = await c.post(
                f"{INFERENCE}/api/v1/drafts/{draft_id}/resolve", headers=H, timeout=60.0,
            )
            if r.status_code != 200 or not r.json().get("ok"):
                fail(f"resolve failed: {r.status_code} {r.text[:200]}")
            ticket = (r.json().get("result") or {}).get("ticket_id")
            ok(f"replayed ticket_id={ticket}")

            # --- 5: verify audit row for draft.replayed ---
            step("5. audit row for mcp_draft.replayed chains onto prior")
            await asyncio.sleep(0.5)
            rows = await _all_audit_rows(pool)
            if len(rows) != baseline_count + 2:
                fail(f"expected {baseline_count + 2} rows got {len(rows)}")
            r2 = rows[-1]
            if r2["action"] != "mcp_draft.replayed":
                fail(f"wrong action: {r2['action']}")
            if r2["previous_hash"] != new_row["entry_hash"]:
                fail(
                    f"chain broken: replayed.previous={r2['previous_hash'][:12]} "
                    f"vs created.entry={new_row['entry_hash'][:12]}"
                )
            details2 = r2["details"]
            if isinstance(details2, str):
                details2 = json.loads(details2)
            if details2.get("draft_id") != draft_id:
                fail(f"replayed row draft_id mismatch: {details2}")
            if (details2.get("result") or {}).get("ticket_id") != ticket:
                fail(f"replayed row ticket_id mismatch: {details2.get('result')}")
            expected_hash2 = _compute_entry_hash(
                previous_hash=r2["previous_hash"] or "",
                timestamp_iso=r2["timestamp"],
                tenant_id=r2["tenant_id"],
                actor_type=r2["actor_type"],
                action=r2["action"],
                resource_type=r2["resource_type"],
                details=details2,
            )
            if expected_hash2 != r2["entry_hash"]:
                fail(f"replayed entry_hash mismatch")
            ok(f"mcp_draft.replayed chain-valid hash={r2['entry_hash'][:12]}... details.ticket_id={ticket}")

            # --- 6: full-chain verification ---
            step("6. full-chain verify — every row hash recomputes")
            prev = ""
            for i, row in enumerate(rows):
                d = row["details"]
                if isinstance(d, str):
                    d = json.loads(d)
                if row["previous_hash"] != prev:
                    fail(f"row {i} previous_hash broken: expected {prev[:12]} got {row['previous_hash'][:12]}")
                expected = _compute_entry_hash(
                    previous_hash=row["previous_hash"] or "",
                    timestamp_iso=row["timestamp"],
                    tenant_id=row["tenant_id"],
                    actor_type=row["actor_type"],
                    action=row["action"],
                    resource_type=row["resource_type"],
                    details=d,
                )
                if expected != row["entry_hash"]:
                    fail(f"row {i} entry_hash mismatch")
                prev = row["entry_hash"]
            ok(f"all {len(rows)} rows hash-valid, chain intact end-to-end")

        finally:
            await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 AUDIT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
