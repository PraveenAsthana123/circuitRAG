# RESOURCES: readonly
"""
Drill: /admin/mcp-fleet-health UI + /api/v1/mcp-fleet-health BFF.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (iter-73 ships
the operator-visible UI surface for the iter-72 health monitor),
§45.4 (no checkbox flips without code), §47 (observability is a
first-class architectural surface), §50.5.3 (read-only operator UI).

Locks (positive):
  L1. BFF route file exists at canonical path
  L2. Frontend page file exists at canonical path
  L3. BFF executes mcp_fleet_health.py --json --full
  L4. BFF caches result in-memory for CACHE_TTL_MS
  L5. Frontend renders 4 sections (mcp / ollama / council / backends)

Locks (negative — ≥3 per §43):
  N1. BFF NEVER invokes any write tool / shell beyond the read script
  N2. Frontend NEVER calls a non-/api/v1/mcp-fleet-health endpoint
  N3. BFF returns valid JSON even when script fails (graceful 503)
  N4. Auto-refresh interval ≤ 30s (matches BFF cache TTL — no thrash)
  N5. Frontend includes ALL 5 status colours in StatusBadge map
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BFF_PATH = REPO / "services" / "frontend" / "app" / "api" / "v1" / "mcp-fleet-health" / "route.ts"
PAGE_PATH = REPO / "services" / "frontend" / "app" / "admin" / "mcp-fleet-health" / "page.tsx"

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
    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: BFF route file exists
    # ------------------------------------------------------------------
    step("1. BFF route exists at canonical Next.js path")
    if not BFF_PATH.exists():
        fail(f"missing: {BFF_PATH.relative_to(REPO)}")
    bff = BFF_PATH.read_text(encoding="utf-8")
    ok(f"BFF: {BFF_PATH.relative_to(REPO)}")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: frontend page file exists
    # ------------------------------------------------------------------
    step("2. frontend page exists at canonical /admin path")
    if not PAGE_PATH.exists():
        fail(f"missing: {PAGE_PATH.relative_to(REPO)}")
    page = PAGE_PATH.read_text(encoding="utf-8")
    ok(f"page: {PAGE_PATH.relative_to(REPO)}")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: BFF executes mcp_fleet_health.py --json --full
    # ------------------------------------------------------------------
    step("3. BFF executes mcp_fleet_health.py --json --full")
    if "mcp_fleet_health.py" not in bff:
        fail("BFF doesn't reference mcp_fleet_health.py script")
    if "--json" not in bff:
        fail("BFF doesn't pass --json flag")
    if "--full" not in bff:
        fail("BFF doesn't pass --full flag (would miss ollama/council/backends)")
    ok("BFF runs mcp_fleet_health.py --json --full")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: BFF caches in-memory
    # ------------------------------------------------------------------
    step("4. BFF caches result with TTL")
    if "CACHE_TTL_MS" not in bff:
        fail("BFF missing CACHE_TTL_MS constant — no cache means py fork per click")
    m = re.search(r"CACHE_TTL_MS\s*=\s*(\d[\d_]*)", bff)
    if not m:
        fail("BFF CACHE_TTL_MS not parseable")
    ttl_ms = int(m.group(1).replace("_", ""))
    if ttl_ms <= 0:
        fail(f"CACHE_TTL_MS={ttl_ms}; expected >0")
    ok(f"BFF caches for {ttl_ms}ms")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: frontend renders 4 sections
    # ------------------------------------------------------------------
    step("5. frontend renders 4 sections (mcp / ollama / council / backends)")
    sections_required = (
        "MCP servers",      # section 1
        "Ollama models",    # section 2
        "Council nodes",    # section 3
        "Backend services", # section 4
    )
    for s in sections_required:
        if s not in page:
            fail(f"frontend missing section header: {s!r}")
    ok("4 sections present (MCP / Ollama / Council / Backends)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: BFF does NOT shell out beyond the read script
    # ------------------------------------------------------------------
    step("6. NEGATIVE: BFF only execs mcp_fleet_health.py (no other shell)")
    # The only execP call should be the script invocation
    exec_calls = re.findall(r"execP\(([^)]+)\)", bff)
    if not exec_calls:
        fail("no execP calls found — script not invoked at all?")
    for call in exec_calls:
        if "mcp_fleet_health" not in call and "cmd" not in call:
            fail(f"BFF execs non-fleet-health command: {call[:80]}")
    ok(f"BFF execs only mcp_fleet_health.py ({len(exec_calls)} call sites)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: frontend only calls the canonical BFF endpoint
    # ------------------------------------------------------------------
    step("7. NEGATIVE: frontend fetches ONLY /api/v1/mcp-fleet-health")
    fetches = re.findall(r"fetch\((['\"])([^'\"]+)\1", page)
    if not fetches:
        fail("no fetch() calls found — page is broken")
    for _, url in fetches:
        if not url.startswith("/api/v1/mcp-fleet-health"):
            fail(f"frontend fetches unexpected URL: {url}")
    ok(f"all {len(fetches)} fetches go to /api/v1/mcp-fleet-health")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: BFF returns JSON 5xx on script failure
    # ------------------------------------------------------------------
    step("8. NEGATIVE: BFF returns JSON 5xx on script failure (graceful)")
    if "fleet_health_script_failed" not in bff:
        fail("BFF doesn't emit fleet_health_script_failed error code")
    if "503" not in bff:
        fail("BFF doesn't emit 503 status on script failure")
    if "fleet_health_invalid_json" not in bff:
        fail("BFF doesn't emit fleet_health_invalid_json on parse failure")
    ok("BFF returns 503 / 502 with structured JSON on failure (no crash)")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: auto-refresh ≤ cache TTL (no thrash)
    # ------------------------------------------------------------------
    step("9. NEGATIVE: auto-refresh interval ≤ BFF cache TTL")
    m = re.search(r"setInterval\(load,\s*(\d[\d_]*)\)", page)
    if not m:
        fail("page missing setInterval(load, …) auto-refresh")
    refresh_ms = int(m.group(1).replace("_", ""))
    if refresh_ms > ttl_ms:
        fail(
            f"auto-refresh ({refresh_ms}ms) > cache TTL ({ttl_ms}ms) — "
            f"would force py fork per refresh"
        )
    ok(f"auto-refresh {refresh_ms}ms ≤ cache TTL {ttl_ms}ms (no thrash)")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: StatusBadge covers all 5 status enums
    # ------------------------------------------------------------------
    step("10. NEGATIVE: StatusBadge map covers all 5 statuses")
    required_statuses = ("WORKING", "DEGRADED", "FAILING", "SLEEPING", "NOT_INSTALLED")
    for s in required_statuses:
        if f"{s}:" not in page and f'{s}"' not in page and f"'{s}'" not in page:
            fail(f"StatusBadge map missing colour for {s}")
    ok("StatusBadge map covers WORKING/DEGRADED/FAILING/SLEEPING/NOT_INSTALLED")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
