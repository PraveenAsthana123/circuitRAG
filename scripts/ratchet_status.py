#!/usr/bin/env python3
"""Ratchet status — one-shot survey of the current discipline ratchets.

Reads the live ratchet definitions from:
  * mcp/tests/drill_drill_catalog_discipline.py
  * mcp/tests/drill_sidecar_nextjs_page.py
  * docs/NEXT_POLICY.md

Reports:
  * KNOWN_MISSING                     (# RESOURCES tag ratchet)
  * KNOWN_MISSING_NEG_MARKER         (docstring marker ratchet)
  * §7 scope-extension grant         (sidecar path whitelist ratchet)
  * catalog ratchets paid down       (operator-facing summary bit)

The command is intentionally read-only and operator-facing:

  $ python3 scripts/ratchet_status.py
  ratchet_state: HEALTHY
    known_missing_count: 0
    resources_new_drift: 0
    ...

Exit codes:
  0  HEALTHY (no new drift)
  1  WARNING (new drift detected in one or more ratchets)
  2  ERROR   (required policy/drill files missing or unparsable)
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DRILL_CATALOG = REPO / "mcp" / "tests" / "drill_drill_catalog_discipline.py"
SIDECAR_SCOPE_DRILL = REPO / "mcp" / "tests" / "drill_sidecar_nextjs_page.py"
NEXT_POLICY = REPO / "docs" / "NEXT_POLICY.md"
DRILL_DIR = REPO / "mcp" / "tests"
SIDECAR_DIR = REPO / "services" / "frontend" / "app" / "admin" / "sidecar"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_local_set(path: Path, name: str) -> set[str]:
    module = ast.parse(_read(path), filename=str(path))
    for node in ast.walk(module):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = ast.literal_eval(node.value)
                    return set(value)
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                value = ast.literal_eval(node.value)
                return set(value)
    raise ValueError(f"{path}: could not find set {name}")


def _drill_files() -> list[Path]:
    return sorted(
        p for p in DRILL_DIR.glob("drill_*.py")
        if p.name != DRILL_CATALOG.name
    )


def _module_docstring_text(path: Path) -> str | None:
    text = _read(path)
    m = re.search(r'"""(.*?)"""', text, re.DOTALL)
    if not m:
        m = re.search(r"'''(.*?)'''", text, re.DOTALL)
    if not m:
        return None
    return m.group(1)


def _actual_missing_resources(drills: list[Path]) -> set[str]:
    missing = set()
    for path in drills:
        if not re.search(r"^# RESOURCES:", _read(path), re.MULTILINE):
            missing.add(path.name)
    return missing


def _actual_no_exit_signal(drills: list[Path]) -> set[str]:
    out = set()
    for path in drills:
        body = _read(path)
        has_explicit_exit = (
            "sys.exit(" in body
            or "SystemExit(" in body
            or "os._exit(" in body
        )
        has_async_pattern = (
            "asyncio.run(main" in body
            and ("raise " in body or "assert " in body)
        )
        if not has_explicit_exit and not has_async_pattern:
            out.add(path.name)
    return out


def _actual_no_negative_marker(drills: list[Path]) -> set[str]:
    out = set()
    for path in drills:
        doc = _module_docstring_text(path)
        if doc is None or "negative" not in doc.lower():
            out.add(path.name)
    return out


def _extract_scope_allowed_paths() -> set[str]:
    module = ast.parse(_read(SIDECAR_SCOPE_DRILL), filename=str(SIDECAR_SCOPE_DRILL))
    for node in ast.walk(module):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "allowed_relative":
                    return set(ast.literal_eval(node.value))
    raise ValueError(f"{SIDECAR_SCOPE_DRILL}: could not find allowed_relative set")


def _actual_scope_paths() -> set[str]:
    if not SIDECAR_DIR.exists():
        return set()
    return {str(p.relative_to(SIDECAR_DIR)) for p in SIDECAR_DIR.rglob("*.tsx")}


def _next_policy_scope_entries() -> list[str]:
    text = _read(NEXT_POLICY)
    entries: list[str] = []
    patterns = [
        r"/admin/sidecar\b",
        r"/admin/sidecar/deep\b",
        r"/admin/sidecar/telemetry\b",
    ]
    for pattern in patterns:
        if re.search(pattern, text):
            entries.append(pattern.replace(r"\b", "").replace("\\", ""))
    return entries


def collect_status() -> dict[str, Any]:
    status: dict[str, Any] = {
        "ratchet_state": "HEALTHY",
    }
    warnings: list[str] = []
    errors: list[str] = []

    try:
        drills = _drill_files()
        known_missing = _extract_local_set(DRILL_CATALOG, "KNOWN_MISSING")
        known_no_neg = _extract_local_set(DRILL_CATALOG, "KNOWN_MISSING_NEG_MARKER")
        scope_allowed = _extract_scope_allowed_paths()
    except (OSError, SyntaxError, ValueError) as exc:
        errors.append(str(exc))
        return {
            "ratchet_state": "ERROR",
            "errors": errors,
        }

    actual_missing = _actual_missing_resources(drills)
    actual_no_neg = _actual_no_negative_marker(drills)
    actual_scope = _actual_scope_paths()
    policy_scope_entries = _next_policy_scope_entries()

    resources_new = sorted(actual_missing - known_missing)
    resources_stale = sorted(known_missing - actual_missing)
    neg_new = sorted(actual_no_neg - known_no_neg)
    neg_stale = sorted(known_no_neg - actual_no_neg)
    scope_extra = sorted(actual_scope - scope_allowed)
    scope_missing = sorted(scope_allowed - actual_scope)

    status.update(
        {
            "known_missing_count": len(known_missing),
            "resources_actual_missing": len(actual_missing),
            "resources_new_drift": len(resources_new),
            "resources_stale_entries": len(resources_stale),
            "resources_new_files": resources_new,
            "resources_stale_files": resources_stale,
            "known_missing_neg_marker_count": len(known_no_neg),
            "neg_actual_missing_marker": len(actual_no_neg),
            "neg_new_drift": len(neg_new),
            "neg_stale_entries": len(neg_stale),
            "neg_new_files": neg_new,
            "neg_stale_files": neg_stale,
            "section7_allowed_paths_count": len(scope_allowed),
            "section7_actual_paths_count": len(actual_scope),
            "section7_extra_paths": scope_extra,
            "section7_missing_paths": scope_missing,
            "section7_policy_mentions": policy_scope_entries,
            "catalog_ratchets_paid_down": (
                len(known_missing) == 0
                and len(actual_missing) == 0
                and len(known_no_neg) == 0
                and len(actual_no_neg) == 0
            ),
        }
    )

    if resources_new:
        warnings.append(f"{len(resources_new)} new # RESOURCES drift file(s)")
    if neg_new:
        warnings.append(f"{len(neg_new)} new NEGATIVE-marker drift file(s)")
    if scope_extra or scope_missing:
        warnings.append(
            f"§7 scope drift detected (extra={len(scope_extra)} missing={len(scope_missing)})"
        )

    if errors:
        status["ratchet_state"] = "ERROR"
        status["errors"] = errors
    elif warnings:
        status["ratchet_state"] = "WARNING"
        status["warnings"] = warnings

    return status


def render_text(status: dict[str, Any]) -> str:
    lines = [f"ratchet_state: {status['ratchet_state']}"]
    ordered_keys = [
        "catalog_ratchets_paid_down",
        "known_missing_count",
        "resources_actual_missing",
        "resources_new_drift",
        "resources_stale_entries",
        "known_missing_neg_marker_count",
        "neg_actual_missing_marker",
        "neg_new_drift",
        "neg_stale_entries",
        "section7_allowed_paths_count",
        "section7_actual_paths_count",
    ]
    for key in ordered_keys:
        if key in status:
            lines.append(f"  {key}: {status[key]}")

    detail_keys = [
        "resources_new_files",
        "resources_stale_files",
        "neg_new_files",
        "neg_stale_files",
        "section7_extra_paths",
        "section7_missing_paths",
        "section7_policy_mentions",
    ]
    for key in detail_keys:
        value = status.get(key)
        if value:
            lines.append(f"  {key}: {value}")

    if "warnings" in status:
        lines.append("")
        lines.append("Warnings:")
        for item in status["warnings"]:
            lines.append(f"  - {item}")
    if "errors" in status:
        lines.append("")
        lines.append("Errors:")
        for item in status["errors"]:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = parser.parse_args()

    status = collect_status()
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(render_text(status))

    return {"HEALTHY": 0, "WARNING": 1, "ERROR": 2}.get(status["ratchet_state"], 2)


if __name__ == "__main__":
    sys.exit(main())
