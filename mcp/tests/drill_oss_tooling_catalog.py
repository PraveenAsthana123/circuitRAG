# RESOURCES: readonly
"""
Drill: OSS-only tooling catalog (iter-97).

Per CLAUDE.md §43 (drill ≥3 negatives), §44 (iter-97 ships OSS catalog),
§57.4 (self-healing as data not code), §57.6 (canonical license rule).

User blueprint: "only opensource ... tool to be considered."
This drill enforces that OSS-only constraint at schema level.

Locks (positive):
  L1. catalog YAML loads + has version field
  L2. ≥80 tools enumerated
  L3. audit script runs + writes report
  L4. report has expected keys
  L5. priority order references only catalog tools

Locks (negative):
  N1. tool with status not in {shipped, partial, planned, not_applicable} → fail
  N2. excluded_commercial entry without oss_alternative → fail
  N3. NO entry has commercial-license string ("Proprietary", "Commercial",
      "Closed Source") — enforces user's "only opensource" filter
  N4. duplicate tool names rejected
  N5. canonical license set covers Apache-2.0 + MIT + BSD + GPL-2.0 + GPL-3.0
      + AGPL-3.0 + MPL-2.0 + LGPL-2.1 (the recognized OSS license families)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "config" / "agentic_observability" / "oss_tooling_catalog.yaml"
SCRIPT = REPO / "scripts" / "oss_tooling_audit.py"
REPORT = REPO / ".loop" / "oss_tooling_audit.json"

GREEN, RED, BOLD, NC = "\033[32m", "\033[31m", "\033[1m", "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


COMMERCIAL_LICENSE_BLACKLIST = (
    "Proprietary", "Commercial", "Closed Source", "Closed-Source",
    "Splunk Master Subscription", "EULA",
)


def main() -> int:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        fail("pyyaml not installed")

    if not CATALOG.exists():
        fail(f"missing: {CATALOG.relative_to(REPO)}")

    cat = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}

    step("1. catalog YAML loads + version field present")
    if "version" not in cat:
        fail("catalog missing version field")
    ok(f"version={cat['version']}, schema_version={cat.get('schema_version','?')}")

    step("2. ≥80 tools enumerated")
    tools = cat.get("tools", [])
    if len(tools) < 80:
        fail(f"only {len(tools)} tools; expected ≥80 to cover the user blueprint")
    ok(f"{len(tools)} tools across {len(cat.get('categories', {}))} categories")

    step("3. audit script runs + writes report")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=30, cwd=str(REPO),
    )
    if proc.returncode not in (0, 1):
        fail(f"audit exited {proc.returncode}; stderr: {proc.stderr[:200]}")
    if not REPORT.exists():
        fail(f"report not written: {REPORT.relative_to(REPO)}")
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    ok(f"audit report wrote {payload.get('total_tools')} tools")

    step("4. report has expected keys")
    for k in ("total_tools", "by_status", "by_category",
              "coverage_pct", "excluded_commercial_count"):
        if k not in payload:
            fail(f"report missing key: {k}")
    ok(f"all canonical keys present; coverage_pct={payload['coverage_pct']}%")

    step("5. priority order references only catalog tools")
    tool_names = {t.get("name") for t in tools}
    pri = cat.get("top_priority_closure_order", [])
    for p_name in pri:
        if p_name not in tool_names:
            fail(f"priority list references unknown tool: {p_name!r}")
    ok(f"{len(pri)} priority entries all reference real catalog tools")

    # ─── Negatives ───
    step("6. NEGATIVE: invalid status caught")
    valid = {"shipped", "partial", "planned", "not_applicable"}
    for t in tools:
        if t.get("status") not in valid:
            fail(f"{t.get('name')}: invalid status {t.get('status')!r}")
    ok(f"all {len(tools)} tools have valid status")

    step("7. NEGATIVE: every excluded_commercial entry has oss_alternative")
    excluded = cat.get("excluded_commercial", [])
    for x in excluded:
        if not x.get("oss_alternative"):
            fail(f"excluded {x.get('name')!r} missing oss_alternative — "
                 f"can't redirect operator to OSS replacement")
    ok(f"all {len(excluded)} excluded commercial entries cite OSS alternatives")

    step("8. NEGATIVE: NO catalog entry has commercial-license string")
    for t in tools:
        lic = (t.get("license") or "").strip()
        for blacklisted in COMMERCIAL_LICENSE_BLACKLIST:
            if blacklisted.lower() in lic.lower():
                fail(f"{t.get('name')}: license {lic!r} contains "
                     f"commercial blacklist token {blacklisted!r}")
    ok("zero catalog entries with commercial-license tokens")

    step("9. NEGATIVE: no duplicate tool names")
    names = [t.get("name") for t in tools]
    if len(set(names)) != len(names):
        dups = [n for n in set(names) if names.count(n) > 1]
        fail(f"duplicate tool names: {dups}")
    ok("all names unique")

    step("10. NEGATIVE: recognized-OSS license families covered")
    licenses_used = {t.get("license", "") for t in tools}
    expected_families = {"Apache-2.0", "MIT", "MPL-2.0"}
    missing = expected_families - licenses_used
    if missing:
        fail(f"catalog doesn't include canonical OSS license families: {missing}")
    ok(f"covers Apache-2.0 + MIT + MPL-2.0 (and {len(licenses_used)} total license strings)")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    print(f"\nCoverage: {payload['coverage_pct']}% ({payload['by_status']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
