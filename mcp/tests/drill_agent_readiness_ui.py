# RESOURCES: readonly
"""
Drill: /admin/agent-readiness UI + /api/v1/agent-readiness BFF (iter-77).

Per CLAUDE.md §43 (drill ≥3 negatives), §44 (iter-77 ships UI),
§38 (governance — verifiable claims), §51 (forensic substrate),
§55 (apply-rate is non-negotiable governance).

Locks (positive):
  L1. BFF route + frontend page exist at canonical paths
  L2. BFF reads .loop/agent_readiness_report.json
  L3. BFF re-runs script when file is stale (>5 min)
  L4. Frontend renders all 7 probes A..G with titles
  L5. Frontend StatusBadge covers YES/NO/MIXED/UNKNOWN

Locks (negative):
  N1. BFF NEVER calls a write tool (read-only contract)
  N2. Frontend ONLY hits /api/v1/agent-readiness (no other endpoint)
  N3. BFF returns JSON 503 when report missing (no silent empty)
  N4. Frontend includes a §55 reminder banner (apply-rate awareness)
  N5. Auto-refresh interval ≤ BFF cache TTL (no thrash)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BFF_PATH = REPO / "services" / "frontend" / "app" / "api" / "v1" / "agent-readiness" / "route.ts"
PAGE_PATH = REPO / "services" / "frontend" / "app" / "admin" / "agent-readiness" / "page.tsx"

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


def main() -> int:
    # Step 1
    step("1. BFF + page exist at canonical Next.js paths")
    if not BFF_PATH.exists():
        fail(f"missing: {BFF_PATH.relative_to(REPO)}")
    if not PAGE_PATH.exists():
        fail(f"missing: {PAGE_PATH.relative_to(REPO)}")
    bff = BFF_PATH.read_text(encoding="utf-8")
    page = PAGE_PATH.read_text(encoding="utf-8")
    ok("BFF + page present")

    # Step 2
    step("2. BFF reads .loop/agent_readiness_report.json")
    if "agent_readiness_report.json" not in bff:
        fail("BFF doesn't reference the readiness report file")
    if "readFile" not in bff and "readFileSync" not in bff:
        fail("BFF never reads the report file from disk")
    ok("BFF reads .loop/agent_readiness_report.json")

    # Step 3
    step("3. BFF re-runs script on stale report (>5 min)")
    if "STALE_THRESHOLD_MS" not in bff:
        fail("BFF missing STALE_THRESHOLD_MS — would serve unbounded-stale data")
    if "agent_readiness_check.py" not in bff:
        fail("BFF doesn't reference the script that produces the report")
    ok("BFF re-runs script when report is stale")

    # Step 4
    step("4. frontend renders all 7 probes A..G with titles")
    expected_keys = (
        "A_models_work", "B_orchestrator_up", "C_council_active",
        "D_apply_rate", "E_work_assignable", "F_mcp_fleet",
        "G_council_nodes",
    )
    for k in expected_keys:
        if k not in page:
            fail(f"frontend missing probe key: {k}")
    ok("all 7 probe keys (A..G) referenced in page")

    # Step 5
    step("5. StatusBadge covers all 4 statuses")
    for s in ("YES", "NO", "MIXED", "UNKNOWN"):
        if f"{s}:" not in page and f"'{s}'" not in page and f'"{s}"' not in page:
            fail(f"StatusBadge map missing colour for {s}")
    ok("StatusBadge covers YES/NO/MIXED/UNKNOWN")

    # Step 6 — NEGATIVE: BFF read-only
    step("6. NEGATIVE: BFF only execs the readiness script (no other shell)")
    exec_calls = re.findall(r"execP\(`([^`]+)`", bff)
    for c in exec_calls:
        if "agent_readiness_check.py" not in c and "${SCRIPT_PATH}" not in c:
            fail(f"BFF execs unexpected command: {c[:80]}")
    ok(f"BFF execs only readiness script ({len(exec_calls)} call sites)")

    # Step 7 — NEGATIVE: frontend only hits canonical BFF
    step("7. NEGATIVE: frontend fetches ONLY /api/v1/agent-readiness")
    fetches = re.findall(r"fetch\((['\"])([^'\"]+)\1", page)
    if not fetches:
        fail("no fetch() calls — page broken")
    for _, url in fetches:
        if not url.startswith("/api/v1/agent-readiness"):
            fail(f"frontend fetches unexpected URL: {url}")
    ok(f"all {len(fetches)} fetches go to /api/v1/agent-readiness")

    # Step 8 — NEGATIVE: BFF returns 503 on missing report
    step("8. NEGATIVE: BFF returns 503 JSON on missing report")
    if "agent_readiness_report_missing" not in bff:
        fail("BFF doesn't emit agent_readiness_report_missing error code")
    if "503" not in bff:
        fail("BFF doesn't emit 503 status on missing file")
    ok("BFF returns 503 with structured JSON on missing report")

    # Step 9 — NEGATIVE: §55 reminder banner present
    step("9. NEGATIVE: frontend has §55 apply-rate reminder banner")
    if "§55" not in page:
        fail("frontend doesn't surface §55 brutal-rule reminder — apply rate could go unnoticed")
    ok("§55 reminder banner present (apply-rate awareness)")

    # Step 10 — NEGATIVE: auto-refresh ≤ cache TTL
    step("10. NEGATIVE: auto-refresh ≤ BFF cache TTL (no thrash)")
    m_ttl = re.search(r"CACHE_TTL_MS\s*=\s*(\d[\d_]*)", bff)
    if not m_ttl:
        fail("BFF missing CACHE_TTL_MS")
    ttl = int(m_ttl.group(1).replace("_", ""))
    m_int = re.search(r"setInterval\(load,\s*(\d[\d_]*)\)", page)
    if not m_int:
        fail("page missing setInterval auto-refresh")
    interval = int(m_int.group(1).replace("_", ""))
    if interval > ttl:
        fail(f"auto-refresh {interval}ms > cache TTL {ttl}ms — script-fork thrash")
    ok(f"auto-refresh {interval}ms ≤ cache TTL {ttl}ms (no thrash)")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
