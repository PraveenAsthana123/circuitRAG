"""Audit the 35-scenario agentic observability catalog (iter-96).

Per CLAUDE.md §44 (iter-96), §57.5 (5-question runbook),
§38 (governance — verifiable claims).

Loads `config/agentic_observability/scenarios.yaml`, counts scenarios
by status (wired / partial / gap), and writes
`.loop/agentic_observability_audit.json` for UI consumption.

Per the user blueprint: "track every operation as Who requested?
Which agent decided? Which tool was called? Was policy checked? What
data was used? What model responded? Was it evaluated? Was it
approved? Can we replay or rollback?"

CLI
---
$ python3 scripts/agentic_observability_audit.py            # text report
$ python3 scripts/agentic_observability_audit.py --json     # machine-readable
$ python3 scripts/agentic_observability_audit.py --gaps     # only gaps
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "config" / "agentic_observability" / "scenarios.yaml"
MISSING_TOOLS = REPO / "config" / "agentic_observability" / "missing_tools.yaml"
OUT = REPO / ".loop" / "agentic_observability_audit.json"

REQUIRED_FIELDS_GLOBAL = ("id", "scenario", "operation", "primary_tool",
                          "span_name", "required_fields", "status",
                          "evidence_path")
ALLOWED_STATUSES = frozenset({"wired", "partial", "gap"})


def load_yaml(p: Path) -> dict:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        print("pyyaml not installed", file=sys.stderr)
        sys.exit(2)
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--gaps", action="store_true",
                   help="only show scenarios with status=gap")
    args = p.parse_args()

    catalog = load_yaml(CATALOG)
    missing = load_yaml(MISSING_TOOLS)

    scenarios = catalog.get("scenarios", [])
    by_status: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    issues: list[str] = []

    for s in scenarios:
        # Validate
        for f in REQUIRED_FIELDS_GLOBAL:
            if f not in s:
                issues.append(f"scenario {s.get('id', '?')}: missing field {f}")
        st = s.get("status", "")
        if st not in ALLOWED_STATUSES:
            issues.append(f"scenario {s.get('id')}: invalid status {st!r}")
        by_status[st] = by_status.get(st, 0) + 1
        tool = s.get("primary_tool", "unknown")
        by_tool[tool] = by_tool.get(tool, 0) + 1
        # required_fields must include request_id or trace_id (forensic substrate)
        rf = set(s.get("required_fields", []))
        if not rf & {"request_id", "trace_id", "council_id", "namespace", "tenant_id"}:
            issues.append(
                f"scenario {s.get('id')}: required_fields lacks any of "
                f"request_id/trace_id/council_id/namespace/tenant_id (§57.6)"
            )

    n_wired = by_status.get("wired", 0)
    n_partial = by_status.get("partial", 0)
    n_gap = by_status.get("gap", 0)
    total = len(scenarios)
    coverage_pct = int(100 * (n_wired + 0.5 * n_partial) / total) if total else 0

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_scenarios": total,
        "by_status": by_status,
        "by_tool": by_tool,
        "coverage_pct": coverage_pct,
        "validation_issues": issues,
        "missing_tools_planned": len(missing.get("tools", [])),
        "missing_tools_top_priority": missing.get("top_priority_order", []),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
        return 1 if issues else 0

    print("=" * 60)
    print("AGENTIC OBSERVABILITY CATALOG AUDIT")
    print("=" * 60)
    print(f"Total scenarios:    {total}")
    print(f"Wired:              {n_wired}/{total}")
    print(f"Partial:            {n_partial}/{total}")
    print(f"Gap:                {n_gap}/{total}")
    print(f"Coverage:           {coverage_pct}%")
    print(f"Validation issues:  {len(issues)}")
    print()
    if args.gaps:
        gap_rows = [s for s in scenarios if s.get("status") == "gap"]
        for s in gap_rows:
            print(f"  GAP #{s['id']:>2}: {s['scenario']}")
            print(f"      → {s.get('primary_tool')} → {s.get('evidence_path')}")
        print()
    print("Top tools (by scenario count):")
    for t, n in sorted(by_tool.items(), key=lambda x: -x[1])[:8]:
        print(f"  {n:>2}  {t}")
    print()
    print(f"Missing-tool backlog: {summary['missing_tools_planned']} entries")
    print(f"Top priority: {', '.join(summary['missing_tools_top_priority'][:5])}")
    print()
    print(f"Wrote: {OUT.relative_to(REPO)}")
    if issues:
        print("\nVALIDATION ISSUES:")
        for iss in issues[:5]:
            print(f"  - {iss}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
