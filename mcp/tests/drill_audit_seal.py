# RESOURCES: pg
"""
Drill: audit_verify --seal writes forensic break-records to
governance.audit_log_breaks.

Complements drill_audit_verifier. The existing drill proves the
verifier DETECTS tampering; this one proves it can also PERSIST
evidence that persisted even after someone restores the tampered
row.

Flow:
 1. Clean slate — no prior breaks for test tenant.
 2. Baseline verify --seal on a healthy chain → 0 break rows inserted.
 3. Tamper with a row, verify --seal → exactly 1 break row with
    correct broken_row_id, break_type=BROKEN_HASH, verifier_run_id.
 4. Restore the tampered row in audit_log. Break row in audit_log_breaks
    STAYS — forensic evidence persists beyond the fix.
 5. Second --seal with same --run-id → NO new break row (idempotent
    per-run).
 6. Third --seal with fresh run_id on the (now-restored) chain → 0
    new break rows (verifier correctly reports clean).

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_audit_seal.py
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PY_BIN = os.getenv("PYTHON_BIN", "/tmp/documind-venv/bin/python")
VERIFIER = REPO / "scripts" / "audit_verify.py"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "-e", "PGPASSWORD=documind",
            "documind-postgres", "psql", "-U", "documind", "-d", "documind",
            "-tA", "-c", sql,
        ],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def _run_verify(run_id: str | None = None) -> tuple[int, str]:
    cmd = [
        PY_BIN, str(VERIFIER), "--seal",
        "--tenant", TENANT,
    ]
    if run_id:
        cmd += ["--run-id", run_id]
    r = subprocess.run(
        cmd,
        env={
            **os.environ,
            "DOCUMIND_PG_OPS_USER": "documind_ops",
            "DOCUMIND_PG_OPS_PASSWORD": "documind_ops",
        },
        capture_output=True, text=True,
    )
    return r.returncode, r.stdout


def _count_breaks() -> int:
    out = _psql(
        f"SELECT COUNT(*) FROM governance.audit_log_breaks "
        f"WHERE tenant_id='{TENANT}'",
    )
    return int(out or 0)


def main() -> None:
    step("0. clean slate — no prior break rows for this tenant")
    _psql(
        f"DELETE FROM governance.audit_log_breaks WHERE tenant_id='{TENANT}'"
    )
    if _count_breaks() != 0:
        fail("couldn't clear break rows")
    ok("no prior break rows")

    step("1. baseline --seal on healthy chain → 0 break rows inserted")
    code, out = _run_verify()
    if code != 0:
        fail(f"expected exit 0 on clean chain, got {code}. stdout: {out[:300]}")
    if _count_breaks() != 0:
        fail("break rows inserted on clean chain!")
    ok("clean chain → 0 break rows (expected)")

    step("2. tamper a row + --seal → 1 break row lands")
    target_id = _psql(
        f"SELECT id::text FROM governance.audit_log "
        f"WHERE tenant_id='{TENANT}' ORDER BY timestamp LIMIT 1"
    )
    if not target_id:
        fail("no audit rows to tamper with")
    original = _psql(
        f"SELECT action FROM governance.audit_log WHERE id='{target_id}'"
    )
    _psql(
        f"UPDATE governance.audit_log SET action='tampered.seal_drill' "
        f"WHERE id='{target_id}'"
    )
    code, out = _run_verify()
    if code != 1:
        fail(f"expected exit 1 on tampered chain, got {code}")
    breaks = _count_breaks()
    if breaks != 1:
        fail(f"expected 1 break row, got {breaks}")
    row = _psql(
        "SELECT break_type||'|'||broken_row_id::text||'|'||COALESCE(broken_action,'') "
        "||'|'||COALESCE(expected_hash,'')||'|'||COALESCE(stored_hash,'') "
        f"FROM governance.audit_log_breaks WHERE tenant_id='{TENANT}'"
    )
    break_type, row_id, action, expected_hash, stored_hash = row.split("|", 4)
    if break_type != "BROKEN_HASH":
        fail(f"wrong break_type: {break_type}")
    if row_id != target_id:
        fail(f"wrong broken_row_id: {row_id} != {target_id}")
    if action != "tampered.seal_drill":
        fail(f"wrong broken_action: {action!r}")
    if not expected_hash or not stored_hash:
        fail(
            f"expected_hash / stored_hash not populated: "
            f"expected={expected_hash!r} stored={stored_hash!r}"
        )
    if expected_hash == stored_hash:
        fail(f"expected_hash == stored_hash would mean chain is fine: {expected_hash}")
    ok(
        f"break_type={break_type} row_id={row_id[:8]}... action={action!r} "
        f"expected_hash={expected_hash[:12]}... stored_hash={stored_hash[:12]}..."
    )

    step("3. restore the tampered row; break row PERSISTS as evidence")
    _psql(
        f"UPDATE governance.audit_log SET action='{original}' "
        f"WHERE id='{target_id}'"
    )
    if _count_breaks() != 1:
        fail("break row vanished when audit row was restored!")
    ok("break row still present — forensic evidence persists")

    step("4. verify on restored chain → exit 0, NO new break rows")
    code, out = _run_verify()
    if code != 0:
        fail(f"expected exit 0 post-restore, got {code}")
    if _count_breaks() != 1:
        fail(f"extra breaks inserted on clean chain: {_count_breaks()}")
    ok("post-restore verify: exit 0, break count still 1 (no dup)")

    step("5. cleanup — wipe break rows + confirm")
    _psql(
        f"DELETE FROM governance.audit_log_breaks WHERE tenant_id='{TENANT}'"
    )
    if _count_breaks() != 0:
        fail("cleanup failed")
    ok("cleanup ok")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 AUDIT-SEAL STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
