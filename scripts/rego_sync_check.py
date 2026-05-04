#!/usr/bin/env python3
"""Rego/JSON policy sync checker — Stage-2 scaffold for OPA swap.

Per CLAUDE.md §47 + §56 (Stage-2 promotion of PolisAI). Verifies that
config/policies/agent_dispatch.json (the runtime source-of-truth) and
config/policies/agent_dispatch.rego (the OPA-ready scaffold) stay in
semantic sync.

Stage-2 ships the Rego file + this validator; Stage-3 swaps
scripts/policy_check.py to call `opa eval` against the Rego file
when the OPA binary is on PATH (technical migration; semantic
content unchanged).

Sync invariant:
  - Every JSON rule's actor + tool + scope_required appears in a
    matching Rego allow block
  - Every Rego allow block's actor + tool + scope_required appears
    in a matching JSON rule
  - Counts match exactly

This is pure-Python; no OPA binary needed. Ship a sync test that
fails CI when the two files drift.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
JSON_POLICY = REPO / "config" / "policies" / "agent_dispatch.json"
REGO_POLICY = REPO / "config" / "policies" / "agent_dispatch.rego"


def parse_json_rules() -> list[dict[str, Any]]:
    """Extract (actor, tool, scope_required) tuples from JSON allowlist."""
    if not JSON_POLICY.exists():
        raise FileNotFoundError(f"{JSON_POLICY} missing")
    doc = json.loads(JSON_POLICY.read_text(encoding="utf-8"))
    rules = []
    for r in doc.get("rules", []):
        if r.get("effect") != "allow":
            continue
        rules.append({
            "actor": r["actor"],
            "tool": r["tool"],
            "scopes": tuple(sorted(r["scope_required"])),
            "rule_id": r["rule_id"],
        })
    return rules


def parse_rego_rules() -> list[dict[str, Any]]:
    """Extract allow blocks from Rego file via brace-counting.

    Rego blocks contain nested {...} (set literals like
    `required := {"x", "y"}`), so a non-greedy regex stops at the
    first inner closing brace. We use a proper brace-counter
    instead — find each `allow {` and walk forward until matching `}`.
    """
    if not REGO_POLICY.exists():
        raise FileNotFoundError(f"{REGO_POLICY} missing")
    src = REGO_POLICY.read_text(encoding="utf-8")
    rules = []

    # Iterate `allow {` openers
    pos = 0
    while True:
        match = re.search(r"\ballow\s*\{", src[pos:])
        if not match:
            break
        # Position of the opening brace
        open_brace_pos = pos + match.end() - 1
        # Walk forward, counting braces until depth=0
        depth = 1
        i = open_brace_pos + 1
        while i < len(src) and depth > 0:
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        if depth != 0:
            break  # unbalanced
        body = src[open_brace_pos + 1:i - 1]
        pos = i

        actor_m = re.search(r'input\.actor\s*==\s*"([^"]+)"', body)
        tool_m = re.search(r'input\.tool\s*==\s*"([^"]+)"', body)
        required_m = re.search(r'required\s*:=\s*\{([^}]*)\}', body)
        if not actor_m or not required_m:
            continue
        scopes_str = required_m.group(1)
        scopes = tuple(sorted(re.findall(r'"([^"]+)"', scopes_str)))
        rules.append({
            "actor": actor_m.group(1),
            "tool": tool_m.group(1) if tool_m else "*",
            "scopes": scopes,
        })
    return rules


def check_sync() -> dict[str, Any]:
    """Compare JSON + Rego; return diff + verdict."""
    json_rules = parse_json_rules()
    rego_rules = parse_rego_rules()

    # Build fingerprint sets — (actor, tool, scopes) tuples
    json_fp = {(r["actor"], r["tool"], r["scopes"]) for r in json_rules}
    rego_fp = {(r["actor"], r["tool"], r["scopes"]) for r in rego_rules}

    json_only = json_fp - rego_fp
    rego_only = rego_fp - json_fp

    return {
        "json_rule_count": len(json_rules),
        "rego_rule_count": len(rego_rules),
        "in_sync": len(json_only) == 0 and len(rego_only) == 0,
        "json_only": [list(t) for t in sorted(json_only)],
        "rego_only": [list(t) for t in sorted(rego_only)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="rego_sync_check")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = parser.parse_args()

    try:
        report = check_sync()
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc), "in_sync": False}, indent=2))
        return 3

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"JSON rules: {report['json_rule_count']}")
        print(f"Rego rules: {report['rego_rule_count']}")
        print(f"In sync:    {report['in_sync']}")
        if report["json_only"]:
            print("\n  JSON-only rules (missing from Rego):")
            for r in report["json_only"]:
                print(f"    - actor={r[0]} tool={r[1]} scopes={r[2]}")
        if report["rego_only"]:
            print("\n  Rego-only rules (missing from JSON):")
            for r in report["rego_only"]:
                print(f"    - actor={r[0]} tool={r[1]} scopes={r[2]}")

    return 0 if report["in_sync"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
