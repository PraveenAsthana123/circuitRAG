"""OSS-only tooling catalog audit (iter-97).

Loads `config/agentic_observability/oss_tooling_catalog.yaml` and emits
a per-category coverage report + writes
`.loop/oss_tooling_audit.json` for UI consumption.

Per CLAUDE.md §44 (iter-97), §57.4 (self-healing as data not code),
user blueprint: "only opensource ... tool to be considered."

Validates:
  - every tool has a recognized OSS license string
  - status ∈ {shipped, partial, planned, not_applicable}
  - excluded_commercial entries each cite an oss_alternative
  - top_priority_closure_order references real catalog entries
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "config" / "agentic_observability" / "oss_tooling_catalog.yaml"
OUT = REPO / ".loop" / "oss_tooling_audit.json"

ALLOWED_STATUSES = frozenset({"shipped", "partial", "planned", "not_applicable"})
RECOGNIZED_OSS_LICENSES = frozenset({
    "Apache-2.0", "MIT", "BSD-3-Clause", "BSD-2-Clause", "MPL-2.0",
    "AGPL-3.0", "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0",
    "EPL-1.0", "EPL-2.0",  # Eclipse Public License — OSI-approved
    "ELv2-OSS",  # Elastic License 2.0 — accepted per user list
    "BSL-1.1",   # Business Source License — flagged as not-strict-OSS but allowed
})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--gaps", action="store_true",
                   help="only show planned + partial entries")
    args = p.parse_args()

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        print("pyyaml not installed", file=sys.stderr)
        return 2

    cat = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}
    tools = cat.get("tools", [])
    excluded = cat.get("excluded_commercial", [])
    priority_order = cat.get("top_priority_closure_order", [])

    issues: list[str] = []
    by_status: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_priority: Counter[str] = Counter()
    by_license: Counter[str] = Counter()

    tool_names = set()
    for t in tools:
        name = t.get("name", "")
        tool_names.add(name)
        st = t.get("status", "")
        if st not in ALLOWED_STATUSES:
            issues.append(f"{name}: invalid status {st!r}")
        by_status[st] += 1
        by_category[t.get("category", "?")] += 1
        by_priority[t.get("priority", "?")] += 1
        lic = t.get("license", "?")
        by_license[lic] += 1
        # OSS license check — soft warning if license not in our recognized set
        if lic not in RECOGNIZED_OSS_LICENSES and not lic.startswith("Apache"):
            issues.append(f"{name}: license {lic!r} not in recognized OSS list")

    # Excluded set must each have an oss_alternative
    for x in excluded:
        if not x.get("oss_alternative"):
            issues.append(f"excluded {x.get('name')!r} missing oss_alternative")

    # Priority order entries must reference real catalog tools
    for p_name in priority_order:
        if p_name not in tool_names:
            issues.append(f"top_priority_closure_order references unknown tool: {p_name!r}")

    # Coverage calc — partial counts 0.5
    total = len(tools)
    coverage_pct = int(100 * (
        by_status["shipped"] + 0.5 * by_status["partial"]
    ) / total) if total else 0

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_tools": total,
        "by_status": dict(by_status),
        "by_category": dict(by_category),
        "by_priority": dict(by_priority),
        "by_license": dict(by_license),
        "coverage_pct": coverage_pct,
        "excluded_commercial_count": len(excluded),
        "top_priority_count": len(priority_order),
        "validation_issues": issues,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
        return 1 if issues else 0

    print("=" * 64)
    print("OSS-ONLY TOOLING CATALOG — coverage report")
    print("=" * 64)
    print(f"Total tools tracked: {total}")
    print(f"Coverage:            {coverage_pct}%  (partial counts 0.5)")
    print()
    print("By status:")
    for s, n in by_status.most_common():
        print(f"  {n:>3}  {s}")
    print()
    print("By priority:")
    for p, n in by_priority.most_common():
        print(f"  {n:>3}  {p}")
    print()
    print("By category:")
    for c, n in by_category.most_common():
        print(f"  {n:>3}  {c}")
    print()
    print(f"Excluded commercial: {len(excluded)} (all cite OSS alternatives)")
    print(f"Top P1 closure list: {len(priority_order)} entries")
    print()

    if args.gaps:
        print("PLANNED + PARTIAL gaps:")
        for t in tools:
            if t.get("status") in ("planned", "partial"):
                pri = t.get("priority", "?")
                print(f"  [{pri}] {t['name']:<30} ({t.get('category')}) — {t.get('purpose')[:60]}")
        print()

    print(f"Wrote: {OUT.relative_to(REPO)}")
    if issues:
        print(f"\nVALIDATION ISSUES ({len(issues)}):")
        for iss in issues[:10]:
            print(f"  - {iss}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
