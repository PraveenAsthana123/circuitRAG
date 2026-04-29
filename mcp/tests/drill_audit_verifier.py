# RESOURCES: pg
"""
Drill: audit_verify.py detects tampering in governance.audit_log.

Flow:
 1. Baseline: run the verifier — exit 0, all OK.
 2. Flip one attribute in a random audit row (mutate `action` from
    'mcp_draft.created' to 'mcp_draft.injected').
 3. Run verifier — exit 1 + BROKEN_HASH report on that row.
 4. Restore the row; verifier returns clean again.
 5. Insert a synthetic row with a bad `previous_hash` value (chain
    break, not hash break).
 6. Run verifier — exit 1 + BROKEN_CHAIN on the new row AND on every
    subsequent row since they chain on a now-broken anchor.
 7. Delete the synthetic row — verifier clean.

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_audit_verifier.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERIFIER = REPO / "scripts" / "audit_verify.py"
PY = os.getenv("PYTHON_BIN", "/tmp/documind-venv/bin/python")

TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _psql(sql: str) -> str:
    """Run a statement via docker exec as documind (superuser) so RLS
    doesn't interfere with our mutation."""
    r = subprocess.run(
        [
            "docker", "exec", "-e", "PGPASSWORD=documind",
            "documind-postgres", "psql", "-U", "documind", "-d", "documind",
            "-tA", "-c", sql,
        ],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def _run_verifier(extra: list[str] | None = None) -> dict:
    cmd = [
        PY, str(VERIFIER), "--json",
        "--tenant", TENANT,
    ] + (extra or [])
    r = subprocess.run(
        cmd,
        env={
            **os.environ,
            "DOCUMIND_PG_OPS_USER": "documind_ops",
            "DOCUMIND_PG_OPS_PASSWORD": "documind_ops",
        },
        capture_output=True, text=True,
    )
    body = json.loads(r.stdout)
    return {"exit": r.returncode, "summary": body["summary"], "rows": body["rows"]}


def main() -> None:
    step("1. baseline — verifier clean (exit 0, all OK)")
    before = _run_verifier()
    if before["exit"] != 0:
        fail(f"expected exit 0 got {before['exit']}: {before}")
    summary = before["summary"].get(TENANT, {})
    if summary.get("OK", 0) == 0:
        fail(f"no OK rows — is audit_log empty? {summary}")
    baseline_ok = summary["OK"]
    ok(f"baseline {baseline_ok} rows, all OK")

    step("2. tamper — flip `action` of one row in place")
    # Pick the oldest row so any chain break cascades forward.
    target_id = _psql(
        f"SELECT id::text FROM governance.audit_log "
        f"WHERE tenant_id='{TENANT}' ORDER BY timestamp, id LIMIT 1"
    )
    if not target_id:
        fail("no audit rows to tamper with")
    original_action = _psql(
        f"SELECT action FROM governance.audit_log WHERE id='{target_id}'"
    )
    _psql(
        f"UPDATE governance.audit_log SET action='mcp_draft.injected' "
        f"WHERE id='{target_id}'"
    )
    ok(f"tampered row id={target_id[:8]} action={original_action!r} → 'mcp_draft.injected'")

    step("3. verifier detects BROKEN_HASH on the tampered row")
    result = _run_verifier()
    if result["exit"] != 1:
        fail(f"expected exit 1 got {result['exit']}: {result}")
    issues = result["rows"]
    broken_hash = [r for r in issues if r["status"] == "BROKEN_HASH"]
    if not broken_hash:
        fail(f"no BROKEN_HASH in report: {issues}")
    first = broken_hash[0]
    if first["row_id"] != target_id:
        fail(f"wrong row flagged: {first['row_id']} (expected {target_id})")
    ok(
        f"BROKEN_HASH caught id={first['row_id'][:8]} "
        f"action={first['action']!r} detail={first['detail']}"
    )
    # Every subsequent row should chain-break too because the tampered
    # row's entry_hash was computed over the ORIGINAL action; the next
    # row's previous_hash still matches, but OUR recompute uses the
    # MUTATED action, so the chain appears to split mid-stream.
    # Note: we don't assert cascade here — the hash-break on row 1 is
    # the decisive signal; cascade depth depends on how the verifier
    # tracks expected_prev, which we keep strict (it tracks the
    # STORED entry_hash, not the recomputed one — so subsequent rows
    # stay OK in this drill).
    ok(f"exit code=1 (tampering detected)")

    step("4. restore row; verifier clean again")
    _psql(
        f"UPDATE governance.audit_log SET action='{original_action}' "
        f"WHERE id='{target_id}'"
    )
    result = _run_verifier()
    if result["exit"] != 0:
        fail(f"expected exit 0 after restore got {result['exit']}: {result}")
    restored = result["summary"].get(TENANT, {}).get("OK", 0)
    if restored != baseline_ok:
        fail(f"post-restore OK count {restored} != baseline {baseline_ok}")
    ok(f"all {restored} rows OK again")

    step("5. insert row with bad previous_hash — chain break")
    # Use an obviously-wrong previous_hash so we get a BROKEN_CHAIN,
    # not a BROKEN_HASH.
    _psql(
        f"""
        INSERT INTO governance.action_drafts (draft_id, tenant_id, tool,
            arguments, reason, status, created_at)
        VALUES ('DRAFT-VERIFIER-DRILL', '{TENANT}', 'hr.leave_request',
            '{{}}'::jsonb, 'drill', 'pending', NOW())
        ON CONFLICT (draft_id) DO NOTHING
        """
    )
    # Build a matching entry_hash so BROKEN_HASH doesn't fire; then flip
    # previous_hash. Easier: just INSERT a row with a bogus previous_hash
    # and an entry_hash that matches our bogus-previous-hash computation.
    # Simpler still: skip hash computation — make the row look tampered at
    # the chain level only. We set entry_hash = some deterministic value,
    # previous_hash = wrong one. The verifier will hit BROKEN_CHAIN (it
    # checks chain before recompute).
    bogus_prev = "deadbeef" * 8  # 64 hex chars, won't match anything
    bogus_entry = "cafebabe" * 8
    _psql(
        f"""
        INSERT INTO governance.audit_log
            (timestamp, tenant_id, actor_type, action, resource_type,
             details, previous_hash, entry_hash)
        VALUES (NOW() + interval '1 second', '{TENANT}', 'service',
                'drill.injected', 'mcp_draft', '{{}}'::jsonb,
                '{bogus_prev}', '{bogus_entry}')
        """
    )
    ok("synthetic row injected with bogus previous_hash")

    step("6. verifier reports BROKEN_CHAIN on the injected row")
    result = _run_verifier()
    if result["exit"] != 1:
        fail(f"expected exit 1 got {result['exit']}")
    chain_breaks = [r for r in result["rows"] if r["status"] == "BROKEN_CHAIN"]
    if not chain_breaks:
        fail(f"no BROKEN_CHAIN: {result['rows']}")
    injected = [r for r in chain_breaks if r["action"] == "drill.injected"]
    if not injected:
        fail(f"injected row not flagged as BROKEN_CHAIN: {chain_breaks}")
    ok(f"BROKEN_CHAIN caught action=drill.injected detail={injected[0]['detail']}")

    step("7. delete synthetic row + draft; verifier clean")
    _psql(
        f"DELETE FROM governance.audit_log WHERE action='drill.injected'"
    )
    _psql(
        f"DELETE FROM governance.action_drafts WHERE draft_id='DRAFT-VERIFIER-DRILL'"
    )
    result = _run_verifier()
    if result["exit"] != 0:
        fail(f"expected exit 0 after cleanup got {result['exit']}: {result}")
    ok(f"cleanup OK, exit=0")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 AUDIT-VERIFIER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
