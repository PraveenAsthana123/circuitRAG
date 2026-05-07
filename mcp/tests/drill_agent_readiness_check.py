# RESOURCES: ollama_runtime
"""
Drill: agent readiness check — does the system actually work? (iter-76).

Per CLAUDE.md §43 (drill ≥3 negatives), §44 (iter-76 ships honest
readiness report), §38 (governance — verifiable claims), §51 (forensic
substrate), §55 ("a fix-bot at 0% apply rate is not a fix-bot").

User asked three questions:
  - "will models work, are they integrated"
  - "can they fix issues, take tasks, provide solutions"
  - "which agent works, orchestrator working, work assignable"

scripts/agent_readiness_check.py answers these EMPIRICALLY (probes,
not claims). This drill locks the contract.

Locks (positive):
  L1. Script exists with canonical structure
  L2. Running it writes .loop/agent_readiness_report.json
  L3. Report has 7 dimensions (A..G)
  L4. Every dimension has {status, evidence, notes} keys
  L5. status ∈ {YES, NO, MIXED, UNKNOWN}

Locks (negative):
  N1. UNKNOWN with --strict exits non-zero (don't silently claim YES)
  N2. probe_orchestrator NEVER returns YES on connection-refused
      (regression: don't fake liveness)
  N3. probe_apply_rate flags 0% council apply with §55 brutal-rule note
      (don't paper over the §55 problem)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "agent_readiness_check.py"
REPORT = REPO / ".loop" / "agent_readiness_report.json"
sys.path.insert(0, str(REPO / "scripts"))

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


VALID_STATUSES = {"YES", "NO", "MIXED", "UNKNOWN"}


def main() -> int:
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT.relative_to(REPO)}")

    src = SCRIPT.read_text(encoding="utf-8")

    # Step 1
    step("1. canonical structure (7 probes A..G)")
    for marker in (
        "def probe_models",
        "def probe_orchestrator",
        "def probe_council",
        "def probe_apply_rate",
        "def probe_assignability",
        "def probe_mcp_fleet",
        "def probe_council_nodes",
    ):
        if marker not in src:
            fail(f"script missing canonical probe: {marker}")
    ok("7 canonical probes (A..G) present")

    # Step 2
    step("2. running script writes .loop/agent_readiness_report.json")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--write"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO),
    )
    if proc.returncode not in (0, 1):
        fail(f"script exited {proc.returncode}; stderr: {proc.stderr[:200]}")
    if not REPORT.exists():
        fail(f"report not written: {REPORT.relative_to(REPO)}")
    ok(f"report file: {REPORT.relative_to(REPO)}")

    # Step 3
    step("3. report has 7 dimensions (A..G)")
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    results = payload.get("results", {})
    expected = {
        "A_models_work", "B_orchestrator_up", "C_council_active",
        "D_apply_rate", "E_work_assignable", "F_mcp_fleet",
        "G_council_nodes",
    }
    missing = expected - set(results.keys())
    if missing:
        fail(f"report missing probes: {missing}")
    ok("all 7 probes (A..G) present in report")

    # Step 4
    step("4. every dimension has {status, evidence, notes}")
    for key, r in results.items():
        for f in ("status", "evidence", "notes"):
            if f not in r:
                fail(f"{key}: missing field {f!r}")
    ok("every probe row has {status, evidence, notes}")

    # Step 5
    step("5. status enum is one of {YES, NO, MIXED, UNKNOWN}")
    for key, r in results.items():
        if r["status"] not in VALID_STATUSES:
            fail(f"{key}: status={r['status']!r} not in {sorted(VALID_STATUSES)}")
    ok(f"all statuses valid; by_status={payload['by_status']}")

    # Step 6 — NEGATIVE: probe_orchestrator never silent-success
    step("6. NEGATIVE: probe_orchestrator never silently returns YES on conn-refused")
    import agent_readiness_check as arc  # type: ignore[import-not-found]
    saved = arc.ORCHESTRATOR_URL
    try:
        arc.ORCHESTRATOR_URL = "http://localhost:65535"  # never bound
        result = arc.probe_orchestrator()
        if result["status"] == "YES":
            fail("probe_orchestrator returned YES on connection-refused — regression")
        if result["status"] not in ("NO", "MIXED"):
            fail(f"probe_orchestrator returned {result['status']!r} on conn-refused; "
                 f"expected NO/MIXED")
    finally:
        arc.ORCHESTRATOR_URL = saved
    ok(f"unreachable orchestrator surfaces {result['status']} (no false YES)")

    # Step 7 — NEGATIVE: --strict on UNKNOWN exits non-zero
    step("7. NEGATIVE: --strict + UNKNOWN row → non-zero exit")
    # Move smoke file out of the way to force probe_models -> UNKNOWN
    smoke = REPO / ".loop" / "ollama_smoke_results.json"
    backup = REPO / ".loop" / "ollama_smoke_results.json.drill-bak"
    if smoke.exists():
        smoke.rename(backup)
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--strict", "--json"],
            capture_output=True, text=True, timeout=15, cwd=str(REPO),
        )
        if proc.returncode == 0:
            fail("--strict + UNKNOWN dimension exited 0 — silently claiming YES")
        # And the report should reflect UNKNOWN
        out = json.loads(proc.stdout)
        if "UNKNOWN" not in out["by_status"]:
            fail("removed smoke file but no UNKNOWN status surfaced")
    finally:
        if backup.exists():
            backup.rename(smoke)
    ok(f"--strict + UNKNOWN exits {proc.returncode} (honest non-zero)")

    # Step 8 — NEGATIVE: §55 brutal rule note appears when council=0%
    step("8. NEGATIVE: probe_apply_rate emits §55 brutal-rule note on 0% lane")
    # Inspect the source for the §55 reference (must be present so a 0%
    # apply rate doesn't get glossed over)
    rate_src = src[src.index("def probe_apply_rate"):src.index("def probe_assignability")]
    if "§55" not in rate_src and "0% apply rate" not in rate_src:
        fail("probe_apply_rate doesn't reference §55 brutal rule on 0%")
    ok("probe_apply_rate cites §55 (no 0% glossing)")

    print(f"\n{GREEN}{BOLD}ALL 8 STEPS PASSED (5 positive + 3 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
