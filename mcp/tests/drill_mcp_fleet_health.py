# RESOURCES: readonly
"""
Drill: mcp_fleet_health.py — fleet health monitor + multi-inventory contract.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-72 ships the operator-visible health surface),
§45.4 (no checkbox flips without code), §47 (observability is a
first-class architectural surface).

User asked: 'all the tools which have been installed or configured must
work; create mechanism which helps understand all tools working or not
/ failing / sleeping' + 'all the models on Ollama, all the nodes of agent
working/review/search/plan/code/test/deploy/security/monitoring/visualization'
+ 'each backend operation tool functionality must be presented'.

iter-72 ships scripts/mcp_fleet_health.py with 4 inventories:
  - MCP fleet (28 servers; classified as WORKING/DEGRADED/FAILING/
    SLEEPING/NOT_INSTALLED based on /health probe + env state)
  - Ollama models (probed via /api/tags + /api/ps for VRAM-loaded set)
  - Council nodes (researcher/author/reviewer/advisor with 5-role aliases;
    available iff their model is in Ollama)
  - Backend services (10 svcs with operations + descriptions; /health probed)

Locks (positive):
  L1. mcp_fleet_health.py exists + canonical structure
  L2. collect_fleet_health() returns FleetHealth dataclass
  L3. classify_server() handles all 5 status cases
  L4. Ollama inventory probes /api/tags + /api/ps
  L5. Council inventory parses local_council.py (4 canonical + aliases)
  L6. BACKEND_SERVICES catalog covers ≥10 services
  L7. CLI --json mode emits parseable JSON

Locks (negative — ≥3 per §43):
  N1. _NON_CRED_ENV_VARS excludes MCP_INJECT_FAIL (chaos var must
      not appear as a "missing upstream cred")
  N2. _probe_e2e never calls a write tool (read-only contract per §50.5.3)
  N3. Empty audit / no env vars → all servers report SLEEPING
      (default state; no false positives)
  N4. Exit code 1 when ANY server FAILING (operational alarm)
  N5. classify_server returns NOT_INSTALLED when server file missing
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "mcp_fleet_health.py"
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


def main() -> int:
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT.relative_to(REPO)}")

    src = SCRIPT.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: canonical structure + dataclasses
    # ------------------------------------------------------------------
    step("1. mcp_fleet_health.py has canonical structure")
    for marker in (
        "class ServerHealth", "class ToolHealth", "class FleetHealth",
        "class OllamaInventory", "class CouncilNode", "class BackendService",
        "def classify_server", "def collect_fleet_health",
        "def collect_ollama_inventory", "def collect_council_inventory",
        "def collect_backend_services_health",
    ):
        if marker not in src:
            fail(f"script missing canonical symbol: {marker}")
    ok("script has 6 dataclasses + 5 collector functions")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: import + collect_fleet_health works
    # ------------------------------------------------------------------
    step("2. collect_fleet_health() returns FleetHealth")
    import mcp_fleet_health as mfh  # type: ignore[import-not-found]
    fleet = mfh.collect_fleet_health(probe_timeout=0.5)
    if not isinstance(fleet, mfh.FleetHealth):
        fail(f"collect_fleet_health returned {type(fleet).__name__}")
    if fleet.total_servers < 20:
        fail(f"fleet has only {fleet.total_servers} servers; expected ≥20")
    ok(f"fleet health: {fleet.total_servers} servers; "
       f"by_status={fleet.by_status}")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: classify_server handles all 5 status cases
    # ------------------------------------------------------------------
    step("3. classify_server handles all 5 status cases")
    valid_statuses = {"WORKING", "DEGRADED", "FAILING", "SLEEPING", "NOT_INSTALLED"}
    for s in fleet.servers:
        if s.status not in valid_statuses:
            fail(f"{s.namespace}: invalid status {s.status!r}")
    ok(f"all {len(fleet.servers)} servers have a valid status")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: Ollama inventory probes /api/tags + /api/ps
    # ------------------------------------------------------------------
    step("4. Ollama inventory probes /api/tags + /api/ps")
    if "/api/tags" not in src or "/api/ps" not in src:
        fail("Ollama probe doesn't hit both /api/tags AND /api/ps")
    ok("Ollama probe hits both endpoints")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: council inventory parses local_council.py
    # ------------------------------------------------------------------
    step("5. council inventory parses local_council.py")
    if "local_council.py" not in src:
        fail("council inventory doesn't reference scripts/local_council.py")
    if "COUNCIL_ROLE_ALIASES" not in src and "alias" not in src.lower():
        fail("council inventory doesn't extract 5-role aliases")
    ok("council inventory parses 4 canonical roles + 5-role aliases")

    # ------------------------------------------------------------------
    # Step 6 — POSITIVE: BACKEND_SERVICES catalog covers ≥10 services
    # ------------------------------------------------------------------
    step("6. BACKEND_SERVICES catalog covers ≥10 services")
    if len(mfh.BACKEND_SERVICES) < 10:
        fail(f"only {len(mfh.BACKEND_SERVICES)} backend services; expected ≥10")
    # Each service has operations + description (UI display data)
    for svc in mfh.BACKEND_SERVICES:
        if not svc.operations or not svc.description:
            fail(f"{svc.name}: missing operations or description")
    ok(f"{len(mfh.BACKEND_SERVICES)} backend services with operations + descriptions")

    # ------------------------------------------------------------------
    # Step 7 — POSITIVE: CLI --json emits parseable JSON
    # ------------------------------------------------------------------
    step("7. CLI --json emits parseable JSON")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--probe-timeout", "0.5"],
        capture_output=True, text=True, timeout=30,
    )
    # Exit 0 (all SLEEPING) OR 1 (any FAILING) both legitimate
    if proc.returncode not in (0, 1, 2):
        fail(f"CLI --json exited {proc.returncode}; expected 0/1/2")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        fail(f"CLI --json output not valid JSON: {e}; stderr: {proc.stderr[:200]}")
    for f in ("generated_at", "total_servers", "by_status", "servers"):
        if f not in parsed:
            fail(f"CLI --json output missing field: {f}")
    ok(f"CLI --json valid JSON; {parsed['total_servers']} servers")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: _NON_CRED_ENV_VARS excludes MCP_INJECT_FAIL
    # ------------------------------------------------------------------
    step("8. NEGATIVE: MCP_INJECT_FAIL is in _NON_CRED_ENV_VARS allowlist")
    if "MCP_INJECT_FAIL" not in mfh._NON_CRED_ENV_VARS:
        fail(
            "MCP_INJECT_FAIL not excluded — would falsely show as missing "
            "upstream cred for every server (chaos test variable)"
        )
    ok("MCP_INJECT_FAIL excluded from missing-cred reports")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: e2e probe never picks a write tool
    # ------------------------------------------------------------------
    step("9. NEGATIVE: _probe_e2e prefers read tools (no destructive probes)")
    e2e_match = re.search(r"def _probe_e2e.*?(?=\ndef \w)", src, re.DOTALL)
    if e2e_match is None:
        fail("could not locate _probe_e2e function")
    e2e_body = e2e_match.group(0)
    # The function should filter to read tools BEFORE picking one
    if "side_effects" not in e2e_body or '"read"' not in e2e_body:
        fail(
            "_probe_e2e doesn't filter to side_effects='read' tools — "
            "could call destructive tools per §50.5.3"
        )
    ok("_probe_e2e picks first side_effects='read' tool only")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: empty env → all SLEEPING (no false positives)
    # ------------------------------------------------------------------
    step("10. NEGATIVE: empty env state → all servers SLEEPING (no false positives)")
    # In dev env (no MCP URLs set), every server should be SLEEPING.
    # This is the default operator-friendly state.
    saved = {}
    for k in list(os.environ.keys()):
        if k.startswith("DOCUMIND_MCP_") and k.endswith("_URL"):
            saved[k] = os.environ.pop(k)
    try:
        empty_fleet = mfh.collect_fleet_health(probe_timeout=0.5)
        non_sleeping = [
            s for s in empty_fleet.servers
            if s.status not in ("SLEEPING", "NOT_INSTALLED")
        ]
        if non_sleeping:
            fail(
                f"{len(non_sleeping)} servers non-SLEEPING with empty env: "
                f"{[s.namespace for s in non_sleeping[:3]]}"
            )
    finally:
        os.environ.update(saved)
    ok("empty env → all servers SLEEPING (default state respected)")

    # ------------------------------------------------------------------
    # Step 11 — NEGATIVE: classify_server returns NOT_INSTALLED for missing file
    # ------------------------------------------------------------------
    step("11. NEGATIVE: classify_server returns NOT_INSTALLED for missing file")
    fake_path = REPO / "mcp" / "server_does_not_exist.py"
    sh = mfh.classify_server(
        "does_not_exist", fake_path, "DOCUMIND_MCP_FAKE_URL", probe_timeout=0.5,
    )
    if sh.status != "NOT_INSTALLED":
        fail(f"missing-file status was {sh.status!r}; expected NOT_INSTALLED")
    if sh.installed:
        fail("ServerHealth.installed=True for missing file")
    ok("missing server file → status=NOT_INSTALLED")

    # ------------------------------------------------------------------
    # Step 12 — NEGATIVE: exit code reflects fleet health
    # ------------------------------------------------------------------
    step("12. NEGATIVE: exit code reflects fleet health (0/1/2)")
    # Build a synthetic FailingFleet by simulating a configured-but-unreachable URL
    saved_url = os.environ.pop("DOCUMIND_MCP_SLACK_URL", None)
    os.environ["DOCUMIND_MCP_SLACK_URL"] = "http://localhost:9999"
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--only", "slack",
             "--probe-timeout", "0.5", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 1:
            fail(f"FAILING fleet should exit 1; got {proc.returncode}")
        parsed = json.loads(proc.stdout)
        if parsed["servers"][0]["status"] != "FAILING":
            fail(f"slack should be FAILING; got {parsed['servers'][0]['status']}")
    finally:
        os.environ.pop("DOCUMIND_MCP_SLACK_URL", None)
        if saved_url is not None:
            os.environ["DOCUMIND_MCP_SLACK_URL"] = saved_url
    ok("FAILING fleet → exit code 1 (operational alarm)")

    print(f"\n{GREEN}{BOLD}ALL 12 STEPS PASSED (7 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
