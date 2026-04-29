#!/usr/bin/env python3
"""Drill catalog summary — one report for tiering, resource sets, and ratchets.

Reads the drill catalog from `mcp/tests/drill_*.py`, using the same
resource-tag semantics as `scripts/run_drills.py`:

  * `# RESOURCES: readonly` / `none` -> zero-resource tier
  * explicit resources -> parsed as written
  * missing tag -> safe default "touches everything"

The report is intended for operators and maintainers who want a quick
snapshot of:
  * total drill count
  * zero-resource vs tagged vs defaulted drills
  * distribution by exact resource set
  * top individual resource usage counts
  * current ratchet status (delegated to scripts/ratchet_status.py)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DRILL_DIR = REPO / "mcp" / "tests"
RESOURCE_TAG_RE = re.compile(r"^#\s*RESOURCES\s*:\s*(.+)$", re.MULTILINE)
DEFAULT_RESOURCES: frozenset[tuple[str, str]] = frozenset({
    ("mcp_hr", "write"),
    ("inference", "write"),
    ("pg", "write"),
})
RATCHET_STATUS = REPO / "scripts" / "ratchet_status.py"


def _parse_resource_tokens(tokens: list[str]) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for token in tokens:
        if ":" in token:
            name, _, mode = token.partition(":")
            mode = mode.strip().lower()
            if mode not in {"read", "write"}:
                mode = "write"
            out.add((name.strip(), mode))
        else:
            out.add((token.strip(), "write"))
    return frozenset(out)


def _discover() -> list[dict[str, Any]]:
    drills: list[dict[str, Any]] = []
    for path in sorted(DRILL_DIR.glob("drill_*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = RESOURCE_TAG_RE.search(text)
        resource_source = "defaulted"
        if match:
            tokens = [t.strip() for t in match.group(1).split() if t.strip()]
            if tokens in (["none"], ["readonly"]):
                resources: frozenset[tuple[str, str]] = frozenset()
                resource_source = "zero"
            else:
                resources = _parse_resource_tokens(tokens)
                resource_source = "tagged"
        else:
            resources = DEFAULT_RESOURCES
        drills.append(
            {
                "name": path.name,
                "resources": resources,
                "resource_source": resource_source,
            }
        )
    return drills


def _resource_key(resources: frozenset[tuple[str, str]]) -> str:
    if not resources:
        return "readonly/none"
    return ", ".join(f"{name}:{mode}" for name, mode in sorted(resources))


def _load_ratchet_status() -> dict[str, Any] | None:
    if not RATCHET_STATUS.exists():
        return None
    result = subprocess.run(
        [sys.executable, str(RATCHET_STATUS), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode not in {0, 1, 2}:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def collect_summary() -> dict[str, Any]:
    drills = _discover()
    exact_sets = Counter(_resource_key(item["resources"]) for item in drills)
    per_resource = Counter()
    per_mode = Counter()
    source_counts = Counter(item["resource_source"] for item in drills)
    for item in drills:
        for name, mode in item["resources"]:
            per_resource[name] += 1
            per_mode[mode] += 1

    ratchets = _load_ratchet_status()
    return {
        "total_drills": len(drills),
        "resource_source_counts": dict(source_counts),
        "exact_resource_sets": dict(sorted(exact_sets.items(), key=lambda kv: (-kv[1], kv[0]))),
        "resource_usage_counts": dict(sorted(per_resource.items(), key=lambda kv: (-kv[1], kv[0]))),
        "resource_mode_counts": dict(sorted(per_mode.items())),
        "ratchets": ratchets,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [f"total_drills: {summary['total_drills']}"]
    source_counts = summary["resource_source_counts"]
    lines.append(f"  zero_resource: {source_counts.get('zero', 0)}")
    lines.append(f"  tagged: {source_counts.get('tagged', 0)}")
    lines.append(f"  defaulted: {source_counts.get('defaulted', 0)}")

    lines.append("")
    lines.append("resource_sets:")
    for key, count in summary["exact_resource_sets"].items():
        lines.append(f"  {count:>3}  {key}")

    lines.append("")
    lines.append("resource_usage:")
    for key, count in summary["resource_usage_counts"].items():
        lines.append(f"  {count:>3}  {key}")

    mode_counts = summary["resource_mode_counts"]
    if mode_counts:
        lines.append("")
        lines.append(f"resource_modes: {mode_counts}")

    ratchets = summary.get("ratchets")
    if ratchets:
        lines.append("")
        lines.append(f"ratchet_state: {ratchets.get('ratchet_state', 'unknown')}")
        for key in [
            "resources_new_drift",
            "audit_new_drift",
            "neg_new_drift",
            "section7_extra_paths",
        ]:
            value = ratchets.get(key)
            if value not in (None, [], {}):
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = parser.parse_args()
    summary = collect_summary()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(render_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
